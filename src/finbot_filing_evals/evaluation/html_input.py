"""Compact model-facing HTML that preserves visible text and table structure.

This is input preparation, not a browser renderer or an EPS extractor. It never
fetches resources, interprets fiscal periods, or rewrites financial values.
"""

from html import escape
import re
from urllib.parse import unquote, urlsplit


KEEP = frozenset('''
    article section main div p h1 h2 h3 h4 h5 h6 table caption colgroup col
    thead tbody tfoot tr th td ul ol li dl dt dd blockquote pre code br hr
    sup sub strong b em i del ins s figure figcaption details summary
'''.split())
DROP = frozenset({
    'head', 'script', 'style', 'template', 'nav', 'ix:header', 'ix:hidden',
    'xbrli:context', 'xbrli:unit',
})
TABLE = frozenset({'table', 'caption', 'colgroup', 'col', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td'})
BLOCK = KEEP - {'sup', 'sub', 'strong', 'b', 'em', 'i', 'del', 'ins', 's', 'code'}
VOID = frozenset({'br', 'hr', 'col'})
SPACE = re.compile(r'[\t\n\r\f ]+')
HIDDEN_STYLE = re.compile(
    r'(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*(?:hidden|collapse))'
    r'\s*(?:!important\s*)?(?:;|$)', re.I,
)


def hidden(element):
    style = re.sub(r'/\*.*?\*/', '', element.get('style', ''), flags=re.S)
    return 'hidden' in element.attrib or HIDDEN_STYLE.search(style) is not None


def attributes(element, tag):
    """Retain semantic table/list attributes, without style or URL payloads."""
    values = {name: element.get(name) for name in ('title', 'aria-label') if element.get(name)}
    if tag in {'td', 'th'}:
        for name in ('rowspan', 'colspan'):
            value = element.get(name, '')
            if re.fullmatch(r'[0-9]+', value):
                values[name] = value
        for name in ('id', 'headers', 'abbr'):
            if element.get(name):
                values[name] = element.get(name)
        if element.get('scope') in {'row', 'col', 'rowgroup', 'colgroup'}:
            values['scope'] = element.get('scope')
    if tag in {'col', 'colgroup'} and re.fullmatch(r'[0-9]+', element.get('span', '')):
        values['span'] = element.get('span')
    if tag == 'table' and element.get('summary'):
        values['summary'] = element.get('summary')
    for tag_name, attribute in (('ol', 'start'), ('li', 'value')):
        if tag == tag_name and re.fullmatch(r'-?[0-9]+', element.get(attribute, '')):
            values[attribute] = element.get(attribute)
    return ''.join(f' {name}="{escape(value, quote=True)}"' for name, value in sorted(values.items()))


def cleaned_html(raw):
    import html5lib

    # Match the existing text helper's encoding handling, including legacy HTML
    # declarations. The parser is tolerant of imperfect SEC financial markup.
    root = html5lib.parse(raw, namespaceHTMLElements=False, default_encoding='utf-8')

    def text(value, preserve_space):
        value = value or ''
        return escape(value if preserve_space else SPACE.sub(' ', value), quote=False)

    def render(element, preserve_space=False):
        if not isinstance(element.tag, str):
            return ''  # Comments have no visible text; the caller keeps the tail.
        tag = element.tag.rsplit('}', 1)[-1].lower()
        if tag in DROP or hidden(element):
            return ''
        if tag == 'img':
            # Retain attachment references/alt text, never inline data URLs.
            source = element.get('src', '')
            try:
                filename = unquote(urlsplit(source).path.rsplit('/', 1)[-1]) if source and not source.lower().startswith('data:') else ''
            except ValueError:
                filename = ''
            label = ' | '.join(part for part in (filename, element.get('alt', '').strip()) if part)
            return f'<img alt="{escape(label, quote=True)}">' if label else ''
        preserve_space = preserve_space or tag == 'pre'
        pieces = [text(element.text, preserve_space)]
        for child in element:
            pieces.extend((render(child, preserve_space), text(child.tail, preserve_space)))
        content = ''.join(pieces)
        if tag not in KEEP:
            # Font/span/link and visible inline-XBRL wrappers are removed, while
            # text fragments remain in order (including split decimal amounts).
            return content
        # Empty cells/rows are retained: removing them changes header alignment.
        if not content.strip() and tag not in TABLE | VOID:
            return ''
        opening = f'<{tag}{attributes(element, tag)}>'
        result = opening if tag in VOID else opening + content + f'</{tag}>'
        return '\n' + result + '\n' if tag in BLOCK and not preserve_space else result

    content = render(root).strip()
    return '<html><body>\n' + content + '\n</body></html>'
