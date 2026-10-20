"""A judge that can't be gamed by flattening or tinting.

  pairs     DPED's held-out test patches: the same spot shot by a phone and by a DSLR.
            Each method turns the phone patch into its version; the score is how far that
            is from the DSLR's patch (OkLab ΔE ×100) — scene by scene, not by statistics.
  contrast  real modern phone photos: the tonal range (p98 − p2 lightness) kept, as a
            ratio to the photo's own — below 1 means blacks lifted / highlights pulled in.
  plus the clip / grey-cast / hue checks from realscore.py.

    python tools/looklab/adaptlut/judge2.py          (methods: original, hand, AI tags)
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
from camera_feel import pre, shoulder  # noqa: E402
from fit_style import from_oklab, oklab  # noqa: E402
from realscore import fidelity  # noqa: E402

REF = pathlib.Path(os.environ.get('SEEDGROWN_DATA', 'data'))  # see docs/DATA.md


def ai_fn(tag):
    import tensorflow as tf
    ck = HERE / f'ckpt_{tag}'
    net = train.build()
    net.load_weights(str(ck / 'net.weights.h5'))
    basis = np.load(ck / 'basis.npy')

    def fix(a):
        s = min(a.shape[:2])
        y0, x0 = (a.shape[0] - s) // 2, (a.shape[1] - s) // 2
        sq = np.asarray(Image.fromarray((a[y0:y0 + s, x0:x0 + s] * 255).astype(np.uint8)).resize((128, 128)), np.float32) / 255
        w = net(sq[None], training=False).numpy()[0]
        lut = train.identity() + np.einsum('k,ksgrc->sgrc', w, basis)
        return np.clip(np.asarray(train.apply_lut(tf, tf.constant(lut[None], tf.float32), tf.constant(a[None])))[0], 0, 1)
    return fix


def tone_only(a, f):
    la, lf = oklab(a), oklab(f)
    g = np.clip(lf[..., 0] / np.maximum(la[..., 0], 1e-3), 0.85, 1.15)[..., None]
    return from_oklab(np.concatenate([lf[..., :1], la[..., 1:] * g], -1))


def hand(a):
    return np.clip(shoulder(pre(a, 1.0), 1.0), 0, 1)


def methods():
    m = {'original': lambda a: a, 'hand': hand}
    for tag in os.environ.get('TAGS', 'dped,gan8').split(','):
        f = ai_fn(tag)
        m[f'AI {tag}'] = f
        m[f'AI {tag} tone+hand'] = (lambda f_: lambda a: hand(tone_only(a, f_(a))))(f)
    return m


def main():
    rng = np.random.default_rng(11)
    pairs = []
    for phone in ('iphone', 'sony', 'blackberry'):
        d = REF / 'dped' / phone / 'test_data' / 'patches'
        names = sorted(p.name for p in (d / phone).glob('*.jpg'))
        for n in rng.choice(names, 150, replace=False):
            pairs.append((np.asarray(Image.open(d / phone / n).convert('RGB'), np.float32) / 255,
                          np.asarray(Image.open(d / 'canon' / n).convert('RGB'), np.float32) / 255))
    files = sorted((REF / 'phonecmp').rglob('*.jpg'))
    phones = []
    for i in rng.choice(len(files), 120, replace=False):
        try:
            im = Image.open(files[i])
            im.draft('RGB', (600, 600))
            im = im.convert('RGB')
            im.thumbnail((384, 384))
            phones.append(np.asarray(im, np.float32) / 255)
        except Exception:
            pass
    print(f'{len(pairs)} DSLR pairs (held out) · {len(phones)} modern phone photos')
    print(f'  {"method":22s} {"ΔE to DSLR":>10s} {"range kept":>10s} {"clip":>6s} {"cast":>5s} {"hue°":>5s}')
    for name, fn in methods().items():
        de = np.mean([np.linalg.norm(oklab(fn(a)) - oklab(b), axis=-1).mean() * 100 for a, b in pairs])
        outs = [fn(a) for a in phones]
        rk = []
        for a, o in zip(phones, outs):
            la, lo = oklab(a)[..., 0], oklab(o)[..., 0]
            rk.append((np.percentile(lo, 98) - np.percentile(lo, 2)) / max(np.percentile(la, 98) - np.percentile(la, 2), 1e-3))
        clip = np.mean([((o.max(-1) > 0.996) | (o.max(-1) < 0.004)).mean() for o in outs]) * 100
        cast, hue = fidelity(phones, outs)
        print(f'  {name:22s} {de:10.2f} {np.mean(rk):10.3f} {clip:5.2f}% {cast:5.2f} {hue:5.1f}', flush=True)


if __name__ == '__main__':
    main()
