"""What separates a camera's rendering from a phone's, measured over many photos of each:
tone (lightness percentiles), chroma by lightness band and by hue, and fine vs mid local
contrast (sharpening / local tone mapping). Prints the differences camera − phone.

    python tools/looklab/camphone.py
"""
import os
import pathlib
import sys

import cv2
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from fit_style import oklab  # noqa: E402

REF = pathlib.Path(os.environ.get('SEEDGROWN_DATA', 'data'))  # see docs/DATA.md
CAM = [REF / 'cams', REF / 'scan'] + [REF / d for d in ['canon_eos_r5', 'sony_a7r_v', 'leica_m10', 'nikon_z7_ii', 'fuji_xt5', 'hasselblad_x1d_ii_50c', 'ricoh_gr_iii', 'fujiofficial']]
PHONE = [REF / 'phonecmp', REF / 'commons']
LB = np.linspace(0, 1, 6)
HB = 12


def files(dirs, cap=700):
    out = []
    for d in dirs:
        out += [p for p in d.rglob('*') if p.suffix.lower() in ('.jpg', '.jpeg')]
    rng = np.random.default_rng(1)
    rng.shuffle(out)
    return out[:cap]


def measure(paths):
    Ls, C_by_L, C_by_H, fine, mid = [], np.zeros((5, 2)), np.zeros((HB, 2)), [], []
    for p in paths:
        im = cv2.imread(str(p), cv2.IMREAD_REDUCED_COLOR_4)
        if im is None:
            continue
        h, w = im.shape[:2]
        s = 768 / max(h, w)
        im = cv2.resize(im, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
        rgb = im[..., ::-1].astype(np.float32) / 255
        lab = oklab(rgb.reshape(-1, 3))
        L = lab[:, 0]
        C = np.hypot(lab[:, 1], lab[:, 2])
        H = (np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360 / 360 * HB).astype(int) % HB
        Ls.append(np.percentile(L, np.arange(1, 100)))
        bi = np.clip(np.digitize(L, LB) - 1, 0, 4)
        for b in range(5):
            m = bi == b
            if m.sum() > 50:
                C_by_L[b] += (C[m].mean(), 1)
        m = C > 0.03
        for b in range(HB):
            mm = m & (H == b)
            if mm.sum() > 50:
                C_by_H[b] += (C[mm].mean(), 1)
        y = L.reshape(rgb.shape[:2])
        b1 = cv2.GaussianBlur(y, (0, 0), 1.0)
        b4 = cv2.GaussianBlur(y, (0, 0), 6.0)
        fine.append(np.abs(y - b1).mean())
        mid.append(np.abs(b1 - b4).mean())
    return np.mean(Ls, 0), C_by_L[:, 0] / np.maximum(C_by_L[:, 1], 1), C_by_H[:, 0] / np.maximum(C_by_H[:, 1], 1), np.median(fine), np.median(mid), len(Ls)


def main():
    c = measure(files(CAM))
    p = measure(files(PHONE))
    print(f'camera n={c[5]}  phone n={p[5]}')
    print('lightness percentiles (5,10,25,50,75,90,95,99):')
    for q in [5, 10, 25, 50, 75, 90, 95, 98]:
        print(f'  p{q:2d}  cam {c[0][q - 1]:.3f}  phone {p[0][q - 1]:.3f}  diff {c[0][q - 1] - p[0][q - 1]:+.3f}')
    print('chroma by L band:', ' '.join(f'{a:.3f}/{b:.3f}' for a, b in zip(c[1], p[1])))
    print('chroma by hue (30° bins from 0=pinkish-red):', ' '.join(f'{a / max(b, 1e-6):.2f}' for a, b in zip(c[2], p[2])))
    print(f'fine detail cam {c[3]:.4f} phone {p[3]:.4f} ratio {c[3] / p[3]:.2f}; mid contrast cam {c[4]:.4f} phone {p[4]:.4f} ratio {c[4] / p[4]:.2f}')
    np.savez(pathlib.Path(__file__).parent / 'out' / 'camphone.npz', cL=c[0], pL=p[0], cCL=c[1], pCL=p[1], cCH=c[2], pCH=p[2])


if __name__ == '__main__':
    main()
