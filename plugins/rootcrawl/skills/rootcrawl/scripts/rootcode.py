"""Root Crawl for code: a map of a codebase instead of its files.

Reading source files to find where something lives costs tens of thousands of tokens. The map
lists each file's classes, functions and methods with their line numbers (signatures only),
most-referenced first, so an AI can open just the lines it needs:

    rootcode.py map PATH [--budget 2500] [--files 40]   # the codebase's map
    rootcode.py symbol PATH NAME [--refs 15]            # where NAME is defined and used
    rootcode.py lines FILE START END                    # just those lines

Python is read with its own parser; Dart, JS/TS, Java, Kotlin, Swift, Go, Rust, C/C++/C#, PHP
and Ruby by declaration patterns. Standard library only.
"""
import ast
import collections
import os
import re
import sys

LANG = {'.py': 'py', '.dart': 'dart', '.js': 'js', '.jsx': 'js', '.mjs': 'js', '.ts': 'js', '.tsx': 'js', '.java': 'java',
        '.kt': 'kt', '.kts': 'kt', '.swift': 'swift', '.go': 'go', '.rs': 'rs', '.c': 'c', '.h': 'c', '.cc': 'c',
        '.cpp': 'c', '.hpp': 'c', '.cs': 'cs', '.php': 'php', '.rb': 'rb'}
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'build', 'dist', '.dart_tool', '.idea', 'target',
             'Pods', '.gradle', 'site-packages', '.next', 'out', 'coverage'}
GENERATED = re.compile(r'(\.g\.dart|\.freezed\.dart|\.pb\.\w+|_pb2\.py|\.min\.js|\.generated\.\w+|\.g\.kt)$|(^|[/\\])(generated|gen)[/\\]', re.I)
KEYWORDS = {'if', 'for', 'while', 'switch', 'catch', 'return', 'new', 'else', 'do', 'try', 'await', 'throw', 'super', 'this',
            'sizeof', 'case', 'assert', 'final', 'const', 'static', 'var', 'let', 'in', 'is', 'as', 'typeof'}

# declaration patterns per language family: (kind, regex with a 'name' group)
PATTERNS = {
    'dart': [('class', r'^\s*(?:abstract\s+|sealed\s+|base\s+|final\s+|interface\s+)*(?:class|mixin|enum|extension(?:\s+type)?)\s+(?P<name>\w+)'),
             ('fn', r'^\s*(?:@\w+\s+)*(?:static\s+|external\s+|abstract\s+|override\s+)*(?!return\b|await\b|new\b|final\b|var\b|const\b|throw\b|yield\b|else\b|case\b)(?P<type>(?:Future|Stream|FutureOr|Iterable|List|Map|Set|void|bool|int|double|num|String|dynamic|Object|Widget|[A-Z]\w*)(?:<[^()]*>)?\??)\s+(?P<name>[a-z_]\w*)\s*(?:<[^>]*>)?\s*\((?:[^()]|\([^()]*\))*(?:\)\s*(?:async\s*\*?|sync\s*\*)?\s*(?:\{|=>)|$)'),
             ('get', r'^\s*(?:static\s+)?[\w<>?,. ]+\s+(?:get|set)\s+(?P<name>\w+)')],
    'js': [('class', r'^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?(?:class|interface|enum|type)\s+(?P<name>\w+)'),
           ('fn', r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(?P<name>\w+)'),
           ('fn', r'^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*(?::[^=]+)?=\s*(?:async\s+)?(?:\([^)]*\)|\w+)\s*=>'),
           ('fn', r'^\s+(?:public\s+|private\s+|protected\s+|static\s+|async\s+|readonly\s+|get\s+|set\s+)*(?P<name>[A-Za-z_]\w*)\s*(?:<[^>]*>)?\s*\([^;]*\)\s*(?::\s*[^{;]+)?\{')],
    'java': [('class', r'^\s*(?:@\w+\s+)*(?:public\s+|private\s+|protected\s+|static\s+|final\s+|abstract\s+|sealed\s+)*(?:class|interface|enum|record)\s+(?P<name>\w+)'),
             ('fn', r'^\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:public\s+|private\s+|protected\s+|static\s+|final\s+|abstract\s+|synchronized\s+|native\s+|default\s+)*(?:<[^>]+>\s+)?[\w<>\[\],.? ]+\s+(?P<name>\w+)\s*\([^;]*\)\s*(?:throws [\w., ]+)?\s*\{')],
    'kt': [('class', r'^\s*(?:(?:public|private|internal|protected|open|abstract|sealed|data|enum|inner|value|annotation)\s+)*(?:class|interface|object)\s+(?P<name>\w+)'),
           ('fn', r'^\s*(?:(?:public|private|internal|protected|override|open|suspend|inline|operator|infix|tailrec)\s+)*fun\s+(?:<[^>]+>\s*)?(?:[\w.]+\.)?(?P<name>\w+)')],
    'swift': [('class', r'^\s*(?:(?:public|private|fileprivate|internal|open|final)\s+)*(?:class|struct|enum|protocol|extension|actor)\s+(?P<name>\w+)'),
              ('fn', r'^\s*(?:(?:public|private|fileprivate|internal|open|override|static|class|mutating|@\w+)\s+)*func\s+(?P<name>\w+)')],
    'go': [('class', r'^type\s+(?P<name>\w+)\s+(?:struct|interface)'),
           ('fn', r'^func\s+(?:\([^)]*\)\s*)?(?P<name>\w+)')],
    'rs': [('class', r'^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait|impl(?:<[^>]*>)?)\s+(?P<name>\w+)'),
           ('fn', r'^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const\s+|async\s+|unsafe\s+|extern\s+"C"\s+)*fn\s+(?P<name>\w+)')],
    'c': [('class', r'^\s*(?:typedef\s+)?(?:class|struct|enum|union|namespace)\s+(?P<name>\w+)\s*[:{]?'),
          ('fn', r'^(?:[\w:*&<>,]+\s+)+\**(?P<name>[A-Za-z_][\w:~]*)\s*\([^;]*\)\s*(?:const\s*)?(?:override\s*)?\{?\s*$')],
    'cs': [('class', r'^\s*(?:(?:public|private|protected|internal|static|sealed|abstract|partial)\s+)*(?:class|interface|struct|enum|record)\s+(?P<name>\w+)'),
           ('fn', r'^\s*(?:(?:public|private|protected|internal|static|virtual|override|async|abstract|sealed)\s+)+[\w<>\[\],.? ]+\s+(?P<name>\w+)\s*\(')],
    'php': [('class', r'^\s*(?:abstract\s+|final\s+)?(?:class|interface|trait|enum)\s+(?P<name>\w+)'),
            ('fn', r'^\s*(?:(?:public|private|protected|static|abstract|final)\s+)*function\s+(?P<name>\w+)')],
    'rb': [('class', r'^\s*(?:class|module)\s+(?P<name>[\w:]+)'),
           ('fn', r'^\s*def\s+(?:self\.)?(?P<name>[\w?!=]+)')],
}
COMPILED = {k: [(kind, re.compile(rx)) for kind, rx in v] for k, v in PATTERNS.items()}
WORD = re.compile(r'[A-Za-z_]\w*')
COMMON = {'main', 'build', 'init', 'run', 'get', 'set', 'add', 'remove', 'update', 'dispose', 'close', 'open', 'load', 'save',
          'start', 'stop', 'reset', 'clear', 'toString', 'toJson', 'fromJson', 'copyWith', 'value', 'name', 'size', 'label',
          'data', 'item', 'items', 'list', 'test', 'setUp', 'tearDown', 'create', 'apply', 'call', 'parse', 'format', 'render',
          'paint', 'draw', 'show', 'hide', 'next', 'prev', 'read', 'write', 'handle', 'process', 'execute', 'equals', 'hashCode'}


def walk(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith('.')]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in LANG:
                yield os.path.join(d, f), LANG[ext]


def py_symbols(src):
    out = []
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return None

    def sig(fn):
        a = fn.args
        names = [x.arg for x in a.posonlyargs + a.args] + (['*' + a.vararg.arg] if a.vararg else []) + [x.arg for x in a.kwonlyargs] + (['**' + a.kwarg.arg] if a.kwarg else [])
        return f'({", ".join(n for n in names if n not in ("self", "cls"))})'

    def visit(node, depth):
        for n in ast.iter_child_nodes(node):
            if isinstance(n, ast.ClassDef):
                out.append((n.lineno, depth, 'class', n.name, f'class {n.name}'))
                visit(n, depth + 1)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append((n.lineno, depth, 'fn', n.name, f'{"async " if isinstance(n, ast.AsyncFunctionDef) else ""}def {n.name}{sig(n)}'))
    visit(tree, 0)
    return out


def regex_symbols(lines, lang):
    out = []
    pats = COMPILED[lang]
    depth = 0
    for i, line in enumerate(lines, 1):
        s = line.split('//')[0] if lang != 'py' else line
        stripped = s.strip()
        if stripped.startswith(('*', '/*', '#', '@')) and not stripped.startswith('#[') and lang not in ('py', 'rb'):
            pass
        else:
            for kind, rx in pats:
                m = rx.match(s)
                if not m:
                    continue
                name = m.group('name').split('.')[-1]
                if name in KEYWORDS or (kind == 'fn' and name[:1].isupper() and lang in ('dart',) and depth == 0 and '(' not in s):
                    continue
                if kind == 'fn' and lang == 'dart' and re.match(r'^\s*(return|if|for|while|switch|else|await)\b', s):
                    continue
                if depth > 1 and lang in ('dart', 'js', 'java', 'kt', 'swift', 'cs', 'php', 'c'):
                    break
                text = re.sub(r'\s+', ' ', stripped.rstrip('{').rstrip())[:110]
                out.append((i, min(depth, 3), 'class' if kind == 'class' else 'fn', name, text))
                break
        depth += line.count('{') - line.count('}')
        depth = max(depth, 0)
    return out


def scan(root):
    files = {}
    for path, lang in walk(root):
        try:
            src = open(path, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        lines = src.splitlines()
        syms = py_symbols(src) if lang == 'py' else None
        if syms is None:
            syms = regex_symbols(lines, 'dart' if lang == 'py' else lang) if lang != 'py' else []
        files[os.path.relpath(path, root)] = {'lang': lang, 'lines': len(lines), 'chars': len(src), 'syms': syms,
                                              'gen': bool(GENERATED.search(path)), 'words': collections.Counter(WORD.findall(src))}
    return files


def refs(files):
    """How many other files mention each defined name: what the codebase leans on."""
    defined = collections.defaultdict(set)
    for f, d in files.items():
        for s in d['syms']:
            if len(s[3]) >= 4 and s[3] not in COMMON:
                defined[s[3]].add(f)
    count = collections.Counter()
    for f, d in files.items():
        for name, where in defined.items():
            if f not in where and name in d['words']:
                count[name] += 1
    return count


def code_map(root, budget, max_files):
    files = scan(root)
    if not files:
        return f'# Root Crawl code map: {os.path.abspath(root)}\nno source files found'
    rc = refs(files)
    total_chars = sum(d['chars'] for d in files.values())
    by_lang = collections.Counter()
    for d in files.values():
        by_lang[d['lang']] += d['lines']
    out = [f'# Code map: {os.path.abspath(root)}',
           f'{len(files)} files · {sum(d["lines"] for d in files.values()):,} lines · ' + ', '.join(f'{k} {v:,}' for k, v in by_lang.most_common()),
           '(line numbers; most-referenced symbols first; `symbol NAME` for definition + uses, `lines FILE A B` to read)\n']

    def score(item):
        f, d = item
        return (d['gen'], -sum(rc[s[3]] for s in d['syms']) - d['lines'] / 200)
    ranked = sorted(files.items(), key=score)
    shown = 0
    for f, d in ranked:
        if shown >= max_files:
            break
        shown += 1
        tag = ' (generated)' if d['gen'] else ''
        out.append(f'## {f} — {d["lines"]} lines{tag}')
        syms = d['syms']
        if d['gen'] and len(syms) > 6:
            out.append(f'  {len(syms)} declarations (generated code)')
            continue
        tops = [s for s in syms if s[1] == 0]
        inner = [s for s in syms if s[1] > 0]
        keep = sorted(syms, key=lambda s: (-rc[s[3]], s[0]))[:14] if len(syms) > 18 else syms
        keep = sorted(keep, key=lambda s: s[0])
        for ln, depth, kind, name, text in keep:
            r = f'  ×{rc[name]}' if rc[name] else ''
            out.append(f'{"  " * (depth + 1)}{ln}: {text}{r}')
        if len(keep) < len(syms):
            # nothing dropped: the rest as name:line, a few tokens each
            kept = {id(x) for x in keep}
            rest = [x for x in syms if id(x) not in kept]
            out.append('    also: ' + ', '.join(f'{x[3]}:{x[0]}' for x in rest))
    if shown < len(files):
        rest = ranked[shown:]
        out.append(f'\n… {len(rest)} more files: ' + ', '.join(f for f, _ in rest[:25]) + (' …' if len(rest) > 25 else ''))
    text = '\n'.join(out)
    if len(text) // 4 > budget:
        text = text[: budget * 4] + '\n… (cut to the budget: map a subfolder, or raise --budget)'
    return text + f'\n\n_Map ≈ {len(text) // 4:,} tokens; reading all {len(files)} files ≈ {total_chars // 4:,} tokens._'


def symbol(root, name, max_refs):
    files = scan(root)
    out = []
    for f, d in files.items():
        for ln, depth, kind, n, text in d['syms']:
            if n == name:
                out.append(f'defined: {f}:{ln}  {text}')
    if not out:
        out.append(f'(no declaration named {name})')
    rx = re.compile(r'\b' + re.escape(name) + r'\b')
    uses = []
    for f, d in files.items():
        if name not in d['words']:
            continue
        try:
            for i, line in enumerate(open(os.path.join(root, f), encoding='utf-8', errors='replace'), 1):
                if rx.search(line):
                    uses.append(f'{f}:{i}  {line.strip()[:120]}')
        except OSError:
            pass
    out.append(f'uses: {len(uses)}')
    out.extend(uses[:max_refs])
    if len(uses) > max_refs:
        out.append(f'… {len(uses) - max_refs} more')
    return '\n'.join(out)


def lines(path, a, b):
    out = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for i, line in enumerate(f, 1):
            if i > b:
                break
            if i >= a:
                out.append(f'{i}\t{line.rstrip()}')
    return '\n'.join(out)


def main(argv=None):
    import argparse
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description='Root Crawl for code')
    sp = ap.add_subparsers(dest='cmd', required=True)
    m = sp.add_parser('map')
    m.add_argument('path')
    m.add_argument('--budget', type=int, default=2500)
    m.add_argument('--files', type=int, default=40)
    s = sp.add_parser('symbol')
    s.add_argument('path')
    s.add_argument('name')
    s.add_argument('--refs', type=int, default=15)
    ln = sp.add_parser('lines')
    ln.add_argument('file')
    ln.add_argument('start', type=int)
    ln.add_argument('end', type=int)
    a = ap.parse_args(argv)
    target = getattr(a, 'path', None) or a.file
    if not os.path.exists(target):
        sys.exit(f'rootcode: no such file or folder: {target}')
    if a.cmd == 'map':
        text = code_map(a.path, a.budget, a.files)
        m = re.findall(r'files ≈ ([\d,]+) tokens', text)
        direct = int(m[-1].replace(',', '')) if m else len(text) // 4
    elif a.cmd == 'symbol':
        text = symbol(a.path, a.name, a.refs)
        files = {ln.split(':')[0].split('  ')[0].replace('defined: ', '') for ln in text.splitlines() if ':' in ln and not ln.startswith(('uses', '…', '('))}
        direct = sum(os.path.getsize(os.path.join(a.path, f)) // 4 for f in files if os.path.isfile(os.path.join(a.path, f)))
    else:
        text = lines(a.file, a.start, a.end)
        direct = os.path.getsize(a.file) // 4
    print(text)
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import savings
        savings.record('code ' + a.cmd, target, len(text) // 4, max(direct, len(text) // 4))
    except Exception:
        pass


if __name__ == '__main__':
    main()
