"""A rendering style measured statistically: two sets of straight-out-of-camera photos (phone
A, phone B — different scenes) compared by their averaged tone and colour distributions in
OkLab, giving a 33³ table A → B:

  * tone: the mean luminance CDFs quantile-matched (contrast, shadow lift, highlight roll-off)
  * chroma: mean chroma per hue × lightness band, B over A (where each renders colour fuller
    or quieter)
  * white point: the mean cast of near-neutral areas, half applied (scene light varies)

Scene content differs from set to set, so only broad tendencies are trusted: every curve is
smoothed and every ratio clamped.

    python tools/looklab/fit_style.py OUT.png A_DIR B_DIR
"""
import pathlib
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from fit_look import N, lin, srgb, strip  # noqa: E402

HB, LB = 12, 5  # hue bins, lightness bands


def oklab(rgb):
    l = lin(rgb)
    M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566], [0.0883024619, 0.2817188376, 0.6299787005]])
    M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099], [0.0259040371, 0.7827717662, -0.8086757660]])
    return np.cbrt(np.maximum(l @ M1.T, 0)) @ M2.T


def from_oklab(lab):
    M2i = np.linalg.inv(np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099], [0.0259040371, 0.7827717662, -0.8086757660]]))
    M1i = np.linalg.inv(np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566], [0.0883024619, 0.2817188376, 0.6299787005]]))
    return srgb(np.clip((lab @ M2i.T) ** 3 @ M1i.T, 0, 1))


def stats(d):
    cdfs, csum, ccnt, casts = [], np.zeros((HB, LB)), np.zeros((HB, LB)), []
    for f in sorted(pathlib.Path(d).glob('*.jpg')):
        try:
            im = Image.open(f).convert('RGB')
        except Exception:
            continue
        im.thumbnail((400, 400))
        lab = oklab(np.asarray(im, np.float32) / 255).reshape(-1, 3)
        L = np.clip(lab[:, 0], 0, 1)
        h, _ = np.histogram(L, 256, (0, 1))
        cdfs.append(np.cumsum(h) / max(h.sum(), 1))
        C = np.hypot(lab[:, 1], lab[:, 2])
        hue = (np.arctan2(lab[:, 2], lab[:, 1]) % (2 * np.pi)) / (2 * np.pi)
        col = C > 0.03
        hb = np.minimum((hue * HB).astype(int), HB - 1)
        lb = np.minimum((L * LB).astype(int), LB - 1)
        # each image counts once per bin (its mean), so big skies don't outvote the rest
        s, c = np.zeros((HB, LB)), np.zeros((HB, LB))
        np.add.at(s, (hb[col], lb[col]), C[col])
        np.add.at(c, (hb[col], lb[col]), 1)
        have = c > 50
        csum[have] += s[have] / c[have]
        ccnt[have] += 1
        grey = (C < 0.035) & (L > 0.35) & (L < 0.9)
        if grey.sum() > 500:
            casts.append(lab[grey, 1:].mean(0))
    print(d, len(cdfs), 'photos')
    return np.mean(cdfs, 0), csum / np.maximum(ccnt, 1), ccnt, np.mean(casts, 0)


def smooth1(x, k=9):
    w = np.ones(k) / k
    return np.convolve(np.pad(x, k // 2, mode='edge'), w, 'valid')


def main():
    out, a_dir, b_dir = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    cdf_a, ch_a, n_a, cast_a = stats(a_dir)
    cdf_b, ch_b, n_b, cast_b = stats(b_dir)
    # tone: L in A → the L in B at the same quantile
    xs = (np.arange(256) + 0.5) / 256
    tone = np.interp(cdf_a, cdf_b, xs)
    tone = smooth1(smooth1(tone))
    tone = np.maximum.accumulate(tone)
    # chroma ratio per hue × band, trusted where both sets have plenty of photos
    ok = (n_a > 20) & (n_b > 20)
    ratio = np.where(ok, ch_b / np.maximum(ch_a, 1e-4), 1.0)
    ratio = np.clip(ratio, 0.75, 1.3)
    # smooth around the hue circle
    ratio = (np.roll(ratio, 1, 0) + 2 * ratio + np.roll(ratio, -1, 0)) / 4
    cast = (cast_b - cast_a) * 0.5
    print('tone at 0.1/0.25/0.5/0.75/0.9:', [round(float(np.interp(v, xs, tone)), 3) for v in (0.1, 0.25, 0.5, 0.75, 0.9)])
    print('chroma ratio by hue (mid band):', np.round(ratio[:, 2], 2))
    print('white cast shift a,b:', np.round(cast, 4))
    # the table
    g = np.linspace(0, 1, N)
    b, gg, r = np.meshgrid(g, g, g, indexing='ij')
    lab = oklab(np.stack([r, gg, b], -1))
    L = np.clip(lab[..., 0], 0, 1)
    C = np.hypot(lab[..., 1], lab[..., 2])
    hue = (np.arctan2(lab[..., 2], lab[..., 1]) % (2 * np.pi)) / (2 * np.pi)
    # bilinear in hue (circular) × band
    hp = hue * HB - 0.5
    h0 = np.floor(hp).astype(int)
    fh = hp - h0
    lp = np.clip(L * LB - 0.5, 0, LB - 1)
    l0 = np.minimum(np.floor(lp).astype(int), LB - 2)
    fl = lp - l0
    def R(hi, li):
        return ratio[hi % HB, li]
    k = (R(h0, l0) * (1 - fh) * (1 - fl) + R(h0 + 1, l0) * fh * (1 - fl) + R(h0, l0 + 1) * (1 - fh) * fl + R(h0 + 1, l0 + 1) * fh * fl)
    L2 = np.interp(L, xs, tone)
    neutral = np.clip(1 - C / 0.08, 0, 1)[..., None]  # the cast mostly on near-greys
    ab = lab[..., 1:] * k[..., None] + cast * (0.4 + 0.6 * neutral)
    res = from_oklab(np.concatenate([L2[..., None], ab], -1))
    strip(np.clip(res, 0, 1), out)
    print('wrote', out)


if __name__ == '__main__':
    main()
