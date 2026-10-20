"""Experiment 6: phone → camera without pairs. Real phone photos and real camera photos of
different scenes; the scene AI learns a table per photo so its phone photos can't be told
from camera photos by a small critic network, while staying close to what was shot.
(The unpaired setting of Zeng et al. 2020: LSGAN loss + a pull toward the input.)

    python tools/looklab/adaptlut/gan.py prep     # phone photos → data_phone.npz
    TAG=gan python tools/looklab/adaptlut/gan.py train 6000
"""
import os
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
os.environ.setdefault('DATA', 'cam')
import train  # noqa: E402


def prep():
    from PIL import Image
    files = sorted((train.REF / 'phonecmp').rglob('*.jpg')) + sorted((train.REF / 'commons').rglob('*.jpg'))
    np.random.default_rng(1).shuffle(files)
    out = []
    for p in files:
        try:
            im = Image.open(p)
            im.draft('RGB', (480, 480))
            im = im.convert('RGB')
        except Exception:
            continue
        w, h = im.size
        s = min(w, h)
        q = int(s * 0.75)
        for x0, y0, side in [((w - s) // 2, (h - s) // 2, s), (0, 0, q), (w - q, h - q, q)]:
            out.append(np.asarray(im.crop((x0, y0, x0 + side, y0 + side)).resize((160, 160), Image.BOX), np.uint8))
    np.savez(HERE / 'data_phone.npz', x=np.stack(out))
    print('phone crops', len(out))


def critic():
    import tensorflow as tf
    L = tf.keras.layers
    inp = L.Input((None, None, 3))
    h = inp
    for c in (16, 32, 64, 64):
        h = L.Conv2D(c, 4, strides=2, padding='same')(h)
        h = L.LeakyReLU(0.2)(h)
    h = L.Conv2D(1, 3, padding='same')(h)  # patch scores
    return tf.keras.Model(inp, h)


def run(steps, lam=float(os.environ.get('LAM', 1.0))):
    import tensorflow as tf
    phone = np.load(HERE / 'data_phone.npz')['x']
    cam = np.load(HERE / f"data_{os.environ.get('CAMDATA', 'cam')}.npz")['x']
    phone_tr = phone[: int(len(phone) * 0.92)]
    cam_tr = cam[: int(len(cam) * 0.92)]
    net, D = train.build(), critic()
    basis = tf.Variable(np.random.default_rng(1).normal(0, 1e-3, (train.K, train.S, train.S, train.S, 3)).astype(np.float32))
    ident = tf.constant(train.identity())
    og, od = tf.keras.optimizers.Adam(1e-3, beta_1=0.5), tf.keras.optimizers.Adam(1e-4, beta_1=0.5)
    ck = train.CK
    ck.mkdir(exist_ok=True)

    @tf.function
    def step(p, c):
        with tf.GradientTape() as tg, tf.GradientTape() as td:
            w = net(p, training=True)
            lut = ident[None] + tf.einsum('bk,ksgrc->bsgrc', w, basis)
            out = train.apply_lut(tf, lut, p)
            fake, real = D(out, training=True), D(c, training=True)
            d_loss = tf.reduce_mean(tf.square(real - 1)) + tf.reduce_mean(tf.square(fake))
            adv = tf.reduce_mean(tf.square(fake - 1))
            stay = tf.reduce_mean(tf.abs(out - p))  # keep what was shot
            # whites and greys stay neutral; colours keep their hue (only tone and density move)
            def cbcr(x):
                return 0.5 * x[..., 2] - 0.0813 * x[..., 1] - 0.4187 * x[..., 0] + 0.0, -0.1687 * x[..., 0] - 0.3313 * x[..., 1] + 0.5 * x[..., 2]
            pr, pb = -0.1687 * p[..., 0] - 0.3313 * p[..., 1] + 0.5 * p[..., 2], 0.5 * p[..., 0] - 0.4187 * p[..., 1] - 0.0813 * p[..., 2]
            orr, ob = -0.1687 * out[..., 0] - 0.3313 * out[..., 1] + 0.5 * out[..., 2], 0.5 * out[..., 0] - 0.4187 * out[..., 1] - 0.0813 * out[..., 2]
            pc = tf.sqrt(pr * pr + pb * pb + 1e-6)
            oc = tf.sqrt(orr * orr + ob * ob + 1e-6)
            neutral = tf.cast(pc < 0.02, tf.float32)
            cast = tf.reduce_sum(neutral * oc) / (tf.reduce_sum(neutral) + 1.0)
            colourful = tf.clip_by_value((pc - 0.03) / 0.05, 0.0, 1.0)
            cosd = (pr * orr + pb * ob) / (pc * oc)
            hue = tf.reduce_sum(colourful * (1 - cosd)) / (tf.reduce_sum(colourful) + 1.0)
            tv = sum(tf.reduce_mean(tf.square(d)) for d in (basis[:, 1:] - basis[:, :-1], basis[:, :, 1:] - basis[:, :, :-1], basis[:, :, :, 1:] - basis[:, :, :, :-1]))
            mono = sum(tf.reduce_mean(tf.nn.relu(-d)) for d in (lut[:, 1:] - lut[:, :-1], lut[:, :, 1:] - lut[:, :, :-1], lut[:, :, :, 1:] - lut[:, :, :, :-1]))
            g_loss = adv + lam * stay + 1e-4 * tv + 10 * mono + float(os.environ.get('NEU', 0)) * (cast + hue)
        gv = net.trainable_variables + [basis]
        og.apply_gradients(zip(tg.gradient(g_loss, gv), gv))
        od.apply_gradients(zip(td.gradient(d_loss, D.trainable_variables), D.trainable_variables))
        return adv, d_loss, stay

    rng = np.random.default_rng(3)
    for s in range(1, steps + 1):
        ip, ic = rng.integers(0, len(phone_tr), 16), rng.integers(0, len(cam_tr), 16)
        o = rng.integers(0, 33, 2)
        p = phone_tr[ip, o[0]:o[0] + 128, o[1]:o[1] + 128].astype(np.float32) / 255
        c = cam_tr[ic, o[1]:o[1] + 128, o[0]:o[0] + 128].astype(np.float32) / 255
        a, d, st = step(tf.constant(p), tf.constant(c))
        if s % 100 == 0:
            print(f'step {s} adv {float(a):.3f} critic {float(d):.3f} change {float(st) * 255:.1f}/255', flush=True)
        if s % 500 == 0 or s == steps:
            np.save(ck / 'basis.npy', basis.numpy())
            net.save_weights(str(ck / 'net.weights.h5'))


if __name__ == '__main__':
    if sys.argv[1] == 'prep':
        prep()
    else:
        run(int(sys.argv[2]) if len(sys.argv) > 2 else 6000)
