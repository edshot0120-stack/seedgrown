# Data card

**No photos are redistributed in this repository.** Below is what the experiments used, its licence
status, and how to rebuild the layout under `$SEEDGROWN_DATA`.

| folder | what | count | licence / status | how to get it |
|---|---|---|---|---|
| `dped/` | DPED: phone (iPhone 3GS, BlackBerry Passport, Sony Xperia Z) ↔ Canon 70D patches of the same spot | 160k pairs per phone (24k used) | no licence text on the project page; research dataset — **check before commercial use** | https://dped-photos.vision.ee.ethz.ch/ |
| `cams/`, `scan/`, per-camera folders | straight-out-of-camera sample JPEGs (Canon, Sony, Leica, Nikon, Fujifilm, Hasselblad, Ricoh) | ~470 | makers' / reviewers' samples and Wikimedia Commons files — each under its own terms; **not redistributable here** | collect your own; any OOC camera JPEGs work |
| `commons/` | phone photos (iPhone / Galaxy) from Wikimedia Commons | ~800 | per-file CC licences | Commons categories by device |
| `phonecmp/` | modern phone photos | ~550 | various; reference only | any recent phone photos |
| `judge_camera/` | **independent judge**: camera JPEGs no model trained on | ~300 | the author's own photos — private | use your own camera's JPEGs |

Rules followed:

- Training material is measured or learned from, never shipped.
- The judge's photos are never used for training.
- Anyone can rebuild an equivalent set; the method doesn't depend on our exact files.

## Model provenance

The model used in Tintly (`TAG=dped`) was trained on DPED pairs. Because DPED states no licence,
the plan is to retrain on our own phone ↔ camera pairs before wider commercial use.
