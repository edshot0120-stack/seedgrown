---
name: rootcrawl
description: Profile a folder of data (photos, CSV/TSV, Excel, JSON/JSONL, logs, text, code) locally and read a short report instead of the files, then pull only the slices needed. Use before opening, listing or reading many or large data files — "analyse this dataset", "what's in this folder", "find the photos from camera X", "rows where …" — to save tokens.
---

# Root Crawl

Read data the cheap way: a local script profiles the files once (cached), and you read its
report (usually 300–3,000 tokens) instead of the files themselves (often hundreds of
thousands). Then you take only the slices you need.

The script is `scripts/rootcrawl.py` in this skill's base directory. It needs Python 3; Pillow
(photo EXIF) and openpyxl (xlsx) are used when installed. Nothing leaves the machine.

## Steps

1. **Profile first.** Before listing, globbing or reading data files in a folder, run:
   `python "<skill base dir>/scripts/rootcrawl.py" profile "<folder>"`
   Add `--budget 1500` for a shorter report. A second run reads only changed files.
2. **Answer from the report** when it's enough (counts, columns, types, ranges, cameras,
   dates, duplicates, pairs).
3. **Take slices, not files**, when you need specifics:
   - table rows: `rootcrawl.py table FILE --cols a,b --where "price>10 and city~seoul" --limit 20`
     (`=`, `!=`, `>`, `<`, `>=`, `<=`, `~` contains; headerless files use col0, col1 …)
   - photos by camera / software: `rootcrawl.py images FOLDER --make SONY --software Lightroom`
   - same-name files in different places or formats (originals ↔ edits, RAW ↔ JPEG):
     `rootcrawl.py pairs FOLDER`
   - the first lines of a text file: `rootcrawl.py peek FILE --lines 40`
4. Open a whole file only when a slice can't answer the question, and say why.

## Notes

- The report ends with the token cost of reading everything directly; mention the saving
  when it's large.
- The cache lives in the user's cache folder, never in the data folder; `--refresh` rebuilds it.
- `profile FILE` profiles a single file.
- Only profile folders the user pointed you to or that the task clearly needs.
