# Root Crawl — read less, know more

A Claude Code plugin (and a standalone script) that profiles a folder of data **locally** and
gives the AI a short report instead of the files.

| folder | files | report | reading it directly |
|---|---|---|---|
| 1,276 photos + an index CSV | 113.8 MB | **≈ 384 tokens** | ≈ 2,066,000 tokens |
| a Flutter app's `lib/` (74 source files) | — | **≈ 230 tokens** | ≈ 166,000 tokens |

### Benchmarks on real folders (`bench.py`, Windows desktop, CPU)

| folder | files | size | first run | cached | report | reading directly* | saving |
|---|---|---|---|---|---|---|---|
| a Flutter app project | 515 | 17.7 MB | 3.3 s | 0.0 s | 857 tokens | 869,433 | ×1,015 |
| numpy source + test data (CSV) | 923 | 19.0 MB | 13.4 s | 0.1 s | 1,215 | 2,712,195 | ×2,232 |
| 1,479 reference photos | 1,479 | 159.3 MB | 0.9 s | 0.1 s | 320 | 2,366,400 | ×7,395 |
| an image-pair dataset (test split) | 8,735 | 94.5 MB | 24.9 s | 0.4 s | 160 | 13,976,000 | ×87,350 |

\* text files at ~4 bytes a token; each image counted as ~1,600 tokens to look at. Real sessions
rarely read everything, but they often read far more than they need — that's the gap.

What the report covers: folders and sizes by type; photos (cameras, editing software,
resolution, dates, names that appear as originals and edits); tables (rows, columns, types,
empty %, ranges, top values, sample rows); Excel sheets; JSON shape; logs (time range, most
common lines with numbers masked); text and code (lines, tokens to read).

Then slices instead of files: `table` (filtered rows and columns), `images` (by camera /
software), `pairs`, `peek`.

## Install (Claude Code)

```
/plugin marketplace add edshot0120-stack/seedgrown
/plugin install rootcrawl@seedgrown
```

Then just ask: *"what's in C:\data\survey?"* — Claude profiles first and reads only what it needs.

## Use without Claude

```
python skills/rootcrawl/scripts/rootcrawl.py profile ./data
python skills/rootcrawl/scripts/rootcrawl.py table ./data/sales.csv --where "region=EU and total>1000" --cols date,total
```

Standard library only (Pillow / openpyxl optional). Results are cached per file in your user
cache folder (`%LOCALAPPDATA%ootcrawl` or `~/.cache/rootcrawl`, override with `ROOTCRAWL_CACHE`)
— the data folder itself is never written to. Nothing is uploaded anywhere.
