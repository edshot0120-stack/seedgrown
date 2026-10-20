# `lut`: eight experiments

Goal: a micro AI that moves a **modern phone photo's** rendering toward a dedicated camera's
(less HDR flatness, real blacks, no clipping) without tinting it.

All numbers are on photos no model trained on. Lower is better unless noted.

## The experiments

| # | training data | how | synthetic test | real phone photos | verdict |
|---|---|---|---|---|---|
| 1 | 3,142 mixed photos | spoil (random exposure / WB / tone / saturation) → restore | 26.9 → 18.2 | brighter and flatter | rejected |
| 2 | 322 camera photos (×5 crops) | spoil like a phone (HDR flattening, lifted mids) → restore | 22.3 → 14.0 | barely moved | rejected |
| 3 | 790 camera photos | as 2 | 14.0 | worse than as-shot | rejected |
| 4 | **DPED: 24k real phone ↔ DSLR patch pairs** | paired L1 | 23.8 → 20.4 | closer to DSLR, but hue shift 5° | **kept for lightness** |
| 5 | 108 camera JPEG ↔ the photographer's Lightroom edit | paired | 16.3 → 15.3 (unseen) | right direction, too little data | future |
| 6 | 4k phone crops vs 3.9k camera crops, unpaired | LSGAN + stay-close | — | "won" every statistic by tinting warm | rejected (grey cast 3.6, hue 6.8°) |
| 7 | as 6, camera JPEGs straight out of camera | + neutral and hue losses | — | safe, no gain | rejected |
| 8 | as 7 | + weaker stay-close | — | "won" tone by lifting blacks | rejected (ΔE 13.4, contrast 0.98) |

## The judge that settled it (`judge2.py`)

450 held-out DPED pairs (same spot, phone and DSLR) + 120 modern phone photos.

| method | ΔE to DSLR | contrast kept ↑ | clipping | grey cast | hue shift |
|---|---|---|---|---|---|
| as shot | 9.22 | 1.000 | 0.97 % | 0.50 | 0.0° |
| hand-made camera rendering | 10.03 | 1.053 | 0.82 % | 0.50 | 0.5° |
| AI #4 | 7.49 | 1.086 | 0.39 % | 0.58 | 5.0° |
| **AI #4 lightness + hand-made** | **8.12** | **1.158** | **0.13 %** | **0.50** | **0.5°** |
| AI #8 | 13.44 | 0.977 | 0.00 % | 0.14 | 1.3° |
| AI #7 | 9.70 | 1.043 | 1.63 % | 0.10 | 0.9° |

## Blind A/B

`blind.py`: 24 modern phone photos spread from dark to bright, each rendered by the hand-made pass
and by AI #4 lightness + hand-made, sides randomised, key opened only after judging (by a vision
model; a human panel is the next step).

| | AI + hand-made | hand-made | tie |
|---|---|---|---|
| real scenes | 9 | 4 | 1 |
| flat greys and charts | 4 | 0 | 5 |
| **total** | **13** | **4** | **6** |

## Lessons

1. **Synthetic degradations don't transfer.** Models trained to undo our idea of a phone's processing
   did nothing useful to real phone photos.
2. **Distribution statistics can be gamed.** Matching camera-photo statistics was won by tinting
   (exp. 6) and by flattening (exp. 8). Neither shows in the statistics; both show at once to the eye.
3. **Same-scene pairs and fidelity checks can't be gamed that way**, and agreed with the blind test.
4. **Let the model do what it's good at.** The paired model's lightness was right and its colour was
   off; using it for lightness only beat both it and the hand-made pass.
