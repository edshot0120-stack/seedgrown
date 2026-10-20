"""Smoke tests on a generated folder of awkward files: run `python plugins/rootcrawl/tests/smoke.py`."""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
S = os.path.join(HERE, '..', 'skills', 'rootcrawl', 'scripts', 'rootcrawl.py')


def run(*args):
    r = subprocess.run([sys.executable, S, *args], capture_output=True, text=True, encoding='utf-8', env={**os.environ, 'ROOTCRAWL_CACHE': CACHE})
    return r.stdout + r.stderr


T = tempfile.mkdtemp()
CACHE = tempfile.mkdtemp()
os.makedirs(os.path.join(T, 'sub', '깊은 폴더'))
open(os.path.join(T, 'sales.csv'), 'w', encoding='utf-8').write('id,name,price,date,flag\n1,사과,1200,2026-10-01,yes\n2,"banana, ripe",,2026-10-02,no\n3,cherry,3.5e2,bad,yes\n')
open(os.path.join(T, 'data.json'), 'w').write('{"users":[{"id":1}],"meta":{"v":2}}')
open(os.path.join(T, 'bad.json'), 'w').write('{broken')
open(os.path.join(T, 'ev.jsonl'), 'w').write('{"a":1}\n{"a":2}\nnot json\n')
open(os.path.join(T, 'app.log'), 'w').write('2026-10-20 10:00:01 ERROR id=1 failed\n2026-10-20 11:00:00 ERROR id=2 failed\n')
open(os.path.join(T, 'fake.jpg'), 'w').write('not an image')
open(os.path.join(T, 'sub', '깊은 폴더', 'm.py'), 'w', encoding='utf-8').write('class A:\n    def go(self, x):\n        return x\n\ndef helper():\n    pass\n')
cases = [
    (('profile', T), 'sales.csv — 3 rows'),
    (('profile', T), 'not valid JSON'),
    (('profile', T), '1 unparsable lines'),
    (('profile', T), '1 unreadable'),
    (('profile', T), 'number'),
    (('profile', os.path.join(T, 'nope')), 'no such file'),
    (('profile', os.path.join(T, 'sales.csv')), '"kind": "table"'),
    (('table', os.path.join(T, 'sales.csv'), '--where', 'price>=1000 and flag=yes'), '1 matching rows'),
    (('table', os.path.join(T, 'sales.csv'), '--cols', 'nme'), 'unknown columns'),
    (('code', 'map', T), 'def go(x)'),
    (('code', 'symbol', T, 'helper'), 'defined:'),
    (('savings',), 'saved'),
]
bad = 0
for args, expect in cases:
    out = run(*args)
    ok = expect in out
    bad += not ok
    print(('PASS' if ok else 'FAIL'), ' '.join(a if len(a) < 40 else '…' + a[-30:] for a in args), '' if ok else '\n   ' + out[-300:])
print('cache folders written into the data folder:', sum(1 for x in os.listdir(T) if 'rootcrawl' in x))
shutil.rmtree(T, ignore_errors=True)
shutil.rmtree(CACHE, ignore_errors=True)
sys.exit(1 if bad else 0)
