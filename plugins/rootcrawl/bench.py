"""Root Crawl on real folders: time, report size and what reading the files would cost.

    python plugins/rootcrawl/bench.py FOLDER [FOLDER …]   → a markdown table
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'skills', 'rootcrawl', 'scripts'))
import rootcrawl  # noqa: E402


def main():
    print('| folder | files | size | 1st run | cached run | report tokens | direct tokens | saving |')
    print('|---|---|---|---|---|---|---|---|')
    for root in sys.argv[1:]:
        t0 = time.time()
        files, fresh, _ = rootcrawl.profile_folder(root, refresh=True)
        first = time.time() - t0
        t0 = time.time()
        files, fresh, secs = rootcrawl.profile_folder(root)
        again = time.time() - t0
        text = rootcrawl.report(root, files, fresh, secs, 3000)
        rep = len(text) // 4
        last = text.strip().splitlines()[-1]
        direct = int(last.split('≈')[-1].split('tokens')[0].replace(',', '').strip())
        size = sum(f['size'] for f in files.values())
        print(f'| {os.path.basename(os.path.normpath(root))} | {len(files):,} | {rootcrawl.human(size)} | {first:.1f}s | {again:.1f}s | {rep:,} | {direct:,} | ×{direct / max(rep, 1):,.0f} |', flush=True)


if __name__ == '__main__':
    main()
