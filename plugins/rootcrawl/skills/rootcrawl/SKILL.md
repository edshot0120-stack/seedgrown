---
name: rootcrawl
description: Read less to know more — profile a data folder (photos, CSV/TSV, Excel, JSON/JSONL, logs, text), map a codebase (classes / functions with line numbers), or outline a web page, locally, and read the short report instead of the files, source or HTML; then take only the slices needed. Use before reading many or large data files, before exploring an unfamiliar codebase to find where something lives, and before fetching or reading a long web page.
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

## Code

Before reading source files to find where something is, map the codebase:
`rootcrawl.py code map FOLDER` — every file's classes, functions and methods with line numbers,
most-referenced first (`--files 80 --budget 8000` for the whole map). Then:
- where a name is defined and used: `rootcrawl.py code symbol FOLDER NAME`
- just the lines you need: `rootcrawl.py code lines FILE 120 180`
Helper functions defined inside other functions aren't listed in the map; `code symbol` still
finds their uses.

## Savings

`rootcrawl.py savings` shows the tokens Root Crawl used against reading the same things
directly (`savings 7` for the last week). Mention it when the user asks what it saved.

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
