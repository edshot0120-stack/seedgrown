"""Root Crawl for web pages: the page's outline instead of its HTML.

A page's HTML is mostly menus, scripts, styles and repeated chrome; its visible text still
carries every menu and footer. The outline keeps what an AI usually needs to decide where to
look — title, headings with each section's opening, tables (header + a few rows), forms (their
fields), and the links that lead somewhere — and the rest is taken on request:

    rootweb.py outline URL|FILE.html [--budget 1500]
    rootweb.py section URL|FILE.html "heading text"     # one section in full
    rootweb.py find URL|FILE.html "words" [--around 200]  # where the words appear
    rootweb.py links URL|FILE.html [--match text] [--limit 40]

Pages are cached for an hour in the Root Crawl cache folder. Standard library only.
"""
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from html.parser import HTMLParser

DROP = {'script', 'style', 'noscript', 'svg', 'template', 'iframe', 'canvas', 'button', 'select', 'option'}
CHROME = {'nav', 'footer', 'header', 'aside'}
BLOCK = {'p', 'li', 'dd', 'dt', 'blockquote', 'pre', 'figcaption', 'caption', 'summary', 'td', 'th', 'div', 'section', 'article', 'main', 'br', 'tr'}
HEAD = {'h1': 1, 'h2': 2, 'h3': 3, 'h4': 4, 'h5': 5, 'h6': 6}
# a class / id token that names page chrome as a whole word (not "sticky-header-enabled")
CHROME_TOKEN = re.compile(r'^(site-|page-|main-|global-|top-|primary-)?(nav|navbar|navigation|menu|menubar|footer|header|masthead|sidebar|side-bar|breadcrumbs?|cookie-?(banner|consent|notice)?|ads?|advert(isement)?s?|promo|social|share|sharing|newsletter|related(-posts)?|comments?)$', re.I)
NEVER_CHROME = {'html', 'body', 'main', 'article'}


def is_chrome_attr(a):
    if a.get('role') in ('navigation', 'banner', 'contentinfo', 'complementary'):
        return True
    tokens = ((a.get('class') or '') + ' ' + (a.get('id') or '')).split()
    return any(CHROME_TOKEN.match(t) for t in tokens)


def cache_file(key):
    base = os.environ.get('ROOTCRAWL_CACHE') or os.path.join(
        os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_CACHE_HOME') or os.path.join(os.path.expanduser('~'), '.cache'), 'rootcrawl')
    os.makedirs(os.path.join(base, 'web'), exist_ok=True)
    return os.path.join(base, 'web', hashlib.blake2b(key.encode(), digest_size=12).hexdigest() + '.html')


def fetch(src, max_age=3600):
    """HTML of a URL (cached) or a local file; returns (html, base_url)."""
    if os.path.exists(src):
        return open(src, encoding='utf-8', errors='replace').read(), src
    path = cache_file(src)
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age:
        return open(path, encoding='utf-8', errors='replace').read(), src
    req = urllib.request.Request(src, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en,ko;q=0.8'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read(8 * 1024 * 1024)
            enc = r.headers.get_content_charset() or 'utf-8'
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429, 503):
            raise OSError(f'the site refused a direct request (HTTP {e.code}); read it with a browser tool, '
                          f'or save the page as .html and run this on the file') from None
        raise
    text = raw.decode(enc, errors='replace')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return text, src


class Page(HTMLParser):
    """Blocks of text with their heading path; tables, forms and links on the side."""

    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.title = ''
        self.blocks = []  # (kind, level/None, text, in_main, in_chrome)
        self.links = []  # (text, href, in_chrome)
        self.tables, self.forms = [], []
        self.stack = []
        self.buf = []
        self.drop = 0
        self.chrome = 0
        self.main = 0
        self.has_main = False
        self.cur_link = None
        self.table = None
        self.row = None
        self.cell = None
        self.form = None
        self.in_title = False

    def _flush(self, kind='text', level=None):
        t = re.sub(r'\s+', ' ', ''.join(self.buf)).strip()
        self.buf = []
        t = t.replace('¶', '').strip()
        if t:
            self.blocks.append((kind, level, t, self.main > 0, self.chrome > 0))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('br', 'img', 'input', 'meta', 'link', 'hr', 'source', 'wbr'):
            if tag == 'input' and self.form is not None and a.get('type', 'text') not in ('hidden', 'submit'):
                self.form['fields'].append(a.get('name') or a.get('placeholder') or a.get('aria-label') or a.get('type', 'text'))
            if tag == 'img' and self.drop == 0 and a.get('alt') and self.cur_link is not None:
                self.cur_link['text'] += ' ' + a['alt']
            return
        self.stack.append(tag)
        is_chrome = tag not in NEVER_CHROME and (tag in CHROME or is_chrome_attr(a) or a.get('aria-hidden') == 'true')
        if tag in DROP or a.get('hidden') is not None:
            self.drop += 1
        if is_chrome:
            self.chrome += 1
        if tag in ('main', 'article') or a.get('role') == 'main':
            self.main += 1
            self.has_main = True
        self._marks = getattr(self, '_marks', [])
        self._marks.append((tag in DROP or a.get('hidden') is not None, is_chrome, tag in ('main', 'article') or a.get('role') == 'main'))
        if tag == 'title':
            self.in_title = True
        if self.drop:
            return
        if tag in HEAD or tag in BLOCK:
            self._flush()
        if tag == 'a' and a.get('href') and not a['href'].startswith(('javascript:', '#')):
            self.cur_link = {'text': '', 'href': urllib.parse.urljoin(self.base, a['href']) if self.base.startswith('http') else a['href'], 'chrome': self.chrome > 0}
        if tag == 'table':
            self.table = {'rows': [], 'caption': ''}
        if tag == 'tr' and self.table is not None:
            self.row = []
        if tag in ('td', 'th') and self.row is not None:
            self.cell = []
        if tag == 'form':
            self.form = {'action': a.get('action', ''), 'fields': []}
        if tag == 'textarea' and self.form is not None:
            self.form['fields'].append(a.get('name') or 'textarea')

    def handle_endtag(self, tag):
        if tag not in self.stack:
            return
        while self.stack:
            t = self.stack.pop()
            dropped, chrome, main = self._marks.pop()
            if not self.drop or dropped:
                if t in HEAD and not (self.drop - dropped):
                    self._flush('h', HEAD[t])
                elif (t in BLOCK) and not self.drop:
                    self._flush()
                if t == 'a' and self.cur_link is not None:
                    txt = re.sub(r'\s+', ' ', self.cur_link['text']).strip()
                    if txt:
                        self.links.append((txt, self.cur_link['href'], self.cur_link['chrome']))
                    self.cur_link = None
                if t in ('td', 'th') and self.cell is not None and self.row is not None:
                    self.row.append(re.sub(r'\s+', ' ', ''.join(self.cell)).strip())
                    self.cell = None
                if t == 'tr' and self.row is not None and self.table is not None:
                    if any(self.row):
                        self.table['rows'].append(self.row)
                    self.row = None
                if t == 'table' and self.table is not None:
                    if len(self.table['rows']) >= 2:
                        self.tables.append(self.table)
                    self.table = None
                if t == 'form' and self.form is not None:
                    if self.form['fields']:
                        self.forms.append(self.form)
                    self.form = None
                if t == 'title':
                    self.in_title = False
            if dropped:
                self.drop -= 1
            if chrome:
                self.chrome -= 1
            if main:
                self.main -= 1
            if t == tag:
                break

    def handle_data(self, d):
        if self.in_title:
            self.title += d
        if self.drop:
            return
        self.buf.append(d)
        if self.cur_link is not None:
            self.cur_link['text'] += d
        if self.cell is not None:
            self.cell.append(d)

    def close(self):
        super().close()
        self._flush()


def parse(src):
    text, base = fetch(src)
    p = Page(base if base.startswith('http') else '')
    p.feed(text)
    p.close()
    return p, text


def content(p):
    """Blocks of the page's content: inside main/article when the page marks one, never chrome."""
    use_main = p.has_main and any(b[3] for b in p.blocks if b[0] == 'h' or len(b[2]) > 40)
    return [b for b in p.blocks if not b[4] and (b[3] or not use_main)]


def short(s, n):
    return s if len(s) <= n else s[: n - 1].rstrip() + '…'


def outline(src, budget):
    p, raw = parse(src)
    blocks = content(p)
    visible = sum(len(b[2]) for b in p.blocks)
    out = [f'# {short(html.unescape(p.title.strip()), 120) or src}', f'{src}']
    words = sum(len(b[2].split()) for b in blocks)
    out.append(f'{words:,} words of content · {len([b for b in blocks if b[0] == "h"])} headings · {len(p.tables)} tables · {len(p.forms)} forms · {len(p.links)} links\n')
    # headings with each section's opening
    out.append('## Outline')
    pending = None
    first_seen = False
    for kind, level, t, _, _ in blocks:
        if kind == 'h':
            if pending:
                out.append(pending)
            pending = None
            out.append(f'{"  " * (max(level, 1) - 1)}- {short(t, 100)}')
            first_seen = True
            pending_level = level
            pending = ''
        elif pending == '' and len(t) > 30:
            pending = f'{"  " * max(pending_level, 1)}{short(t, 160)}'
        elif not first_seen and len(t) > 60:
            out.append(f'  {short(t, 200)}')
            first_seen = True
    if pending:
        out.append(pending)
    for i, tb in enumerate(p.tables[:6]):
        rows = tb['rows']
        ncol = max(len(r) for r in rows)
        width = 70 if ncol <= 3 else 24  # list-like tables (a ranking, a feed) keep their titles
        out.append(f'\n## Table {i + 1}: {len(rows)} rows × {ncol} cols')
        for r in rows[:6 if ncol <= 3 else 4]:
            out.append('| ' + ' | '.join(short(c, width) for c in r[:8] if c or ncol > 3) + ' |')
    seen_forms = set()
    for f in p.forms[:6]:
        key = (f['action'], tuple(f['fields']))
        if key in seen_forms:
            continue
        seen_forms.add(key)
        out.append(f'\n## Form → {short(f["action"] or "(this page)", 60)}: fields {", ".join(short(x, 20) for x in f["fields"][:12])}')
    body = [l for l in p.links if not l[2]]
    seen, keep = set(), []
    for t, h, _ in body:
        if h in seen or len(t) < 3:
            continue
        seen.add(h)
        keep.append((t, h))
    if keep:
        out.append(f'\n## Links in the content: {len(keep)} (first 15; `links` for more)')
        for t, h in keep[:15]:
            out.append(f'- {short(t, 60)} → {short(h, 90)}')
    text = '\n'.join(out)
    if len(text) // 4 > budget:
        text = text[: budget * 4] + '\n… (cut to the budget: `section` / `find` for detail)'
    text += f'\n\n_Outline ≈ {len(text) // 4:,} tokens · page text ≈ {visible // 4:,} · HTML ≈ {len(raw) // 4:,}_'
    return text


def section(src, heading):
    p, _ = parse(src)
    blocks = content(p) or p.blocks
    out, level = [], None
    for kind, lv, t, _, _ in blocks:
        if kind == 'h':
            if level is not None and lv <= level:
                break
            if level is None and heading.lower() in t.lower():
                level = lv
                out.append(f'## {t}')
                continue
        if level is not None:
            out.append(t if kind != 'h' else f'{"#" * (lv + 1)} {t}')
    return '\n'.join(out) if out else f'(no heading containing "{heading}")'


def find(src, words, around):
    p, _ = parse(src)
    blocks = content(p) or p.blocks
    head, hits = '', []
    for kind, lv, t, _, _ in blocks:
        if kind == 'h':
            head = t
        low, w = t.lower(), words.lower()
        i = low.find(w)
        while i >= 0:  # every occurrence in the block, not just the first
            hits.append(f'[{short(head, 50)}] …{t[max(0, i - around): i + len(words) + around]}…')
            i = low.find(w, i + len(w))
    return '\n'.join(hits[:12]) + f'\n# {len(hits)} matches' if hits else f'# no match for "{words}"'


def links(src, match, limit):
    p, _ = parse(src)
    seen, out = set(), []
    for t, h, chrome in p.links:
        if h in seen:
            continue
        seen.add(h)
        if match and match.lower() not in (t + ' ' + h).lower():
            continue
        out.append(f'{"·" if chrome else "-"} {short(t, 70)} → {h}')
    return '\n'.join(out[:limit]) + f'\n# {len(out)} links ({"·" if True else ""} = menu / footer)'



def unmangle(argv):
    """Undo Git Bash's path conversion of arguments that began with "/" (MSYS on Windows)."""
    if os.name != 'nt':
        return argv
    out = []
    for a in argv:
        m = re.match(r'^[A-Za-z]:[/\\](?:Program Files[/\\]Git|msys64|usr)([/\\].*)$', a)
        out.append(m.group(1).replace('\\', '/') if m and not os.path.exists(a) else a)
    return out

def main(argv=None):
    import argparse
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description='Root Crawl for web pages')
    sp = ap.add_subparsers(dest='cmd', required=True)
    o = sp.add_parser('outline')
    o.add_argument('src')
    o.add_argument('--budget', type=int, default=1500)
    s = sp.add_parser('section')
    s.add_argument('src')
    s.add_argument('heading')
    f = sp.add_parser('find')
    f.add_argument('src')
    f.add_argument('words')
    f.add_argument('--around', type=int, default=160)
    l = sp.add_parser('links')
    l.add_argument('src')
    l.add_argument('--match')
    l.add_argument('--limit', type=int, default=40)
    a = ap.parse_args(unmangle(sys.argv[1:] if argv is None else argv))
    try:
        if a.cmd == 'outline':
            text = outline(a.src, a.budget)
        elif a.cmd == 'section':
            text = section(a.src, a.heading)
        elif a.cmd == 'find':
            text = find(a.src, a.words, a.around)
        else:
            text = links(a.src, a.match, a.limit)
        print(text)
        try:
            import savings
            p, _ = parse(a.src)
            page_text = sum(len(b[2]) for b in p.blocks) // 4
            savings.record('web ' + a.cmd, a.src, len(text) // 4, max(page_text, len(text) // 4))
        except Exception:
            pass
    except (OSError, ValueError) as e:
        sys.exit(f'rootweb: could not read {a.src}: {e}')


if __name__ == '__main__':
    main()
