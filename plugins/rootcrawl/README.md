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

### Code (`rootcrawl.py code …`)

`code map` lists every file's classes, functions and methods with line numbers, most-referenced
first; `code symbol NAME` gives the definition and every use; `code lines FILE A B` reads just
those lines. Python by its own parser; Dart, JS/TS, Java, Kotlin, Swift, Go, Rust, C/C++/C#,
PHP and Ruby by declaration patterns.

| codebase | files | map (default) | full map | reading all files |
|---|---|---|---|---|
| a Flutter app (`lib/`, Dart) | 74 | 2,514 tokens | 10,143 (all 946 declarations) | 161,839 |

Finding where the app develops a RAW shot: `code symbol lib _developNow` (112 tokens) →
`code lines camera_screen.dart 722 760` (~300) instead of reading the 21,000-token file.

### Savings ledger (`rootcrawl.py savings`)

Every answer records what it cost and what reading the source directly would have
(conservatively: a page's plain text, not its HTML). After one test round:

| command | used | reading directly |
|---|---|---|
| profile (1,276 photos) | 387 | 2,066,384 |
| code map | 2,530 | 161,839 |
| table (filtered rows) | 80 | 26,384 |
| code symbol | 112 | 21,260 |
| code lines | 302 | 21,260 |
| web outline | 551 | 5,471 |

### Web pages (`rootcrawl.py web …`)

The outline of a page instead of its HTML or full text, then `section` / `find` / `links` on
request. On nine real pages (`bench_web.py`, tokens ≈ characters / 4):

| page | outline | page text | HTML | vs HTML |
|---|---|---|---|---|
| Wikipedia article (en) | 815 | 5,436 | 52,266 | ×64 |
| Wikipedia article (ko) | 869 | 3,589 | 53,413 | ×61 |
| Python docs page | 536 | 5,471 | 24,884 | ×46 |
| MDN reference page | 1,513* | 9,093 | 61,823 | ×41 |
| GitHub repo page | 1,194 | 1,897 | 72,588 | ×61 |
| Hacker News front page | 376 | 966 | 8,491 | ×23 |
| BBC News front page | 1,513* | 2,104 | 92,250 | ×61 |
| flutter.dev docs | 428 | 2,552 | 33,566 | ×78 |
| anthropic.com/news | 677 | 804 | 108,265 | ×160 |

\* cut at the default 1,500-token budget. Against the page's plain text the saving is ×2–×10 on
long articles and small on short pages — the outline's job there is to say *where* to look.
Pages that render their content with JavaScript come back thin; use a browser tool for those.

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
cache folder (`%LOCALAPPDATA%
ootcrawl` or `~/.cache/rootcrawl`, override with `ROOTCRAWL_CACHE`)
— the data folder itself is never written to. Nothing is uploaded anywhere.
