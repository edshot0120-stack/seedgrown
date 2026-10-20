"""Camera rendering for every colour look: what camera photos have and phone photos lack,
measured by camphone.py over ~470 camera and ~600 phone photos, baked into the look tables.

  · density: at the same lightness a camera's colours are richer, and saturated colours
    sit darker (as film dyes and camera profiles render them) instead of bright and pastel
  · midtones a touch lower: phones push everything bright
  · highlight shoulder: tones roll into white and lose colour gently instead of clipping

The pass runs on the look's input (the phone's render becomes a camera's, then the look),
plus a final shoulder on its output, then the finishing stage (finish.py).

    from camera_feel import apply;  table = apply(table, a=1.0)
"""
import json
import pathlib
import shutil
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from fit_look import N, strip  # noqa: E402
from fit_sim import load_table  # noqa: E402
from fit_style import from_oklab, oklab  # noqa: E402
from finish import finish  # noqa: E402



def bell(x, c, w):
    return np.exp(-((x - c) / w) ** 2)


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def pre(rgb, a):
    """Phone render → camera render (OkLab), strength a."""
    lab = oklab(rgb)
    L, A, B = lab[..., 0], lab[..., 1], lab[..., 2]
    C = np.hypot(A, B)
    # richer colour through the mids, none added to near-greys
    k = 1 + a * 0.14 * bell(L, 0.55, 0.28) * smooth(0.0, 0.04, C)
    # saturated colours sit darker (subtractive density), less so in deep shadow
    L2 = L - a * 0.30 * np.minimum(C, 0.22) * smooth(0.15, 0.45, L)
    # mids a little lower
    L2 = L2 - a * 0.022 * np.sin(np.pi * np.clip(L2, 0, 1))
    return from_oklab(np.stack([L2, A * k, B * k], -1))


def shoulder(rgb, a):
    """Tones roll into white and lose colour there, instead of clipping hard."""
    lab = oklab(rgb)
    L = lab[..., 0]
    k0 = 0.80
    over = np.maximum(L - k0, 0)
    span = 1 - k0
    Ln = np.where(L > k0, k0 + span * (1 - np.exp(-over / span * 1.25)) / (1 - np.exp(-1.25)) * (1 - a * 0.02), L)
    d = 1 - a * 0.35 * smooth(0.82, 1.0, L)
    return from_oklab(np.stack([Ln, lab[..., 1] * d, lab[..., 2] * d], -1))


def trilinear(T, rgb):
    """Samples a [b][g][r] table at rgb (…, 3)."""
    p = np.clip(rgb, 0, 1) * (N - 1)
    i0 = np.minimum(np.floor(p).astype(int), N - 2)
    f = p - i0
    r0, g0, b0 = i0[..., 0], i0[..., 1], i0[..., 2]
    fr, fg, fb = f[..., 0:1], f[..., 1:2], f[..., 2:3]
    out = 0
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                w = (fb if db else 1 - fb) * (fg if dg else 1 - fg) * (fr if dr else 1 - fr)
                out = out + w * T[b0 + db, g0 + dg, r0 + dr]
    return out


def apply(table, a=1.0, creative=False, mono=False):
    """A look table (N³×3, [b][g][r], encoded sRGB) with the camera rendering on its input and
    the finishing stage on its output."""
    g = np.linspace(0, 1, N)
    b, gg, r = np.meshgrid(g, g, g, indexing='ij')
    ident = np.stack([r, gg, b], -1)
    out = shoulder(trilinear(table, pre(ident, a)), a)
    return finish(out, oklab(ident), creative=creative, mono=mono)
