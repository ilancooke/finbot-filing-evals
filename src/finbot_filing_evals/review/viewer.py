"""Display-only derivatives of original HTML; never fetch or rewrite source files.

HTML5 parsing and allowlist sanitization are followed by a restrictive CSP and
an iframe with no sandbox permissions. Only the generated wrapper is embedded
in Streamlit's component frame, which itself permits scripts by default.
"""

from collections.abc import Sequence
from html import escape
from base64 import b64encode
from io import BytesIO

from .dataset import SourceDocument

_TAGS = frozenset("""
    a abbr b bdi bdo blockquote br caption center cite code col colgroup dd del
    details div dl dt em figcaption figure font h1 h2 h3 h4 h5 h6 hr i ins kbd
    li main mark ol p pre q s samp section small span strike strong sub summary
    sup table tbody td tfoot th thead tr tt u ul var wbr img
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
    "img": ["src", "alt", "width", "height"],
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
    "form-action 'none'; base-uri 'none'; img-src data:"
)
_BASE_STYLE = """
    html { color-scheme: light; }
    body { margin: 16px; color: #202124; background: white;
           font: 16px/1.45 Georgia, serif; overflow-wrap: break-word; }
    table { border-collapse: collapse; } td, th { padding: 2px 4px; }
    pre { white-space: pre-wrap; } a { color: inherit; }
    img { max-width: 100%; height: auto; }
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


def _document_body(raw: bytes, images=None):
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
                source = child.attrib.get("src", "")
                local = (images or {}).get(source)
                child.attrib.clear()
                if local is not None:
                    child.attrib.update(src=local, alt=alt or "Collected filing page or graphic")
                else:
                    child.tag = "span"
                    child.attrib["data-missing-image"] = "true"
                    child.text = f" [Image: {alt}] " if alt else ""
            else:
                clean(child)

    clean(root)
    return root.find("body")


def _enlarge_embedded_text(body) -> bool:
    """Reveal tiny image-page transcripts without overriding ordinary typography."""
    import tinycss2

    enlarged = False
    page_image_available = False
    for element in body.iter():
        if element.tag == "img":
            page_image_available = True
        elif element.tag == "hr" or element.attrib.get("data-missing-image"):
            page_image_available = False
        declarations = tinycss2.parse_declaration_list(
            element.attrib.get("style", ""), skip_comments=True, skip_whitespace=True,
        )
        sizes = [item for item in declarations
                 if item.type == "declaration" and item.lower_name == "font-size"]
        if not sizes:
            continue
        # The last declaration at the highest importance wins in inline CSS.
        size = sorted(sizes, key=lambda item: item.important)[-1]
        tokens = [token for token in size.value if token.type != "whitespace"]
        if len(tokens) != 1:
            continue
        token = tokens[0]
        pixels = None
        if token.type == "dimension":
            if token.lower_unit == "px":
                pixels = token.value
            elif token.lower_unit == "pt":
                pixels = token.value * 4 / 3
        elif token.type == "number" and token.value == 0:
            pixels = 0
        if pixels is None or not 0 <= pixels <= 2 or not "".join(element.itertext()).strip():
            continue
        if page_image_available:
            continue  # Keep a collected page's hidden transcription unobtrusive.
        # Image-backed filings can include a white 1pt transcript. The images
        # are unavailable, so expose that text on the viewer's white background.
        element.attrib.pop("size", None)
        element.attrib["style"] = tinycss2.serialize([
            item for item in declarations
            if item.type == "declaration" and item.lower_name not in {
                "font-size", "color", "background-color", "line-height",
            }
        ]) + "font-size:16px!important;color:#202124!important;background-color:white!important;line-height:1.45!important;"
        enlarged = True
    return enlarged


def _image_data(images):
    """Only verified manifest bytes become image URLs; source URLs never survive."""
    from PIL import Image
    from .errors import ReviewError
    import warnings

    bodies = set(images.values())
    if len(bodies) > 128 or sum(map(len, bodies)) > 64 * 1024 * 1024:
        raise ReviewError("Collected images exceed the viewer's count or byte limit.")
    result, encoded = {}, {}
    for source, body in images.items():
        if body in encoded:
            result[source] = encoded[body]
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(body)) as picture:
                    format = picture.format.lower()
                    if (format not in {"jpeg", "png", "gif"} or max(picture.size) > 8000
                            or len(body) > 8 * 1024 * 1024 or getattr(picture, "n_frames", 1) != 1):
                        raise ValueError("unsupported or oversized raster")
                    picture.verify()
            result[source] = f"data:image/{format};base64,{b64encode(body).decode('ascii')}"
            encoded[body] = result[source]
        except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ReviewError("A collected supporting image is invalid or exceeds viewer limits.") from exc
    return result


def case_images(case):
    """Read only hash-verified assets listed in this filing's manifest."""
    from urllib.parse import quote
    from .errors import ReviewError

    filing = case.to_dict()["filing"]
    prefix = f"https://www.sec.gov/Archives/edgar/data/{int(filing['cik'])}/{case.filing_id.replace('-', '')}/"
    images = {}
    assets = [doc for doc in case.documents if doc.filename.lower().endswith((".jpg", ".jpeg", ".png", ".gif"))]
    if len(assets) > 128 or sum(doc.size_bytes for doc in assets) > 64 * 1024 * 1024:
        raise ReviewError("Collected images exceed the viewer's count or byte limit.")
    for doc in assets:
        if doc.filename.lower().endswith((".jpg", ".jpeg", ".png", ".gif")):
            body = doc.read_bytes()
            # Resolve relative and canonical same-accession references only;
            # arbitrary URLs sharing a basename can never select an asset.
            encoded_name = quote(doc.filename, safe="._-")
            for source in (doc.filename, "./" + doc.filename, encoded_name,
                           "./" + encoded_name, prefix + encoded_name):
                images[source] = body
    return images


def sanitized_html(raw: bytes, *, images=None) -> str:
    """Return a complete inert HTML derivative, preserving safe inline styling."""
    import bleach
    import html5lib

    body = _document_body(raw, _image_data(images or {}))
    enlarged = _enlarge_embedded_text(body)
    serialized = html5lib.serialize(body, omit_optional_tags=False, quote_attr_values="always")
    # A fresh cleaner per call avoids sharing its stateful parser across sessions.
    content = bleach.Cleaner(
        tags=_TAGS, attributes=_ATTRIBUTES, protocols=["data"], strip=True,
        strip_comments=True, css_sanitizer=_InlineStyle(),
    ).clean(serialized)
    notice = (
        '<p role="note">Very small embedded text has been enlarged for reading. '
        'Missing page images can prevent the original table layout from being reproduced.</p>'
        if enlarged else ""
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f'<meta http-equiv="Content-Security-Policy" content="{escape(_CSP, quote=True)}">'
        f'<style>{_BASE_STYLE}</style></head><body>{notice}{content}</body></html>'
    )


def viewer_frame(raw: bytes, *, images=None) -> str:
    """Trusted outer markup; source content is escaped inside a locked srcdoc."""
    return (
        '<iframe title="Filing document (display only)" sandbox="" '
        'referrerpolicy="no-referrer" style="width:100%;height:680px;border:0" '
        f'srcdoc="{escape(sanitized_html(raw, images=images), quote=True)}"></iframe>'
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
