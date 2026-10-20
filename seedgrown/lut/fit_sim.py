"""A camera look from same-scene JPEGs: one scene rendered in a base look (e.g. Provia) and in
others (Classic Chrome, …). Fits base → other as a 33³ table, then chains it after a measured
neutral → base table (fit_look.py), giving neutral → other for the app.

    python tools/looklab/fit_sim.py BASE_TABLE.png BASE.jpg OUT_DIR  OTHER.jpg [OTHER.jpg…]
        [--mask-bottom 0.2]   ignore a caption band at the bottom
"""
import pathlib
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from fit_look import N, apply, fit, strip  # noqa: E402


def load_table(path):
    s = np.asarray(Image.open(path).convert('RGB'), dtype=np.float32) / 255  # (N, N*N, 3) rows=g
    return np.transpose(s.reshape(N, N, N, 3), (1, 0, 2, 3))  # → [b][g][r]


def small(path, mask_bottom):
    im = Image.open(path).convert('RGB')
    w, h = im.size
    im = im.crop((0, 0, w, int(h * (1 - mask_bottom))))
    tw = 480
    a = np.asarray(im.resize((tw, round(tw * im.size[1] / im.size[0])), Image.BOX), dtype=np.float32) / 255
    return a


def main():
    args = sys.argv[1:]
    mb = 0.0
    if '--mask-bottom' in args:
        i = args.index('--mask-bottom')
        mb = float(args[i + 1])
        del args[i:i + 2]
    base_table, base_jpg, out = load_table(args[0]), args[1], pathlib.Path(args[2])
    out.mkdir(parents=True, exist_ok=True)
    b = small(base_jpg, mb)
    g = np.linspace(0, 1, N)
    bb, gg, rr = np.meshgrid(g, g, g, indexing='ij')
    lattice = np.stack([rr, gg, bb], -1)
    via_base = apply(base_table, lattice)  # neutral → base
    for other in args[3:]:
        o = small(other, mb)
        sim, nodes = fit([(b, o)], smooth=4)  # base → other (one scene, web JPEGs: smoothed)
        chained = apply(sim, via_base)  # neutral → base → other
        name = pathlib.Path(other).stem
        strip(chained, out / f'{name}.png')
        err0, err1 = np.abs(b - o).mean() * 255, np.abs(apply(sim, b) - o).mean() * 255
        print(f'{name:28s} base→other {err0:5.2f} → fitted {err1:5.2f}  ({nodes} nodes)')


if __name__ == '__main__':
    main()
