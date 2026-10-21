"""Display-only derivatives of original HTML; never fetch or rewrite source files.

HTML5 parsing and allowlist sanitization are followed by a restrictive CSP and
an iframe with no sandbox permissions. Only the generated wrapper is embedded
in Streamlit's component frame, which itself permits scripts by default.
"""

from collections.abc import Sequence
from html import escape

from .dataset import SourceDocument

_TAGS = frozenset("""
    a abbr b bdi bdo blockquote br caption center cite code col colgroup dd del
    details div dl dt em figcaption figure font h1 h2 h3 h4 h5 h6 hr i ins kbd
    li main mark ol p pre q s samp section small span strike strong sub summary
    sup table tbody td tfoot th thead tr tt u ul var wbr
""".split())
_DROP_CONTENT = frozenset({
    "head", "script", "style", "iframe", "object", "embed", "template",
    "svg", "math", "ix:header", "ix:hidden",
})
_ATTRIBUTES = {
    "*": ["style", "title", "lang", "dir", "align"],
    "table": ["border", "cellpadding", "cellspacing", "width", "bgcolor"],
    "td": ["colspan", "rowspan", "width", "valign", "bgcolor"],
    "th": ["colspan", "rowspan", "width", "valign", "bgcolor", "scope"],
    "col": ["span", "width"], "colgroup": ["span", "width"],
    "font": ["color", "face", "size"], "ol": ["start", "type"], "li": ["value"],
    "details": ["open"],
}
# No backgrounds/images, positioning, hiding, animation, generated content or
# custom properties. Keep typography and table layout useful for financial data.
_CSS_PROPERTIES = frozenset("""
    color background-color font-family font-size font-style font-weight
    font-variant line-height letter-spacing word-spacing text-align text-indent
    text-decoration text-transform vertical-align white-space overflow-wrap
    word-break border border-top border-right border-bottom border-left
    border-color border-style border-width border-top-color border-top-style
    border-top-width border-bottom-color border-bottom-style border-bottom-width
    border-left-color border-left-style border-left-width border-right-color
    border-right-style border-right-width border-collapse border-spacing
    table-layout caption-side empty-cells width min-width max-width
    margin margin-top margin-right margin-bottom margin-left
    padding padding-top padding-right padding-bottom padding-left
    list-style-type list-style-position
""".split())
_CSS_FUNCTIONS = {"rgb", "rgba", "hsl", "hsla", "calc", "min", "max", "clamp"}
_CSP = (
    "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; "
    "form-action 'none'; base-uri 'none'"
)
_BASE_STYLE = """
    html { color-scheme: light; }
    body { margin: 16px; color: #202124; background: white;
           font: 16px/1.45 Georgia, serif; overflow-wrap: break-word; }
    table { border-collapse: collapse; } td, th { padding: 2px 4px; }
    pre { white-space: pre-wrap; } a { color: inherit; }
"""


def initial_attachment(documents: Sequence[SourceDocument]) -> str:
    """Prefer the earnings release, retaining manifest order for other choices."""
    return next(
        (doc.artifact_id for doc in documents
         if (doc.document_type or "").strip().upper() == "EX-99.1"),
        documents[0].artifact_id,
    )


def _safe_css_value(tokens) -> bool:
    for token in tokens:
        if token.type in {"url", "error", "at-keyword"}:
            return False
        if token.type == "function":
            if token.lower_name not in _CSS_FUNCTIONS or not _safe_css_value(token.arguments):
                return False
        if token.type in {"() block", "[] block", "{} block"}:
            return False
    return True


class _InlineStyle:
    def sanitize_css(self, style: str) -> str:
        import tinycss2

        declarations = tinycss2.parse_declaration_list(style, skip_comments=True, skip_whitespace=True)
        return tinycss2.serialize([
            item for item in declarations
            if item.type == "declaration" and item.lower_name in _CSS_PROPERTIES
            and _safe_css_value(item.value)
        ])


def _document_body(raw: bytes):
    import html5lib

    # Parsing bytes respects BOM/HTML encoding declarations. UTF-8 is the default
    # for this bundle; legacy declarations still take precedence when present.
    root = html5lib.parse(raw, namespaceHTMLElements=False, default_encoding="utf-8")

    def clean(parent):
        for child in list(parent):
            tag = child.tag.rsplit("}", 1)[-1] if isinstance(child.tag, str) else ""
            if tag in _DROP_CONTENT or not isinstance(child.tag, str):
                # Preserve the following visible text when removing a subtree.
                index = list(parent).index(child)
                if index:
                    previous = parent[index - 1]
                    previous.tail = (previous.tail or "") + (child.tail or "")
                else:
                    parent.text = (parent.text or "") + (child.tail or "")
                parent.remove(child)
            elif tag == "img":
                alt = child.attrib.get("alt", "").strip()
                child.tag = "span"
                child.attrib.clear()
                child.text = f" [Image: {alt}] " if alt else ""
            else:
                clean(child)

    clean(root)
    return root.find("body")


def sanitized_html(raw: bytes) -> str:
    """Return a complete inert HTML derivative, preserving safe inline styling."""
    import bleach
    import html5lib

    body = _document_body(raw)
    serialized = html5lib.serialize(body, omit_optional_tags=False, quote_attr_values="always")
    # A fresh cleaner per call avoids sharing its stateful parser across sessions.
    content = bleach.Cleaner(
        tags=_TAGS, attributes=_ATTRIBUTES, protocols=[], strip=True,
        strip_comments=True, css_sanitizer=_InlineStyle(),
    ).clean(serialized)
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f'<meta http-equiv="Content-Security-Policy" content="{escape(_CSP, quote=True)}">'
        f'<style>{_BASE_STYLE}</style></head><body>{content}</body></html>'
    )


def viewer_frame(raw: bytes) -> str:
    """Trusted outer markup; source content is escaped inside a locked srcdoc."""
    return (
        '<iframe title="Filing document (display only)" sandbox="" '
        'referrerpolicy="no-referrer" style="width:100%;height:680px;border:0" '
        f'srcdoc="{escape(sanitized_html(raw), quote=True)}"></iframe>'
    )


def plain_text_preview(raw: bytes) -> str:
    """Readable fallback from originals; no precomputed review text is required."""
    body = _document_body(raw)
    parts: list[str] = []
    blocks = {"p", "div", "tr", "br", "hr", "section", "li", "pre", "h1", "h2", "h3", "h4"}

    def walk(element):
        start = len(parts)
        if element.tag in blocks:
            parts.append("\n")
        if element.text:
            parts.append(element.text)
        for child in element:
            walk(child)
            if child.tail:
                parts.append(child.tail)
        if element.tag in {"td", "th"}:
            if any(part.strip() for part in parts[start:]):
                parts.append(" | ")
        elif element.tag in blocks:
            parts.append("\n")

    walk(body)
    return "\n".join(" ".join(line.split()) for line in "".join(parts).splitlines() if line.strip())
