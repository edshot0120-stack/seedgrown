"""Measures a camera's colour rendering from RAW + camera-JPEG pairs of the same shots and
bakes it into a 33³ look table (the app's strip format):

    neutral(RAW)  →  camera JPEG

`neutral` is a plain, standard rendering of the RAW (camera white balance, sRGB, a gentle
default contrast — close to what a phone JPEG looks like); the table is what the camera does
on top of that. Only colour statistics leave this tool — no image is shipped.

    python tools/looklab/fit_look.py OUT.png [--holdout N] pairs_dir [pairs_dir…]

Each pairs_dir holds NAME.jpg + NAME.raf/.arw/.nef/.cr3/.dng. Writes OUT.png (strip) and
OUT.cmp.jpg (neutral | fitted | camera on held-out shots).
"""
import pathlib
import sys

import numpy as np
import rawpy
from PIL import Image

N = 33
W = 480  # analysis width
RAW_EXT = ('.raf', '.arw', '.nef', '.cr3', '.cr2', '.dng', '.orf', '.rw2', '.3fr', '.fff')


def srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055)


def lin(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def tone(e):
    """A gentle default contrast (like a phone's standard rendering) on encoded values."""
    s = e * e * (3 - 2 * e)
    return e + (s - e) * 0.35


def _resize(a, tw, th):
    return np.stack([np.asarray(Image.fromarray(a[..., c].astype(np.float32)).resize((tw, th), Image.BOX)) for c in range(3)], -1)


def _blur(x):  # two 3×3 box passes ≈ a small gaussian
    for _ in range(2):
        p = np.pad(x, ((1, 1), (1, 1), (0, 0)), mode='edge')
        x = sum(p[dy:dy + x.shape[0], dx:dx + x.shape[1]] for dy in range(3) for dx in range(3)) / 9
    return x


def _ncc(a, b):
    a = a - a.mean()
    b = b - b.mean()
    return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum() + 1e-12))


def pair(raw_path, jpg_path):
    """(neutral, camera) at analysis size, or None when they don't show the same frame."""
    jpg = Image.open(jpg_path).convert('RGB')
    with rawpy.imread(str(raw_path)) as r:
        # linear, camera white balance, sRGB primaries, no auto brightening
        rgb = r.postprocess(use_camera_wb=True, output_color=rawpy.ColorSpace.sRGB, gamma=(1, 1), no_auto_bright=True,
                            output_bps=16, half_size=True, user_flip=0)
    a0 = rgb.astype(np.float32) / 65535
    jw, jh = jpg.size
    tw, th = W, round(W * jh / jw)
    cam = np.asarray(jpg.resize((tw, th), Image.BOX), dtype=np.float32) / 255
    camL = srgb(lin(cam)) @ [0.3, 0.6, 0.1]
    best = None
    # orientation (some JPEGs are stored upright, the RAW never is) and the JPEG's crop
    for k in (0, 1, 3, 2):
        a = np.rot90(a0, k)
        h, w = a.shape[:2]
        for z in (1.0, 0.97, 0.94, 0.9):
            cw, ch = w * z, w * z * jh / jw
            if ch > h:
                ch, cw = h * z, h * z * jw / jh
            y0, x0 = int((h - ch) / 2), int((w - cw) / 2)
            crop = a[y0:y0 + int(ch), x0:x0 + int(cw)]
            if crop.shape[0] < 16 or crop.shape[1] < 16:
                continue
            ls = _resize(crop, tw, th)
            c = _ncc(srgb(ls / max(np.median(ls), 1e-6) * 0.18) @ [0.3, 0.6, 0.1], camL)
            if best is None or c > best[0]:
                best = (c, ls)
    if best is None or best[0] < 0.85:
        print(f'  skipped {pathlib.Path(jpg_path).name}: not the same frame (match {best[0] if best else 0:.2f})')
        return None
    lin_small = best[1]
    lin_small, cam = _blur(lin_small), _blur(cam)
    # the centre only: lens corrections in the JPEG move the edges of the frame
    mh, mw = int(th * 0.1), int(tw * 0.1)
    lin_small, cam = lin_small[mh:th - mh, mw:tw - mw], cam[mh:th - mh, mw:tw - mw]
    # exposure: the neutral rendering's mid-grey matched to the camera's (exposure isn't the look)
    yl = np.median(lin_small @ [0.2126, 0.7152, 0.0722])
    yc = np.median(lin(cam) @ [0.2126, 0.7152, 0.0722])
    lin_small = lin_small * (yc / max(yl, 1e-6))
    # white balance isn't the look (it's set per shot): the RAW's channel gains matched to the
    # camera JPEG on near-grey areas, so only the colour rendering is left to measure
    cl = lin(cam)
    grey = (cam.max(-1) - cam.min(-1) < 0.06) & (cam.mean(-1) > 0.15) & (cam.mean(-1) < 0.85)
    if grey.sum() > 200:
        g = np.median(cl[grey], 0) / np.maximum(np.median(lin_small[grey], 0), 1e-6)
        g = g / g[1]
        lin_small = lin_small * np.clip(g, 0.6, 1.6)
    neutral = tone(srgb(lin_small))
    return neutral, cam


def flatness(img):
    """1 on flat areas, → 0 on edges (where a pixel of misalignment changes the colour)."""
    l = img @ np.array([0.3, 0.6, 0.1])
    gy, gx = np.gradient(l)
    return 1 / (1 + (np.hypot(gx, gy) * 40) ** 2)


def fit(pairs, smooth=0):
    x = np.concatenate([p[0].reshape(-1, 3) for p in pairs])
    y = np.concatenate([p[1].reshape(-1, 3) for p in pairs])
    wt = np.concatenate([np.minimum(flatness(p[0]), flatness(p[1])).reshape(-1) for p in pairs])
    keep = (x.max(1) < 0.995) & (x.min(1) > 0.003) & (y.max(1) < 0.995) & (wt > 0.2)  # clipped pixels and edges say nothing
    x, y, wt = x[keep], y[keep], wt[keep]
    d = y - x  # the look as a residual: identity where there's no data
    g = x * (N - 1)
    i0 = np.clip(np.floor(g).astype(int), 0, N - 2)
    f = g - i0
    acc = np.zeros((N, N, N, 3))
    wsum = np.zeros((N, N, N))
    for dr in (0, 1):
        for dg in (0, 1):
            for db in (0, 1):
                w = (f[:, 0] if dr else 1 - f[:, 0]) * (f[:, 1] if dg else 1 - f[:, 1]) * (f[:, 2] if db else 1 - f[:, 2]) * wt
                idx = (i0[:, 2] + db, i0[:, 1] + dg, i0[:, 0] + dr)  # [b][g][r]
                np.add.at(wsum, idx, w)
                np.add.at(acc, idx, d * w[:, None])
    have = wsum > 0.5
    res = np.where(have[..., None], acc / np.maximum(wsum, 1e-9)[..., None], 0)
    conf = np.clip(wsum / 20, 0, 1)
    # fill and smooth: nodes with little data lean on their neighbours (diffusion), data stays
    cur = res.copy()
    for _ in range(200):
        nb = np.zeros_like(cur)
        cnt = np.zeros(cur.shape[:3])
        for ax in range(3):
            for s in (1, -1):
                sh = np.roll(cur, s, axis=ax)
                m = np.ones(cur.shape[:3])
                if s == 1:
                    sl = [slice(None)] * 3
                    sl[ax] = 0
                    m[tuple(sl)] = 0
                else:
                    sl = [slice(None)] * 3
                    sl[ax] = -1
                    m[tuple(sl)] = 0
                nb += sh * m[..., None]
                cnt += m
        avg = nb / cnt[..., None]
        cur = res * conf[..., None] + avg * (1 - conf[..., None]) * 0.98  # far from data → back towards identity
    # extra smoothing (few or compressed references): a separable [1 2 1] pass per axis
    for _ in range(smooth):
        for ax in range(3):
            p = np.concatenate([cur.take([0], axis=ax), cur, cur.take([-1], axis=ax)], axis=ax)
            n = cur.shape[ax]
            cur = (p.take(range(0, n), axis=ax) + 2 * p.take(range(1, n + 1), axis=ax) + p.take(range(2, n + 2), axis=ax)) / 4
    gg = np.linspace(0, 1, N)
    b, gq, r = np.meshgrid(gg, gg, gg, indexing='ij')
    base = np.stack([r, gq, b], -1)
    return np.clip(base + cur, 0, 1), int(have.sum())


def apply(lut, img):
    p = np.clip(img, 0, 1) * (N - 1)
    i0 = np.clip(np.floor(p).astype(int), 0, N - 2)
    f = p - i0
    out = 0
    for dr in (0, 1):
        for dg in (0, 1):
            for db in (0, 1):
                w = (f[..., 0] if dr else 1 - f[..., 0]) * (f[..., 1] if dg else 1 - f[..., 1]) * (f[..., 2] if db else 1 - f[..., 2])
                out = out + lut[i0[..., 2] + db, i0[..., 1] + dg, i0[..., 0] + dr] * w[..., None]
    return out


def strip(lut, path):
    s = np.transpose(lut, (1, 0, 2, 3)).reshape(N, N * N, 3)
    Image.fromarray(np.clip(s * 255 + 0.5, 0, 255).astype(np.uint8)).save(path, optimize=True)


def main():
    args = sys.argv[1:]
    out = pathlib.Path(args.pop(0))
    hold, smooth = 2, 0
    while args and args[0].startswith('--'):
        flag = args.pop(0)
        if flag == '--holdout':
            hold = int(args.pop(0))
        elif flag == '--smooth':
            smooth = int(args.pop(0))
    names = []
    for d in args:
        for j in sorted(pathlib.Path(d).glob('*.jpg')):
            raw = next((j.with_suffix(e) for e in RAW_EXT if j.with_suffix(e).exists()), None)
            if raw:
                names.append((raw, j))
    pairs = [p for p in (pair(r, j) for r, j in names) if p is not None]
    train, test = pairs[hold:], pairs[:hold]
    lut, nodes = fit(train, smooth=smooth)
    strip(lut, out)

    def de(a, b):
        return float(np.abs(a - b).mean() * 255)
    rows = []
    for (n, c) in test:
        fitted = apply(lut, n)
        print(f'held-out: neutral→camera {de(n, c):5.2f}   fitted→camera {de(fitted, c):5.2f}  (mean |Δ| in 8-bit levels)')
        rows.append(np.concatenate([n, fitted, c], 1))
    Image.fromarray((np.clip(np.concatenate(rows, 0), 0, 1) * 255).astype(np.uint8)).save(out.with_suffix('.cmp.jpg'), quality=90)
    print(f'{len(train)} training shots, {nodes} table nodes with data')


if __name__ == '__main__':
    main()
