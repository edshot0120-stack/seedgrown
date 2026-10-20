"""The savings ledger: every Root Crawl answer records what it cost and what reading the
source directly would have cost (conservatively: a web page's plain text, not its HTML; a whole
file, not a whole folder, for a slice), so `rootcrawl.py savings` can show what it saved.
"""
import json
import os
import time


def _path():
    base = os.environ.get('ROOTCRAWL_CACHE') or os.path.join(
        os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_CACHE_HOME') or os.path.join(os.path.expanduser('~'), '.cache'), 'rootcrawl')
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, 'savings.jsonl')


def record(cmd, target, used, direct):
    """used / direct are token estimates (characters / 4)."""
    try:
        with open(_path(), 'a', encoding='utf-8') as f:
            f.write(json.dumps({'t': int(time.time()), 'cmd': cmd, 'target': str(target)[:200], 'used': int(used), 'direct': int(direct)}) + '\n')
    except OSError:
        pass


def report(days=None):
    rows = []
    try:
        with open(_path(), encoding='utf-8') as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    if days:
        cut = time.time() - days * 86400
        rows = [r for r in rows if r['t'] >= cut]
    if not rows:
        return 'No Root Crawl answers recorded yet.'
    by = {}
    for r in rows:
        k = r['cmd']
        u, d, n = by.get(k, (0, 0, 0))
        by[k] = (u + r['used'], d + r['direct'], n + 1)
    used = sum(r['used'] for r in rows)
    direct = sum(r['direct'] for r in rows)
    out = [f'# Root Crawl savings{f" (last {days} days)" if days else ""}',
           f'{len(rows)} answers · {used:,} tokens used instead of {direct:,} → saved {direct - used:,} ({direct / max(used, 1):.1f}× less)\n',
           '| command | answers | used | reading directly | saved |', '|---|---|---|---|---|']
    for k, (u, d, n) in sorted(by.items(), key=lambda kv: -(kv[1][1] - kv[1][0])):
        out.append(f'| {k} | {n} | {u:,} | {d:,} | {d - u:,} |')
    out.append('\n_Estimates: tokens ≈ characters / 4; images ≈ 1,600 tokens each to look at._')
    return '\n'.join(out)
