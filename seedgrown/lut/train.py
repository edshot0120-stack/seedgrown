"""Tintly's scene AI: a tiny network that looks at a photo once (128 px) and returns a colour
table that carries it to a well-exposed, neutral-balanced rendering — the step before a look.
(After "Learning Image-adaptive 3D Lookup Tables", Zeng et al. 2020: a small CNN weights a
few learned basis tables; the table, not the network, touches the pixels.)

Training is self-supervised: good photos are spoiled at random (exposure, white balance,
a phone's flat or punchy tone, a lifted black, saturation) and the network learns to undo it.

    python tools/looklab/adaptlut/train.py prep      # photos → data.npz (160 px crops)
    python tools/looklab/adaptlut/train.py train [steps]
    python tools/looklab/adaptlut/train.py eval      # held-out error, vs no correction
"""
import pathlib
import sys

import os

import numpy as np

HERE = pathlib.Path(__file__).parent
# experiment knobs (env): TAG names the checkpoint folder, K the basis tables, W the width
TAG = os.environ.get('TAG', '')
CK = HERE / ('ckpt' + (f'_{TAG}' if TAG else ''))
REF = pathlib.Path(os.environ.get('SEEDGROWN_DATA', 'data'))  # see docs/DATA.md
S = 17  # basis table size
K = int(os.environ.get('K', 8))  # basis tables
W = float(os.environ.get('W', 1))  # network width multiplier
IMG = 128


def srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


DATA = os.environ.get('DATA', 'all')  # 'cam': camera photos only as the answers
SPOIL = os.environ.get('SPOIL', 'generic')  # 'phone': what a phone's processing does


def prep_dped(per=8000):
    """Real pairs: each phone's patch and the DSLR's patch of the same spot (DPED)."""
    from PIL import Image
    root = REF / 'dped'
    xs, ys = [], []
    rng = np.random.default_rng(0)
    for phone in ('iphone', 'sony', 'blackberry'):
        d = root / phone / 'training_data'
        names = sorted(p.name for p in (d / phone).glob('*.jpg'))
        for n in rng.choice(names, min(per, len(names)), replace=False):
            xs.append(np.asarray(Image.open(d / phone / n).convert('RGB'), np.uint8))
            ys.append(np.asarray(Image.open(d / 'canon' / n).convert('RGB'), np.uint8))
        print(phone, len(xs), flush=True)
    idx = rng.permutation(len(xs))
    np.savez(HERE / 'data_dped.npz', x=np.stack(xs)[idx], y=np.stack(ys)[idx])
    print('pairs', len(xs))


def prep():
    if DATA == 'dped':
        return prep_dped()
    from PIL import Image
    dirs = ['cams', 'scan', 'canon_eos_r5', 'sony_a7r_v', 'leica_m10', 'nikon_z7_ii', 'fuji_xt5', 'store_portraits', 'commons', 'phonecmp', 'styles', 'fujiofficial']
    if DATA == 'ooc':
        # straight out of the camera only (makers' samples, review samples): no one's grading
        dirs = ['scan', 'canon_eos_r5', 'sony_a7r_v', 'leica_m10', 'nikon_z7_ii', 'fuji_xt5', 'hasselblad_x1d_ii_50c', 'ricoh_gr_iii', 'fujiofficial', 'cams']
    if DATA == 'cam':
        dirs = ['cams', 'scan', 'canon_eos_r5', 'sony_a7r_v', 'leica_m10', 'nikon_z7_ii', 'fuji_xt5', 'hasselblad_x1d_ii_50c', 'ricoh_gr_iii', 'fujiofficial', 'store_portraits']
        dirs += [f'styles/{d}' for d in ('cam-hasselblad', 'cam-leica-m11', 'cam-leica-q3', 'cam-ricoh-gr', 'cam-sony', 'cam-x100vi')]
    files = []
    for d in dirs:
        files += sorted((REF / d).rglob('*.jpg'))
    np.random.default_rng(0).shuffle(files)
    out = []
    for i, p in enumerate(files):
        try:
            im = Image.open(p)
            im.draft('RGB', (480, 480))
            im = im.convert('RGB')
        except Exception:
            continue
        w, h = im.size
        s = min(w, h)
        boxes = [((w - s) // 2, (h - s) // 2, s)]
        if DATA in ('cam', 'ooc'):
            # few camera photos: corners and centre at 3/4 size too
            q = int(s * 0.75)
            boxes += [(0, 0, q), (w - q, 0, q), (0, h - q, q), (w - q, h - q, q)]
        for x0, y0, side in boxes:
            out.append(np.asarray(im.crop((x0, y0, x0 + side, y0 + side)).resize((160, 160), Image.BOX), np.uint8))
        if i % 300 == 0:
            print(i, len(files), flush=True)
    x = np.stack(out)  # photos in random order, a photo's crops together: the tail is unseen photos
    if DATA == 'all':
        np.random.default_rng(0).shuffle(x)
    np.savez_compressed(HERE / f'data_{DATA}.npz' if DATA != 'all' else HERE / 'data.npz', x=x)
    print('photos', x.shape)


def spoil_phone(e, rng):
    """A camera's photo as a phone renders the same scene: brighter mids, lifted shadows,
    local tone mapping (HDR) flattening the big light differences while keeping texture,
    a little more saturation; plus some exposure and white-balance error."""
    import cv2
    li = lin(e) * 2 ** rng.uniform(-0.7, 0.6)
    t, g = rng.uniform(-0.15, 0.15), rng.uniform(-0.05, 0.05)
    gain = np.array([1 + t, 1 + g, 1 - t])
    li = li * gain / gain.mean()
    y = np.maximum((li * np.array([0.2126, 0.7152, 0.0722])).sum(-1), 1e-4)
    ly = np.log(y)
    base = cv2.GaussianBlur(ly.astype(np.float32), (0, 0), rng.uniform(4, 12))
    c = rng.uniform(0.45, 0.85)  # how hard the HDR compresses
    m = np.median(base)
    ly2 = m + (base - m) * c + (ly - base) * rng.uniform(1.0, 1.25)
    li = li * (np.exp(ly2) / y)[..., None]
    x = srgb(li)
    x = np.clip(x, 0, 1) ** rng.uniform(0.72, 0.95)  # brighter mids
    x = x + rng.uniform(0, 0.05) * (1 - x)  # lifted shadows
    yy = (x * np.array([0.2126, 0.7152, 0.0722])).sum(-1, keepdims=True)
    x = np.clip(yy + (x - yy) * rng.uniform(0.95, 1.25), 0, 1)
    return x.astype(np.float32)


def spoil(e, rng):
    if SPOIL == 'phone':
        return spoil_phone(e, rng)
    return spoil_generic(e, rng)


def spoil_generic(e, rng):
    """A good photo (encoded, 0..1) as a phone or a careless exposure might have made it."""
    li = lin(e)
    li = li * 2 ** rng.uniform(-1.6, 1.1)
    t, g = rng.uniform(-0.28, 0.28), rng.uniform(-0.08, 0.08)
    gain = np.array([1 + t, 1 + g, 1 - t])
    li = li * gain / gain.mean()
    x = srgb(li)
    # tone: flat (phone HDR) or punchy, around the mids
    k = rng.uniform(0.65, 1.3)
    x = np.clip(0.5 + (x - 0.5) * k, 0, 1) if rng.random() < 0.5 else np.clip(x ** (1 / k), 0, 1)
    x = x + rng.uniform(0, 0.07) * (1 - x)  # lifted black
    y = (x * np.array([0.2126, 0.7152, 0.0722])).sum(-1, keepdims=True)
    x = np.clip(y + (x - y) * rng.uniform(0.6, 1.4), 0, 1)
    return x.astype(np.float32)


def pair_batches(x, y, bs, rng):
    n = x.shape[1]
    c = IMG if n >= IMG else n - 4
    while True:
        idx = rng.integers(0, len(x), bs)
        o = rng.integers(0, n - c + 1, 2)
        a = x[idx, o[0]:o[0] + c, o[1]:o[1] + c].astype(np.float32) / 255
        b = y[idx, o[0]:o[0] + c, o[1]:o[1] + c].astype(np.float32) / 255
        if rng.random() < 0.5:
            a, b = a[:, :, ::-1], b[:, :, ::-1]
        yield a, b


def batches(x, bs, rng):
    while True:
        idx = rng.integers(0, len(x), bs)
        tgt, inp = [], []
        for i in idx:
            o = rng.integers(0, 160 - IMG + 1, 2)
            im = x[i, o[0]:o[0] + IMG, o[1]:o[1] + IMG].astype(np.float32) / 255
            if rng.random() < 0.5:
                im = im[:, ::-1]
            tgt.append(im)
            inp.append(spoil(im, rng))
        yield np.stack(inp), np.stack(tgt)


def build(size=None):
    import tensorflow as tf
    L = tf.keras.layers
    inp = L.Input((size, size, 3))  # any size: the pooled features don't care
    h = inp
    for c in (16, 32, 32, 64, 64):
        c = int(c * W)
        h = L.Conv2D(c, 3, strides=2, padding='same')(h)
        h = L.LeakyReLU(0.2)(h)
        h = L.BatchNormalization()(h)
    h = L.Conv2D(64, 3, padding='same', activation='relu')(h)
    h = L.GlobalAveragePooling2D()(h)
    h = L.Dropout(0.2)(h)
    w = L.Dense(K)(h)
    return tf.keras.Model(inp, w)


def identity():
    g = np.linspace(0, 1, S, dtype=np.float32)
    b, gg, r = np.meshgrid(g, g, g, indexing='ij')
    return np.stack([r, gg, b], -1)  # [b][g][r]


def apply_lut(tf, lut, x):
    """lut (B,S,S,S,3) [b][g][r]; x (B,H,W,3) → trilinear lookup."""
    B = tf.shape(x)[0]
    p = tf.clip_by_value(x, 0, 1) * (S - 1)
    i0 = tf.minimum(tf.cast(tf.floor(p), tf.int32), S - 2)
    f = p - tf.cast(i0, tf.float32)
    flat = tf.reshape(lut, [B, S * S * S, 3])
    out = 0.0
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                idx = (i0[..., 2] + db) * S * S + (i0[..., 1] + dg) * S + (i0[..., 0] + dr)
                v = tf.gather(flat, tf.reshape(idx, [B, -1]), batch_dims=1)
                v = tf.reshape(v, tf.shape(x))
                wb = f[..., 2:3] if db else 1 - f[..., 2:3]
                wg = f[..., 1:2] if dg else 1 - f[..., 1:2]
                wr = f[..., 0:1] if dr else 1 - f[..., 0:1]
                out = out + v * wb * wg * wr
    return out


def train(steps):
    import tensorflow as tf
    data = np.load(HERE / (f'data_{DATA}.npz' if DATA != 'all' else 'data.npz'))
    x = data['x']
    n = len(x)
    tr = x[: int(n * 0.92)]
    ytr = data['y'][: int(n * 0.92)] if 'y' in data.files else None
    net = build()
    basis = tf.Variable(np.zeros((K, S, S, S, 3), np.float32) + np.random.default_rng(1).normal(0, 1e-3, (K, S, S, S, 3)).astype(np.float32))
    ident = tf.constant(identity())
    opt = tf.keras.optimizers.Adam(2e-3)
    ckpt = CK
    ckpt.mkdir(exist_ok=True)
    if (ckpt / 'basis.npy').exists():
        basis.assign(np.load(ckpt / 'basis.npy'))
        net.load_weights(str(ckpt / 'net.weights.h5'))
        print('resumed')

    @tf.function
    def step(inp, tgt):
        with tf.GradientTape() as tape:
            w = net(inp, training=True)
            lut = ident[None] + tf.einsum('bk,ksgrc->bsgrc', w, basis)
            out = apply_lut(tf, lut, inp)
            loss = tf.reduce_mean(tf.abs(out - tgt))
            # smooth tables, and tones that don't reverse along any axis
            tv = sum(tf.reduce_mean(tf.square(d)) for d in (basis[:, 1:] - basis[:, :-1], basis[:, :, 1:] - basis[:, :, :-1], basis[:, :, :, 1:] - basis[:, :, :, :-1]))
            mono = sum(tf.reduce_mean(tf.nn.relu(-d)) for d in (lut[:, 1:] - lut[:, :-1], lut[:, :, 1:] - lut[:, :, :-1], lut[:, :, :, 1:] - lut[:, :, :, :-1]))
            total = loss + 1e-4 * tv + 10 * mono + 1e-4 * tf.reduce_mean(tf.square(w))
        vars_ = net.trainable_variables + [basis]
        opt.apply_gradients(zip(tape.gradient(total, vars_), vars_))
        return loss

    rng = np.random.default_rng(2)
    gen = pair_batches(tr, ytr, 16, rng) if ytr is not None else batches(tr, 16, rng)
    run = 0.0
    for s in range(1, steps + 1):
        inp, tgt = next(gen)
        l = float(step(tf.constant(inp), tf.constant(tgt)))
        run = l if s == 1 else 0.98 * run + 0.02 * l
        if s % 100 == 0:
            print(f'step {s} L1 {run * 255:.2f}/255', flush=True)
        if s % 500 == 0 or s == steps:
            np.save(ckpt / 'basis.npy', basis.numpy())
            net.save_weights(str(ckpt / 'net.weights.h5'))


def evaluate():
    import tensorflow as tf
    data = np.load(HERE / (f'data_{DATA}.npz' if DATA != 'all' else 'data.npz'))
    x = data['x']
    te = x[int(len(x) * 0.92):]
    yte = data['y'][int(len(x) * 0.92):] if 'y' in data.files else None
    net = build()
    net.load_weights(str(CK / 'net.weights.h5'))
    basis = np.load(CK / 'basis.npy')
    rng = np.random.default_rng(99)
    e0, e1 = [], []
    for i in range(0, min(len(te), 1600), 16):
        if yte is not None:
            inp = te[i:i + 16].astype(np.float32) / 255
            tgt = yte[i:i + 16].astype(np.float32) / 255
        else:
            tgt = te[i:i + 16, 16:144, 16:144].astype(np.float32) / 255
            inp = np.stack([spoil(t, rng) for t in tgt])
        w = net(inp, training=False).numpy()
        lut = identity()[None] + np.einsum('bk,ksgrc->bsgrc', w, basis)
        out = apply_lut(tf, tf.constant(lut, tf.float32), tf.constant(inp)).numpy()
        e0.append(np.abs(inp - tgt).mean() * 255)
        e1.append(np.abs(out - tgt).mean() * 255)
    print(f'held-out {len(te)} photos · spoiled {np.mean(e0):.2f}/255 → AI-corrected {np.mean(e1):.2f}/255')


def export():
    """The app's files: the network as TFLite (float16 weights) and the basis tables."""
    import tensorflow as tf
    net = build(IMG)  # the app feeds 128 px
    net.load_weights(str(CK / 'net.weights.h5'))
    # (Keras 3 models convert through a concrete function)
    fn = tf.function(lambda x: net(x, training=False), input_signature=[tf.TensorSpec([1, IMG, IMG, 3], tf.float32)])
    conv = tf.lite.TFLiteConverter.from_concrete_functions([fn.get_concrete_function()], net)
    conv.optimizations = [tf.lite.Optimize.DEFAULT]
    conv.target_spec.supported_types = [tf.float16]
    models = pathlib.Path(os.environ.get('EXPORT_DIR', 'export'))
    models.mkdir(parents=True, exist_ok=True)
    (models / 'scene.tflite').write_bytes(conv.convert())
    # basis: K × [b][g][r] × rgb, float32 little-endian
    np.load(CK / 'basis.npy').astype('<f4').tofile(models / 'scene_basis.bin')
    print('exported', (models / 'scene.tflite').stat().st_size, (models / 'scene_basis.bin').stat().st_size)


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'prep':
        prep()
    elif cmd == 'train':
        train(int(sys.argv[2]) if len(sys.argv) > 2 else 3000)
    elif cmd == 'export':
        export()
    else:
        evaluate()
