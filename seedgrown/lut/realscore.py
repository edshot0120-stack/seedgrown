"""How camera-like real phone photos become: the scene AI at several strengths (and none),
scored against the camera statistics camphone.py measured (lightness percentiles, chroma by
lightness band). There is no answer photo for a real phone shot, so this is the judge.

    TAG=phone3 DATA=cam SPOIL=phone python tools/looklab/adaptlut/realscore.py
"""
import os
import pathlib
import sys

import numpy as np
from PIL import Image

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import train  # noqa: E402
from fit_style import oklab  # noqa: E402

REF = pathlib.Path(os.environ.get('SEEDGROWN_DATA', 'data'))  # see docs/DATA.md
LB = np.linspace(0, 1, 6)


def stats(imgs):
    lp, cl = [], np.zeros((5, 2))
    clip = []
    for a in imgs:
        lab = oklab(a.reshape(-1, 3))
        L, C = lab[:, 0], np.hypot(lab[:, 1], lab[:, 2])
        lp.append(np.percentile(L, np.arange(1, 100)))
        bi = np.clip(np.digitize(L, LB) - 1, 0, 4)
        for b in range(5):
            m = bi == b
            if m.sum() > 50:
                cl[b] += (C[m].mean(), 1)
        clip.append(((a.max(-1) > 0.996) | (a.max(-1) < 0.004)).mean())
    return np.mean(lp, 0), cl[:, 0] / np.maximum(cl[:, 1], 1), float(np.mean(clip) * 100)


def fidelity(src, out):
    """Whites / greys gaining colour (OkLab chroma ×100, where the input was neutral) and the
    hue turning on colourful pixels (degrees, median): what the camera statistics can't see."""
    casts, hues = [], []
    for a, b in zip(src, out):
        la, lb = oklab(a.reshape(-1, 3)), oklab(b.reshape(-1, 3))
        ca, cb = np.hypot(la[:, 1], la[:, 2]), np.hypot(lb[:, 1], lb[:, 2])
        n = ca < 0.015
        if n.sum() > 100:
            casts.append(cb[n].mean() * 100)
        c = ca > 0.06
        if c.sum() > 100:
            d = np.angle(np.exp(1j * (np.arctan2(lb[c, 2], lb[c, 1]) - np.arctan2(la[c, 2], la[c, 1]))))
            hues.append(np.degrees(np.median(np.abs(d))))
    return float(np.mean(casts)), float(np.mean(hues))


def main():
    import tensorflow as tf
    import os
    if os.environ.get('JUDGE') == 'mine':
        # an independent judge: camera JPEGs never used in any training set
        from camphone import measure
        # any folder of straight-out-of-camera JPEGs that no model trained on
        paths = sorted((REF / 'judge_camera').rglob('*.jpg'))
        m = measure(paths)
        camL, camC = m[0], m[1]
        print('judge: independent camera JPEGs,', m[5])
    else:
        cam = np.load(HERE.parent / 'out' / 'camphone.npz')
        camL, camC = cam['cL'], cam['cCL']
    net = train.build()
    net.load_weights(str(train.CK / 'net.weights.h5'))
    basis = np.load(train.CK / 'basis.npy')
    files = sorted((REF / 'phonecmp').rglob('*.jpg'))
    rng = np.random.default_rng(5)
    files = [files[i] for i in rng.choice(len(files), 200, replace=False)]
    phone, fixed = [], []
    for p in files:
        try:
            im = Image.open(p)
            im.draft('RGB', (600, 600))
            im = im.convert('RGB')
        except Exception:
            continue
        im.thumbnail((384, 384))
        a = np.asarray(im, np.float32) / 255
        s = min(a.shape[:2])
        sq = np.asarray(im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width - s) // 2 + s, (im.height - s) // 2 + s)).resize((128, 128)), np.float32) / 255
        w = net(sq[None], training=False).numpy()[0]
        lut = train.identity() + np.einsum('k,ksgrc->sgrc', w, basis)
        f = np.clip(np.asarray(train.apply_lut(tf, tf.constant(lut[None], tf.float32), tf.constant(a[None])))[0], 0, 1)
        phone.append(a)
        fixed.append(f)
    print(f'{len(phone)} real phone photos · camera-likeness distance (lower = more like a camera)')
    for k in (0.0, 0.4, 0.6, 0.8, 1.0):
        imgs = [a + k * (f - a) for a, f in zip(phone, fixed)]
        L, C, clip = stats(imgs)
        dl = np.abs(L - camL).mean() * 100
        dc = np.abs(C - camC).mean() * 1000
        cast, hue = fidelity(phone, imgs)
        print(f'  AI {k:.1f}: tone {dl:5.2f} · colour {dc:5.2f} · total {dl + dc:5.2f} · clip {clip:.2f}% · grey cast {cast:.2f} · hue shift {hue:.1f}°')
    # the hand-made camera rendering (camera_feel.pre + shoulder) as the baseline
    from camera_feel import pre, shoulder
    for k in (0.5, 1.0):
        imgs = [np.clip(shoulder(pre(a, k), k), 0, 1) for a in phone]
        L, C, clip = stats(imgs)
        dl = np.abs(L - camL).mean() * 100
        dc = np.abs(C - camC).mean() * 1000
        print(f'  hand {k:.1f}: tone {dl:5.2f} · colour {dc:5.2f} · total {dl + dc:5.2f} · clip {clip:.2f}%')
    # the AI for lightness only (colour kept as shot), then the hand-made density
    from fit_style import from_oklab
    def tone_only(a, f, k):
        la, lf = oklab(a), oklab(f)
        L = la[..., 0] + k * (lf[..., 0] - la[..., 0])
        # chroma follows lightness a little, so darker mids don't read as greyer
        g = np.clip(L / np.maximum(la[..., 0], 1e-3), 0.85, 1.15)[..., None]
        return from_oklab(np.concatenate([L[..., None], la[..., 1:] * g], -1))
    for k in (0.6, 1.0):
        imgs = [np.clip(shoulder(pre(tone_only(a, f, k), 1.0), 1.0), 0, 1) for a, f in zip(phone, fixed)]
        L, C, clip = stats(imgs)
        dl = np.abs(L - camL).mean() * 100
        dc = np.abs(C - camC).mean() * 1000
        cast, hue = fidelity(phone, imgs)
        print(f'  AI-tone {k:.1f}+hand: tone {dl:5.2f} · colour {dc:5.2f} · total {dl + dc:5.2f} · clip {clip:.2f}% · grey cast {cast:.2f} · hue shift {hue:.1f}°')
    # the two together: the AI's tone, then the hand-made density on top
    for k in (0.6, 1.0):
        imgs = [np.clip(shoulder(pre(a + k * (f - a), 1.0), 1.0), 0, 1) for a, f in zip(phone, fixed)]
        L, C, clip = stats(imgs)
        dl = np.abs(L - camL).mean() * 100
        dc = np.abs(C - camC).mean() * 1000
        cast, hue = fidelity(phone, imgs)
        print(f'  AI {k:.1f}+hand: tone {dl:5.2f} · colour {dc:5.2f} · total {dl + dc:5.2f} · clip {clip:.2f}% · grey cast {cast:.2f} · hue shift {hue:.1f}°')


if __name__ == '__main__':
    main()
