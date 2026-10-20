"""The finishing stage every look table goes through last: what separates a professional
profile from a phone filter.

  · smoothing   the table's change from neutral is evened out where it's jagged (banding)
  · detail guard  blacks and whites stop short of crushing / blowing what had detail
  · skin guard  skin's hue, chroma and lightness stay within a range (wider for creative looks)
  · gamut       colours past what the screen shows are eased back along their own hue and
                lightness, keeping the gradation, instead of clipping channel by channel

    finish(table, creative=False, mono=False) → table
"""
import numpy as np

from fit_style import oklab

M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099], [0.0259040371, 0.7827717662, -0.8086757660]])
M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566], [0.0883024619, 0.2817188376, 0.6299787005]])
M2i, M1i = np.linalg.inv(M2), np.linalg.inv(M1)


def lab_to_lin(lab):
    return (lab @ M2i.T) ** 3 @ M1i.T


def lin_to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def smooth_max(a, b, e):
    return 0.5 * (a + b + np.sqrt((a - b) ** 2 + e * e))


def smooth_min(a, b, e):
    return 0.5 * (a + b - np.sqrt((a - b) ** 2 + e * e))


def blur3(x, passes=1):
    """A light [1 2 1] blur along each axis of the cube (edges held)."""
    for _ in range(passes):
        for ax in range(3):
            p = np.concatenate([np.take(x, [0], ax), x, np.take(x, [-1], ax)], ax)
            n = x.shape[ax]
            x = 0.25 * np.take(p, range(0, n), ax) + 0.5 * np.take(p, range(1, n + 1), ax) + 0.25 * np.take(p, range(2, n + 2), ax)
    return x


def max_chroma(L, h, iters=18):
    """The largest in-gamut chroma at each lightness / hue (bisection)."""
    lo = np.zeros_like(L)
    hi = np.full_like(L, 0.4)
    ca, sa = np.cos(h), np.sin(h)
    for _ in range(iters):
        m = (lo + hi) / 2
        rgb = lab_to_lin(np.stack([L, m * ca, m * sa], -1))
        ok = (rgb >= -1e-4).all(-1) & (rgb <= 1 + 1e-4).all(-1)
        lo = np.where(ok, m, lo)
        hi = np.where(ok, hi, m)
    return lo


def finish(T, ident_lab, creative=False, mono=False):
    out = oklab(np.clip(T, 0, 1))
    # 1 smoothing: the change from neutral, blurred a little where the table is rough
    d = out - ident_lab
    rough = np.zeros(out.shape[:3])
    for ax in range(3):
        d2 = np.linalg.norm(np.diff(out, 2, axis=ax), axis=-1)
        pad = [(0, 0)] * 3
        pad[ax] = (1, 1)
        rough = np.maximum(rough, np.pad(d2, pad, mode='edge'))
    w = np.clip((rough - 0.02) / 0.04, 0, 1)[..., None]
    out = ident_lab + d * (1 - w) + blur3(d, 2) * w
    L, a, b = out[..., 0], out[..., 1], out[..., 2]
    Lin = ident_lab[..., 0]
    # 2 detail guard: what had tone keeps a little (creative looks may go further)
    floor = (0.012 if creative else 0.03) * np.clip((Lin - 0.12) / 0.2, 0, 1)
    ceil = 1 - (0.008 if creative else 0.02) * np.clip((0.9 - Lin) / 0.2, 0, 1)
    L = smooth_max(L, floor, 0.02)
    L = smooth_min(L, ceil, 0.02)
    C = np.hypot(a, b)
    h = np.arctan2(b, a)
    if not mono:
        # 3 skin guard: in the input's skin region, hold the output near the input's skin
        li, ai, bi = ident_lab[..., 0], ident_lab[..., 1], ident_lab[..., 2]
        Ci, hi = np.hypot(ai, bi), np.arctan2(bi, ai)
        hd = np.degrees(hi) % 360
        sk = (np.clip((hd - 20) / 12, 0, 1) * np.clip((90 - hd) / 12, 0, 1) * np.clip((Ci - 0.02) / 0.02, 0, 1)
              * np.clip((0.16 - Ci) / 0.04, 0, 1) * np.clip((li - 0.38) / 0.08, 0, 1) * np.clip((0.92 - li) / 0.05, 0, 1))
        dh_max, c_lo, c_hi, dl_max = (np.radians(26), 0.55, 1.6, 0.12) if creative else (np.radians(11), 0.78, 1.32, 0.07)
        dh = np.angle(np.exp(1j * (h - hi)))
        h = np.where(sk > 0, hi + dh + (np.clip(dh, -dh_max, dh_max) - dh) * sk, h)
        ratio = C / np.maximum(Ci, 1e-4)
        C = np.where(sk > 0, C + (Ci * np.clip(ratio, c_lo, c_hi) - C) * sk, C)
        dl = L - li
        L = np.where(sk > 0, L + (li + np.clip(dl, -dl_max, dl_max) - L) * sk, L)
        # 4 gamut: a soft knee at 72% of what this lightness and hue allow
        cm = max_chroma(np.clip(L, 0, 1), h)
        k = 0.72 * cm
        over = C > k
        C = np.where(over, k + (cm - k) * np.tanh((C - k) / np.maximum(cm - k, 1e-5)), C)
    else:
        C = C * 0
    lab = np.stack([L, C * np.cos(h), C * np.sin(h)], -1)
    # 5 tone order: a brighter input never comes out darker (no solarized steps in a
    # gradient) — lightness made monotone along each axis, as the mean of its running max
    # and its running min from the far end; small dips (< 0.3%) are left alone
    for _ in range(2):
        for ax in range(3):
            Lx = np.moveaxis(lab[..., 0], ax, -1)
            up = np.maximum.accumulate(Lx, axis=-1)
            dn = np.flip(np.minimum.accumulate(np.flip(Lx, -1), axis=-1), -1)
            mono_l = 0.5 * (up + dn)
            fix = np.abs(mono_l - Lx) > 0.003
            lab[..., 0] = np.moveaxis(np.where(fix, mono_l, Lx), -1, ax)
    # 6 a last even-out where the guards left seams
    d = lab - ident_lab
    rough = np.zeros(lab.shape[:3])
    for ax in range(3):
        d2 = np.linalg.norm(np.diff(lab, 2, axis=ax), axis=-1)
        pad = [(0, 0)] * 3
        pad[ax] = (1, 1)
        rough = np.maximum(rough, np.pad(d2, pad, mode='edge'))
    w = np.clip((rough - 0.03) / 0.04, 0, 1)[..., None]
    lab = ident_lab + d * (1 - w) + blur3(d, 1) * w
    return lin_to_srgb(lab_to_lin(lab))
