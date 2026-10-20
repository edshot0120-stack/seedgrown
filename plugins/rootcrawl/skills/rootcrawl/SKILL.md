---
name: rootcrawl
description: Profile a folder of data (photos, CSV/TSV, Excel, JSON/JSONL, logs, text, code) or a web page locally and read a short report instead of the raw files or HTML, then pull only the slices needed. Use before opening, listing or reading many or large data files, or before fetching / reading a long web page — "analyse this dataset", "what's in this folder", "rows where …", "what does this page say about X" — to save tokens.
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

## Web pages

Instead of fetching a page's HTML (often 30k–100k tokens) or its full text, read its outline
(title, headings with each section's opening, tables, forms, the links in the content):
`rootcrawl.py web outline URL` (`--budget 800` for less). Then:
- one section in full: `rootcrawl.py web section URL "heading text"`
- where words appear: `rootcrawl.py web find URL "words"`
- links, filtered: `rootcrawl.py web links URL --match pricing`
A saved `.html` file works in place of the URL. Pages are cached for an hour. Pages that
build their content with JavaScript may come back thin; then use a browser tool.

## Notes

- The report ends with the token cost of reading everything directly; mention the saving
  when it's large.
- The cache lives in the user's cache folder, never in the data folder; `--refresh` rebuilds it.
- `profile FILE` profiles a single file.
- Only profile folders the user pointed you to or that the task clearly needs.
