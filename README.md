# CSV Cleaner

CSV Cleaner is a Python command-line utility for repeatable CSV cleanup. It normalizes column names, trims cell whitespace, pads short records, and can optionally remove empty or duplicate rows.

## Install

Requires Python 3.10 or newer and has no runtime dependencies.

~~~powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
~~~

~~~sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
~~~

## Use

~~~sh
csv-clean messy.csv --output cleaned.csv
csv-clean messy.csv --output cleaned.csv --drop-empty-rows --drop-duplicates --report cleaning-report.json
csv-clean data.txt --output cleaned.csv --delimiter ";"
~~~

The input and output must be different files. Headers are normalized by default to lowercase snake_case, and duplicate or blank header names are made unique. Cell whitespace is trimmed by default. Short rows are padded with empty cells. Empty and duplicate row removal is opt-in.

Rows wider than the header cause the command to stop and leave the destination untouched, so extra fields are never silently discarded. Malformed CSV quoting, an unrecognized delimiter, or an unreadable file also produces an error. Use --delimiter to set a one-character separator if automatic detection is ambiguous.

Duplicate removal uses a temporary SQLite index on disk, allowing larger files without holding every row in memory. CSV values are otherwise streamed. The optional JSON report records row counts, repairs, removed rows, and header changes. Blank text remains blank; the tool does not infer null markers, change data types, or guess how values should be rewritten.