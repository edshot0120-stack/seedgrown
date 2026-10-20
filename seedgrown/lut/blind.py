"""Blind A/B sheets for a judge (a person or a vision model): each row is one photo done two
ways, left / right at random; the key is written separately and opened only after judging.

    python tools/looklab/adaptlut/blind.py METHOD_A METHOD_B OUT_DIR [N]
    methods as in judge2.py ('hand', 'original', 'AI gan8 tone+hand', …)
"""
import json
import os
import pathlib
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import judge2  # noqa: E402

REF = pathlib.Path(os.environ.get('SEEDGROWN_DATA', 'data'))  # see docs/DATA.md


def main():
    a_name, b_name, out = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 24
    out.mkdir(parents=True, exist_ok=True)
    ms = judge2.methods()
    fa, fb = ms[a_name], ms[b_name]
    rng = np.random.default_rng(23)
    files = sorted((REF / 'phonecmp').rglob('*.jpg')) + sorted((REF / 'commons').rglob('*.jpg'))
    # spread over dark → bright so night and high-key are in
    meds = []
    for i in rng.choice(len(files), 400, replace=False):
        try:
            im = Image.open(files[i]).convert('L')
            im.thumbnail((64, 64))
            meds.append((float(np.median(np.asarray(im))), files[i]))
        except Exception:
            pass
    meds.sort()
    pick = [meds[int(q * (len(meds) - 1))][1] for q in np.linspace(0.02, 0.98, n)]
    key, rows = {}, []
    for k, p in enumerate(pick):
        im = Image.open(p)
        im.draft('RGB', (700, 700))
        im = im.convert('RGB')
        im.thumbnail((360, 360))
        x = np.asarray(im, np.float32) / 255
        left_is_a = bool(rng.random() < 0.5)
        l, r = (fa(x), fb(x)) if left_is_a else (fb(x), fa(x))
        key[k + 1] = a_name if left_is_a else b_name
        rows.append((k + 1, np.concatenate([l, np.ones((l.shape[0], 8, 3)), r], 1)))
    per = 6
    for s in range(0, len(rows), per):
        chunk = rows[s:s + per]
        w = max(r.shape[1] for _, r in chunk)
        tiles = []
        for num, r in chunk:
            canvas = np.ones((r.shape[0] + 22, w, 3))
            canvas[22:, :r.shape[1]] = r
            img = Image.fromarray((canvas * 255).astype(np.uint8))
            ImageDraw.Draw(img).text((6, 4), f'#{num}   L | R', fill=(0, 0, 0))
            tiles.append(np.asarray(img))
        Image.fromarray(np.concatenate(tiles, 0)).save(out / f'sheet_{s // per + 1}.jpg', quality=88)
    json.dump({'a': a_name, 'b': b_name, 'left': key}, open(out / 'KEY_do_not_open_before_judging.json', 'w'))
    print('sheets', (len(rows) + per - 1) // per, 'in', out)


if __name__ == '__main__':
    main()
