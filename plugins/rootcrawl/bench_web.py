"""Root Crawl web mode on real pages: outline vs the page's text vs its HTML (tokens ≈ chars / 4)."""
import sys
import time
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'skills', 'rootcrawl', 'scripts'))
import rootweb  # noqa: E402

URLS = sys.argv[1:]
print('| page | outline | page text | HTML | vs text | vs HTML | headings | time |')
print('|---|---|---|---|---|---|---|---|')
for u in URLS:
    t0 = time.time()
    try:
        o = rootweb.outline(u, 1500)
    except Exception as e:
        print(f'| {u} | error: {str(e)[:60]} |')
        continue
    last = o.strip().splitlines()[-1]
    nums = [int(x.replace(',', '')) for x in __import__('re').findall(r'≈ ([\d,]+)', last)]
    p, _ = rootweb.parse(u)
    hs = len([b for b in rootweb.content(p) if b[0] == 'h'])
    name = u.split('//')[-1][:45]
    print(f'| {name} | {nums[0]:,} | {nums[1]:,} | {nums[2]:,} | ×{nums[1] / max(nums[0], 1):.0f} | ×{nums[2] / max(nums[0], 1):.0f} | {hs} | {time.time() - t0:.1f}s |', flush=True)
