"""A phone's rendering measured against another's on the same scenes (published comparison
shots, tiled): the tiles are assembled, the second phone's frame aligned onto the first's
(different lenses → a homography), and base → other fitted as a 33³ table.

    python tools/looklab/fit_phone.py OUT.png BASE_DIR OTHER_DIR [BASE_DIR OTHER_DIR …]

Each dir holds RR-CC.jpg tiles. Writes OUT.png and OUT.cmp.jpg (base | fitted | other).
Only colour statistics leave this tool — no image is shipped.
"""
import pathlib
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from fit_look import apply, fit, strip  # noqa: E402

W = 900  # analysis width


def assemble(d):
    if str(d).lower().endswith(('.jpg', '.jpeg', '.png')):  # a single image
        im = Image.open(d).convert('RGB')
        return np.asarray(im.resize((W, round(W * im.size[1] / im.size[0])), Image.BOX), dtype=np.float32) / 255
    tiles = {}
    for f in pathlib.Path(d).glob('*.jpg'):
        r, c = map(int, f.stem.split('-'))
        tiles[(r, c)] = Image.open(f).convert('RGB')
    rows = sorted({r for r, _ in tiles})
    cols = sorted({c for _, c in tiles})
    tw, th = tiles[(rows[0], cols[0])].size
    out = Image.new('RGB', (tw * len(cols), th * len(rows)))
    for (r, c), im in tiles.items():
        out.paste(im, ((c - cols[0]) * tw, (r - rows[0]) * th))
    a = np.asarray(out.resize((W, round(W * out.size[1] / out.size[0])), Image.BOX), dtype=np.float32) / 255
    return a


def align(base, other):
    """`other` warped onto `base`'s frame, and the mask of where it lands."""
    g = lambda a: cv2.cvtColor((a * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    sift = cv2.SIFT_create(4000)
    k1, d1 = sift.detectAndCompute(g(base), None)
    k2, d2 = sift.detectAndCompute(g(other), None)
    m = cv2.BFMatcher().knnMatch(d2, d1, k=2)
    good = [a for a, b in m if a.distance < 0.75 * b.distance]
    src = np.float32([k2[a.queryIdx].pt for a in good])
    dst = np.float32([k1[a.trainIdx].pt for a in good])
    H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
    h, w = base.shape[:2]
    warped = cv2.warpPerspective(other, H, (w, h), flags=cv2.INTER_AREA)
    mask = cv2.warpPerspective(np.ones(other.shape[:2], np.float32), H, (w, h)) > 0.99
    print(f'  {len(good)} matches, {int(inl.sum())} inliers')
    return warped, mask, int(inl.sum())


def main():
    args = sys.argv[1:]
    out = pathlib.Path(args.pop(0))
    pairs, rows = [], []
    for bd, od in zip(args[::2], args[1::2]):
        b, o = assemble(bd), assemble(od)
        try:
            o, mask, inl = align(b, o)
        except Exception as e:
            print('  skipped', od, e)
            continue
        if inl < 40:
            print('  skipped', od, '(too few matches: not the same frame)')
            continue
        ys, xs = np.where(mask)
        y0, y1, x0, x1 = ys.min() + 8, ys.max() - 8, xs.min() + 8, xs.max() - 8
        b, o = b[y0:y1, x0:x1], o[y0:y1, x0:x1]
        pairs.append((b, o))
    lut, nodes = fit(pairs, smooth=2)
    strip(lut, out)
    for b, o in pairs:
        f = apply(lut, b)
        print(f'base→other {np.abs(b - o).mean() * 255:5.2f} → fitted {np.abs(f - o).mean() * 255:5.2f}')
        rows.append(np.concatenate([b, f, o], 1))
    wmax = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, wmax - r.shape[1]), (0, 0))) for r in rows]
    Image.fromarray((np.clip(np.concatenate(rows, 0), 0, 1) * 255).astype(np.uint8)).save(out.with_suffix('.cmp.jpg'), quality=88)
    print(nodes, 'nodes')


if __name__ == '__main__':
    main()
