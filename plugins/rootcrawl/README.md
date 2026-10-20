# Root Crawl — read less, know more

A Claude Code plugin (and a standalone script) that profiles a folder of data **locally** and
gives the AI a short report instead of the files.

| folder | files | report | reading it directly |
|---|---|---|---|
| 1,276 photos + an index CSV | 113.8 MB | **≈ 384 tokens** | ≈ 2,066,000 tokens |
| a Flutter app's `lib/` (74 source files) | — | **≈ 230 tokens** | ≈ 166,000 tokens |

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

Standard library only (Pillow / openpyxl optional). Results are cached per file in
`.rootcrawl/`; nothing is uploaded anywhere.
