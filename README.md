# Seed Grown

Small local tools and micro AIs that learn from the data where they're planted.

## ⭐ Root Crawl — read less, know more (Claude Code plugin)

Your AI reads a **short report instead of files, source code or HTML** — then only the slices it needs.

![Root Crawl savings](docs/img/rootcrawl-savings.png)

```
/plugin marketplace add edshot0120-stack/seedgrown
/plugin install rootcrawl@seedgrown
```

| what | how | saved (measured) |
|---|---|---|
| data folders (photos, CSV/Excel, JSON, logs) | `profile` → `table` / `images` / `pairs` / `peek` | 1,276 photos: 387 tokens instead of ~2 M |
| codebases (12 languages) | `code map` → `code symbol` → `code lines` | finding one function: 410 instead of 21,000 |
| web pages | `web outline` → `section` / `find` / `links` | 7–35× vs the page text, 23–160× vs HTML |
| what it saved you | `savings` | running total of every answer |

Runs locally, standard-library Python, nothing uploaded; caches outside your data folders.
Tested on 1,000,000-row CSVs, locked files, Korean CP949 files, nine real websites —
[details and limits](plugins/rootcrawl).

## Micro AIs: why a judge they can't fool

Training a small model is easy. **Knowing whether it actually helps is the hard part.** While building
`lut` we trained eight models; several looked clearly better on synthetic tests and on
distribution statistics, and were in fact worse on real photos — one tinted everything warm, another
lifted the blacks to flatten contrast. Both "won" on the numbers.

What survived was a judge built to be hard to fool:

| judge | what it checks | what it catches |
|---|---|---|
| **paired** (`judge2.py`) | the same scene shot by a phone and by a DSLR; ΔE (OkLab) of the corrected phone shot to the DSLR's | anything that only matches statistics |
| **contrast kept** | tonal range (p98 − p2) on modern phone photos | flattening / lifted blacks |
| **fidelity** (`realscore.py`) | neutrals gaining colour; hue rotation on colourful pixels | colour casts |
| **clipping** | extra pixels at pure black / white | lost detail |
| **blind A/B** (`blind.py`) | side-by-side sheets, sides randomised, key opened after judging | anything the numbers miss |

## The `lut` module

A ~100k-parameter CNN looks at the photo once (128 px) and weights 8 learned 17³ basis tables into one
table for that photo (after Zeng et al., *Learning Image-adaptive 3D Lookup Tables*, 2020). The table,
not the network, touches the pixels — in a GPU shader — so the cost is one tiny inference per photo.
Exported as TFLite: **225 KB** model + **472 KB** basis tables.

In Tintly the model sets **lightness only** (colour is kept as shot); a hand-made "camera rendering"
pass (`camera_feel.py`) and a finishing stage (`finish.py`: smoothing, detail guard, skin guard, soft
gamut, tone order) give the colour its density.

### Results (see [docs/RESULTS.md](docs/RESULTS.md))

| method | ΔE to DSLR ↓ | contrast kept | clipping | grey cast | hue shift |
|---|---|---|---|---|---|
| phone as shot | 9.22 | 1.000 | 0.97 % | 0.50 | 0.0° |
| hand-made camera rendering | 10.03 | 1.053 | 0.82 % | 0.50 | 0.5° |
| **AI (lightness) + hand-made** | **8.12** | 1.158 | **0.13 %** | 0.50 | 0.5° |
| AI trained unpaired (rejected) | 13.44 | 0.977 | 0.00 % | 0.14 | 1.3° |

Blind A/B on 23 modern phone photos: **AI + hand-made preferred 13 : 4** (6 ties).

## Use

```bash
pip install -r requirements.txt
export SEEDGROWN_DATA=/path/to/data      # layout: docs/DATA.md
DATA=dped python seedgrown/lut/train.py prep
TAG=dped DATA=dped python seedgrown/lut/train.py train 8000
TAG=dped DATA=dped python seedgrown/lut/train.py eval
TAGS=dped python seedgrown/lut/judge2.py
TAG=dped DATA=dped python seedgrown/lut/train.py export   # → export/scene.tflite, scene_basis.bin
```

Everything runs offline on a CPU (an experiment is ~1 h on a desktop CPU).

## Data

No photos are redistributed here. [docs/DATA.md](docs/DATA.md) lists every source used, its licence
status and how to obtain it.

## Roadmap

`lut` is the first *seed* (vision). The plan is the same loop for other senses — **Root Crawl**
(profile authorised local data) → **Grow** (train) → **Prune** (judge, keep only what wins) →
**Bloom** (deploy on device) — with people approving every step that changes anything.

## Licence

**AGPL-3.0** for this code. Using it inside a product that isn't itself released under the AGPL
needs a commercial licence — contact the author. See [LICENSE](LICENSE).

## About

Made for Tintly, a camera and colour app. Research code: issues and ideas are welcome; support is
best-effort.

---

## 한국어 요약

**Seed Grown**은 폰이나 오프라인 PC에서 돌아가는 수백 KB짜리 **마이크로 AI**를 만들고, **속일 수 없는 심판**으로
검증된 것만 내보내는 연구 코드입니다. 첫 모듈 `lut`는 폰 사진의 밝기·대비를 카메라처럼 바꾸는 장면 적응형 색 모델로,
사진 앱 Tintly에 들어갔습니다.

- 8개 모델을 학습했고, 통계 지표로는 이겼지만 실제로는 색을 물들이거나 대비를 낮춘 모델들을 심판이 걸러냈습니다.
- 채택된 모델: 같은 장면 DSLR 비교 10.0 → 8.1, 클리핑 0.82% → 0.13%, 블라인드 비교 13 : 4 승.
- 사진은 재배포하지 않으며 출처와 라이선스는 `docs/DATA.md`에 정리했습니다.
- **Root Crawl 플러그인**: 데이터 폴더를 로컬에서 먼저 요약해, AI가 파일 대신 짧은 보고서만 읽게 합니다(사진 1,276장 ≈ 384토큰).
- 라이선스: AGPL-3.0, 상업 제품에 넣으려면 별도 상업 라이선스.
