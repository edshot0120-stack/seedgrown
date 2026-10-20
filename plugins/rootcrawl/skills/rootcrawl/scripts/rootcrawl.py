#!/usr/bin/env python3
"""Root Crawl — read a folder of data once, locally, and hand an AI a short report instead of
the files. Saves tokens: a 10 MB CSV or 3,000 photos become a ~2,000-token profile, and only
the slices that matter are read after that.

    rootcrawl.py profile PATH [--budget 3000] [--refresh]
    rootcrawl.py table FILE [--cols a,b] [--where "col>10"] [--limit 20]
    rootcrawl.py images PATH [--make SONY] [--software Lightroom] [--limit 30]
    rootcrawl.py pairs PATH                 # same-name files in different places / formats
    rootcrawl.py peek FILE [--lines 40]     # the first lines of any text file
    rootcrawl.py web outline URL            # a web page's outline instead of its HTML (rootweb.py)

Standard library only; Pillow (EXIF) and openpyxl (xlsx) are used when installed.
Profiles are cached per file (size + mtime) in the user's cache folder (never inside the data
folder), so a second run is instant and only changed files are read again. Nothing leaves the
machine.
"""
import argparse
import collections
import csv
import hashlib
import io
import json
import os
import re
import statistics
import sys
import time

IMAGE = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp', '.tif', '.tiff', '.bmp', '.gif'}
RAW = {'.arw', '.cr2', '.cr3', '.nef', '.raf', '.dng', '.orf', '.rw2', '.3fr', '.pef', '.srw'}
TABLE = {'.csv', '.tsv'}
JSONS = {'.json', '.jsonl', '.ndjson'}
TEXT = {'.txt', '.md', '.log', '.py', '.js', '.ts', '.dart', '.java', '.kt', '.go', '.rs', '.c', '.h', '.cpp',
        '.cs', '.rb', '.php', '.sh', '.yaml', '.yml', '.toml', '.ini', '.xml', '.html', '.css', '.sql'}
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.rootcrawl', '.venv', 'venv', 'build', '.dart_tool', '.idea'}
CACHE_VERSION = 3


def human(n):
    for u in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or u == 'TB':
            return f'{n:.0f}{u}' if u == 'B' else f'{n:.1f}{u}'
        n /= 1024


def short(s, n=60):
    s = str(s).replace('\n', ' ')
    return s if len(s) <= n else s[: n - 1] + '…'


# --- per-file profilers ---------------------------------------------------------------------------

def sniff_type(v):
    v = v.strip()
    if v == '':
        return 'empty'
    if re.fullmatch(r'[-+]?\d+', v):
        return 'int'
    if re.fullmatch(r'[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?', v):
        return 'float'
    if re.fullmatch(r'\d{4}[-/.]\d{1,2}[-/.]\d{1,2}([ T]\d{1,2}:\d{2}(:\d{2})?)?.*', v):
        return 'date'
    if v.lower() in ('true', 'false', 'yes', 'no'):
        return 'bool'
    return 'str'


def profile_table(path, sample_rows=3, max_rows=200000):
    with open(path, 'r', encoding='utf-8-sig', errors='replace', newline='') as f:
        head = f.read(64 * 1024)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(head, delimiters=',\t;|')
        except csv.Error:
            dialect = csv.excel_tab if path.lower().endswith('.tsv') else csv.excel
        try:
            has_header = csv.Sniffer().has_header(head)
        except csv.Error:
            has_header = True
        r = csv.reader(f, dialect)
        first = next(r, [])
        header = first if has_header else [f'col{i}' for i in range(len(first))]
        cols = [{'name': h or f'col{i}', 'types': collections.Counter(), 'nums': [], 'vals': collections.Counter(), 'empty': 0}
                for i, h in enumerate(header)]
        samples, n = [], 0
        rows = r if has_header else __import__('itertools').chain([first], r)
        for row in rows:
            n += 1
            if len(samples) < sample_rows:
                samples.append(row)
            if n > max_rows:
                continue  # count only
            for c, v in zip(cols, row):
                t = sniff_type(v)
                c['types'][t] += 1
                if t == 'empty':
                    c['empty'] += 1
                elif t in ('int', 'float'):
                    if len(c['nums']) < 50000:
                        c['nums'].append(float(v))
                elif len(c['vals']) < 2000 or v in c['vals']:
                    c['vals'][v] += 1
    out = {'kind': 'table', 'rows': n, 'cols': []}
    for c in cols:
        t = [k for k, _ in c['types'].most_common() if k != 'empty'][:1]
        if c['types']['int'] and c['types']['float']:
            t = ['number']
        d = {'name': c['name'], 'type': t[0] if t else 'empty', 'empty%': round(100 * c['empty'] / max(n, 1), 1)}
        if c['nums']:
            d.update(min=min(c['nums']), max=max(c['nums']), mean=round(statistics.fmean(c['nums']), 4))
        elif c['vals']:
            d['distinct'] = len(c['vals'])
            if len(c['vals']) <= 20 or d['type'] == 'bool':
                d['top'] = [(short(k, 24), v) for k, v in c['vals'].most_common(5)]
            else:
                d['examples'] = [short(k, 24) for k, _ in c['vals'].most_common(3)]
        out['cols'].append(d)
    out['header'] = has_header
    out['sample'] = [[short(v, 24) for v in s] for s in samples]
    return out


def profile_xlsx(path):
    try:
        import openpyxl
    except ImportError:
        return {'kind': 'xlsx', 'note': 'install openpyxl for sheet details'}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets = []
    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        header = next(rows, ())
        first = next(rows, ())
        sheets.append({'sheet': ws.title, 'dims': ws.dimensions, 'header': [short(h, 20) for h in header][:30],
                       'first_row': [short(v, 20) for v in first][:30]})
    return {'kind': 'xlsx', 'sheets': sheets}


def shape_of(x, depth=0):
    if depth > 3:
        return '…'
    if isinstance(x, dict):
        return {k: shape_of(v, depth + 1) for k, v in list(x.items())[:25]}
    if isinstance(x, list):
        return [shape_of(x[0], depth + 1), f'×{len(x)}'] if x else []
    return type(x).__name__


def profile_json(path):
    if path.lower().endswith(('.jsonl', '.ndjson')):
        n, bad, first, keys = 0, 0, None, collections.Counter()
        with open(path, encoding='utf-8', errors='replace') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    bad += 1
                    continue
                n += 1
                first = first or o
                if isinstance(o, dict):
                    keys.update(o.keys())
        return {'kind': 'jsonl', 'records': n, 'bad_lines': bad, 'keys': keys.most_common(25), 'first': shape_of(first)}
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            o = json.load(f)
    except (ValueError, MemoryError) as e:
        return {'kind': 'json', 'error': short(e, 80)}
    return {'kind': 'json', 'shape': shape_of(o)}


TS = re.compile(r'(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})')


def profile_text(path, max_lines=200000):
    n, chars, tss = 0, 0, []
    templates = collections.Counter()
    is_log = path.lower().endswith('.log')
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            n += 1
            chars += len(line)
            if n > max_lines:
                continue
            m = TS.search(line)
            if m:
                tss.append(m.group(1))
            if is_log or m:
                templates[re.sub(r'\d+', '#', re.sub(r'0x[0-9a-fA-F]+|[0-9a-f]{8,}', '<id>', line.strip()))[:90]] += 1
    out = {'kind': 'text', 'lines': n, 'approx_tokens': chars // 4}
    if tss:
        out['time_range'] = [min(tss), max(tss)]
    if templates and (is_log or len(tss) > n * 0.3):
        out['kind'] = 'log'
        out['top_lines'] = templates.most_common(6)
    return out


def profile_image(path):
    d = {'kind': 'image'}
    try:
        from PIL import Image
    except ImportError:
        return d
    try:
        with Image.open(path) as im:
            d['size'] = im.size
            e = im.getexif()
            d['make'] = (e.get(271) or '').strip() or None
            d['model'] = (e.get(272) or '').strip() or None
            d['software'] = (e.get(305) or '').strip() or None
            d['date'] = (e.get(306) or '').strip() or None
    except Exception as x:
        d['error'] = short(x, 60)
    return d


def head_hash(path, n=65536):
    h = hashlib.blake2b(digest_size=12)
    with open(path, 'rb') as f:
        h.update(f.read(n))
    return h.hexdigest()


def profile_file(path, ext):
    if ext in TABLE:
        return profile_table(path)
    if ext == '.xlsx':
        return profile_xlsx(path)
    if ext in JSONS:
        return profile_json(path)
    if ext in IMAGE:
        return profile_image(path)
    if ext in RAW:
        return {'kind': 'raw'}
    if ext in TEXT:
        return profile_text(path)
    return {'kind': 'other'}


# --- folder profile with cache --------------------------------------------------------------------

def walk(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith('.')]
        for f in files:
            if f.startswith('.'):
                continue
            yield os.path.join(d, f)


def cache_path(root):
    """The cache lives in the user's cache folder, keyed by the folder's absolute path: the data
    folder itself is never written to (and read-only folders are cached too)."""
    base = os.environ.get('ROOTCRAWL_CACHE') or os.path.join(
        os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_CACHE_HOME') or os.path.join(os.path.expanduser('~'), '.cache'), 'rootcrawl')
    key = hashlib.blake2b(os.path.abspath(root).encode('utf-8'), digest_size=10).hexdigest()
    return os.path.join(base, key + '.json')


def load_cache(root):
    p = cache_path(root)
    try:
        c = json.load(open(p, encoding='utf-8'))
        return c if c.get('v') == CACHE_VERSION else {'v': CACHE_VERSION, 'files': {}}
    except (OSError, ValueError):
        return {'v': CACHE_VERSION, 'files': {}}


def save_cache(root, cache):
    p = cache_path(root)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        cache['root'] = os.path.abspath(root)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(cache, f)
    except OSError:
        pass  # no writable cache folder: just no cache


def profile_folder(root, refresh=False, per_kind_limit=4000):
    cache = {'v': CACHE_VERSION, 'files': {}} if refresh else load_cache(root)
    files, fresh, t0 = {}, 0, time.time()
    kind_seen = collections.Counter()
    for p in walk(root):
        try:
            st = os.stat(p)
        except OSError:
            continue
        rel = os.path.relpath(p, root)
        ext = os.path.splitext(p)[1].lower()
        sig = f'{st.st_size}:{int(st.st_mtime)}'
        c = cache['files'].get(rel)
        if c and c.get('sig') == sig:
            files[rel] = c
            kind_seen[c['p'].get('kind')] += 1
            continue
        kind = 'image' if ext in IMAGE else ext
        kind_seen[kind] += 1
        # past the limit, many files of one kind are only counted (their totals stay right)
        prof = profile_file(p, ext) if kind_seen[kind] <= per_kind_limit else {'kind': 'image' if ext in IMAGE else 'skipped'}
        files[rel] = {'sig': sig, 'size': st.st_size, 'ext': ext, 'p': prof}
        fresh += 1
    cache['files'] = files
    save_cache(root, cache)
    return files, fresh, time.time() - t0


def report(root, files, fresh, secs, budget):
    out = io.StringIO()
    w = out.write
    total = sum(f['size'] for f in files.values())
    w(f'# Root Crawl: {os.path.abspath(root)}\n')
    w(f'{len(files)} files · {human(total)} · {fresh} read now, {len(files) - fresh} from cache · {secs:.1f}s\n\n')
    # by folder
    by_dir = collections.defaultdict(lambda: [0, 0, collections.Counter()])
    for rel, f in files.items():
        top = rel.split(os.sep)[0] if os.sep in rel else '.'
        by_dir[top][0] += 1
        by_dir[top][1] += f['size']
        by_dir[top][2][f['ext'] or '(none)'] += 1
    w('## Folders\n')
    for d, (n, s, exts) in sorted(by_dir.items(), key=lambda kv: -kv[1][1])[:20]:
        w(f'- {d}/ — {n} files, {human(s)} ({", ".join(f"{e} {c}" for e, c in exts.most_common(4))})\n')
    if len(by_dir) > 20:
        w(f'- … {len(by_dir) - 20} more folders\n')
    # images
    imgs = {r: f for r, f in files.items() if f['p'].get('kind') == 'image'}
    raws = [r for r, f in files.items() if f['p'].get('kind') == 'raw']
    if imgs or raws:
        broken = sum(1 for f in imgs.values() if f['p'].get('error'))
        unread = sum(1 for f in imgs.values() if 'size' not in f['p'] and not f['p'].get('error'))
        w(f'\n## Photos: {len(imgs)} images, {len(raws)} RAW'
          + (f', {broken} unreadable' if broken else '') + '\n')
        if unread:
            w(f'- EXIF read for {len(imgs) - unread - broken}; {unread} more only counted (profile a subfolder for detail)\n')
        ok = [f for f in imgs.values() if 'size' in f['p']]
        cams = collections.Counter(' '.join(x for x in (f['p'].get('make'), f['p'].get('model')) if x) or '(no EXIF)' for f in ok)
        soft = collections.Counter((f['p'].get('software') or '(none)').split(' (')[0] for f in ok)
        sizes = [f['p']['size'] for f in imgs.values() if f['p'].get('size')]
        dates = sorted(f['p']['date'] for f in imgs.values() if f['p'].get('date'))
        w('- cameras: ' + ', '.join(f'{k} {v}' for k, v in cams.most_common(6)) + '\n')
        w('- software: ' + ', '.join(f'{short(k, 30)} {v}' for k, v in soft.most_common(5)) + '\n')
        if sizes:
            mp = sorted(a * b / 1e6 for a, b in sizes)
            w(f'- resolution: {mp[0]:.1f}–{mp[-1]:.1f} MP (median {mp[len(mp) // 2]:.1f})\n')
        if dates:
            w(f'- dates: {dates[0][:10]} → {dates[-1][:10]}\n')
        stems = collections.defaultdict(set)
        for r in list(imgs) + raws:
            stems[re.split(r'[-_ ](edit|편집|copy|\d+x)', os.path.splitext(os.path.basename(r))[0], flags=re.I)[0].upper()].add(os.path.dirname(r) + '|' + os.path.splitext(r)[1].lower())
        multi = sum(1 for v in stems.values() if len(v) > 1)
        if multi:
            w(f'- {multi} names appear in more than one place / format (originals ↔ edits? → `pairs`)\n')
    # tables and structured data
    for kind, title in (('table', 'Tables'), ('xlsx', 'Workbooks'), ('json', 'JSON'), ('jsonl', 'JSON lines'), ('log', 'Logs')):
        group = sorted(((r, f) for r, f in files.items() if f['p'].get('kind') == kind), key=lambda rf: -rf[1]['size'])
        if not group:
            continue
        w(f'\n## {title}: {len(group)}\n')
        for r, f in group[:8]:
            p = f['p']
            if kind == 'table':
                w(f'### {r} — {p["rows"]} rows × {len(p["cols"])} cols, {human(f["size"])}\n')
                for c in p['cols'][:30]:
                    extra = ''
                    if 'min' in c:
                        extra = f' {c["min"]:g}…{c["max"]:g} (mean {c["mean"]:g})'
                    elif 'top' in c:
                        extra = ' ' + ', '.join(f'{k}×{v}' for k, v in c['top'])
                    elif 'examples' in c:
                        extra = f' {c["distinct"]} distinct, e.g. ' + ', '.join(c['examples'])
                    empty = f', {c["empty%"]}% empty' if c['empty%'] else ''
                    w(f'- {c["name"]}: {c["type"]}{empty}{extra}\n')
                if len(p['cols']) > 30:
                    w(f'- … {len(p["cols"]) - 30} more columns\n')
                if p.get('sample'):
                    w('- sample: ' + ' | '.join(', '.join(s) for s in p['sample'][:2]) + '\n')
            elif kind == 'xlsx':
                for s in p.get('sheets', [])[:5]:
                    w(f'### {r} › {s["sheet"]} ({s["dims"]})\n- header: {", ".join(map(str, s["header"]))}\n')
            elif kind in ('json', 'jsonl'):
                shape = p.get('shape') or p.get('first')
                w(f'### {r} — {human(f["size"])}' + (f', {p["records"]} records' if 'records' in p else '')
                  + (f', {p["bad_lines"]} unparsable lines' if p.get('bad_lines') else '') + '\n')
                if p.get('error'):
                    w(f'- not valid JSON: {p["error"]}\n')
                else:
                    w('- shape: ' + short(json.dumps(shape, ensure_ascii=False), 400) + '\n')
            else:
                w(f'### {r} — {p["lines"]} lines' + (f', {p["time_range"][0]} → {p["time_range"][1]}' if p.get('time_range') else '') + '\n')
                for t, c in p.get('top_lines', [])[:5]:
                    w(f'- ×{c} {t}\n')
        if len(group) > 8:
            w(f'- … {len(group) - 8} more\n')
    # text / code
    texts = [(r, f) for r, f in files.items() if f['p'].get('kind') == 'text']
    if texts:
        tok = sum(f['p'].get('approx_tokens', 0) for _, f in texts)
        w(f'\n## Text and code: {len(texts)} files, ~{tok:,} tokens to read them all\n')
        for r, f in sorted(texts, key=lambda rf: -rf[1]['size'])[:10]:
            w(f'- {r} — {f["p"]["lines"]} lines (~{f["p"]["approx_tokens"]:,} tokens)\n')
    # what reading it all would cost: text at ~4 bytes a token, each image ~1,600 tokens to look at
    raw_tokens = sum(f['size'] // 4 for f in files.values() if f['p'].get('kind') in ('table', 'json', 'jsonl', 'text', 'log', 'xlsx'))         + 1600 * sum(1 for f in files.values() if f['p'].get('kind') == 'image')
    text = out.getvalue()
    if len(text) // 4 > budget:
        text = text[: budget * 4] + '\n… (report cut to the budget: raise --budget or profile a subfolder)\n'
    text += f'\n_Report ≈ {len(text) // 4:,} tokens; reading the files directly ≈ {raw_tokens:,} tokens._\n'
    return text


# --- slices ---------------------------------------------------------------------------------------

OPS = {'>=': lambda a, b: a >= b, '<=': lambda a, b: a <= b, '!=': lambda a, b: a != b, '=': lambda a, b: a == b,
       '>': lambda a, b: a > b, '<': lambda a, b: a < b, '~': lambda a, b: str(b).lower() in str(a).lower()}


def parse_where(expr):
    conds = []
    for part in [p.strip() for p in (expr or '').split(' and ') if p.strip()]:
        for op in ('>=', '<=', '!=', '=', '>', '<', '~'):
            if op in part:
                col, val = part.split(op, 1)
                conds.append((col.strip(), op, val.strip().strip('"\'')))
                break
    return conds


def cmp_val(v, target):
    try:
        return float(v), float(target)
    except ValueError:
        return v, target


def cmd_table(a):
    conds = parse_where(a.where)
    with open(a.file, encoding='utf-8-sig', errors='replace', newline='') as f:
        try:
            dialect = csv.Sniffer().sniff(f.read(65536), delimiters=',\t;|')
        except csv.Error:
            dialect = csv.excel
        f.seek(0)
        head = f.read(65536)
        f.seek(0)
        try:
            has_header = csv.Sniffer().has_header(head)
        except csv.Error:
            has_header = True
        names = None
        if not has_header:
            names = [f'col{i}' for i in range(len(next(csv.reader(io.StringIO(head), dialect), [])))]
        r = csv.DictReader(f, fieldnames=names, dialect=dialect)
        cols = [c.strip() for c in a.cols.split(',')] if a.cols else r.fieldnames
        known = set(r.fieldnames or [])
        unknown = [c for c in cols + [c for c, _, _ in conds] if c not in known]
        if unknown:
            print(f'# unknown columns: {", ".join(dict.fromkeys(unknown))} (columns are: {", ".join(r.fieldnames or [])})')
            return
        wr = csv.writer(sys.stdout)
        wr.writerow(cols)
        shown = matched = 0
        for row in r:
            ok = True
            for col, op, val in conds:
                x, y = cmp_val(row.get(col, ''), val)
                try:
                    ok = OPS[op](x, y)
                except TypeError:
                    ok = OPS[op](str(x), str(y))
                if not ok:
                    break
            if ok:
                matched += 1
                if shown < a.limit:
                    wr.writerow([short(row.get(c, ''), 80) for c in cols])
                    shown += 1
        print(f'# {matched} matching rows, {shown} shown')


def cmd_images(a):
    files, _, _ = profile_folder(a.path)
    n = 0
    for r, f in sorted(files.items()):
        p = f['p']
        if p.get('kind') != 'image':
            continue
        if a.make and a.make.lower() not in f'{p.get("make")} {p.get("model")}'.lower():
            continue
        if a.software and a.software.lower() not in str(p.get('software')).lower():
            continue
        n += 1
        if n <= a.limit:
            print(f'{r}\t{p.get("size")}\t{p.get("make")} {p.get("model")}\t{p.get("software")}\t{p.get("date")}')
    print(f'# {n} matching images, {min(n, a.limit)} shown')


def cmd_pairs(a):
    files, _, _ = profile_folder(a.path)
    stems = collections.defaultdict(list)
    for r in files:
        if files[r]['p'].get('kind') in ('image', 'raw'):
            stem = re.split(r'[-_ ](edit|편집|copy)', os.path.splitext(os.path.basename(r))[0], flags=re.I)[0].upper()
            stems[stem].append(r)
    groups = [v for v in stems.values() if len(v) > 1]
    for g in groups[: a.limit]:
        print(' ↔ '.join(sorted(g)))
    print(f'# {len(groups)} groups, {min(len(groups), a.limit)} shown')


def cmd_peek(a):
    with open(a.file, encoding='utf-8', errors='replace') as f:
        for i, line in enumerate(f):
            if i >= a.lines:
                break
            sys.stdout.write(short(line.rstrip('\n'), 300) + '\n')


def main():
    # web pages: `rootcrawl.py web outline|section|find|links …` (rootweb.py)
    if len(sys.argv) > 1 and sys.argv[1] == 'web':
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import rootweb
        return rootweb.main(sys.argv[2:])
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description='Root Crawl: profile data locally, read less.')
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('profile')
    p.add_argument('path')
    p.add_argument('--budget', type=int, default=3000, help='max tokens in the report')
    p.add_argument('--refresh', action='store_true')
    t = sp.add_parser('table')
    t.add_argument('file')
    t.add_argument('--cols')
    t.add_argument('--where', help='e.g. "price>10 and city~seoul"')
    t.add_argument('--limit', type=int, default=20)
    i = sp.add_parser('images')
    i.add_argument('path')
    i.add_argument('--make')
    i.add_argument('--software')
    i.add_argument('--limit', type=int, default=30)
    pr = sp.add_parser('pairs')
    pr.add_argument('path')
    pr.add_argument('--limit', type=int, default=30)
    pk = sp.add_parser('peek')
    pk.add_argument('file')
    pk.add_argument('--lines', type=int, default=40)
    a = ap.parse_args()
    target = getattr(a, 'path', None) or getattr(a, 'file', None)
    if not os.path.exists(target):
        sys.exit(f'rootcrawl: no such file or folder: {target}')
    if a.cmd == 'profile' and os.path.isfile(a.path):
        ext = os.path.splitext(a.path)[1].lower()
        print(f'# Root Crawl: {os.path.abspath(a.path)} ({human(os.path.getsize(a.path))})')
        print(json.dumps(profile_file(a.path, ext), ensure_ascii=False, indent=1, default=str)[: a.budget * 4])
        return
    if a.cmd in ('images', 'pairs') and not os.path.isdir(a.path):
        sys.exit(f'rootcrawl: {a.cmd} needs a folder: {a.path}')
    if a.cmd == 'profile':
        files, fresh, secs = profile_folder(a.path, refresh=a.refresh)
        print(report(a.path, files, fresh, secs, a.budget))
    else:
        {'table': cmd_table, 'images': cmd_images, 'pairs': cmd_pairs, 'peek': cmd_peek}[a.cmd](a)


if __name__ == '__main__':
    main()
