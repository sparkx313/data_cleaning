from __future__ import annotations

import argparse
import sys
from pathlib import Path

from csv_cleaner.cleaner import CleaningError, CleaningOptions, clean_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="csv-clean",
        description="Normalize and clean a CSV file without silently discarding malformed data.",
    )
    parser.add_argument("input", type=Path, help="source CSV file")
    parser.add_argument("-o", "--output", required=True, type=Path, help="cleaned CSV destination")
    parser.add_argument(
        "--delimiter",
        default="auto",
        help="one-character delimiter, or auto to detect comma, semicolon, tab, or pipe",
    )
    parser.add_argument("--encoding", default="utf-8-sig", help="input text encoding (default: utf-8-sig)")
    parser.add_argument("--keep-headers", action="store_false", dest="normalize_headers")
    parser.add_argument("--no-trim-values", action="store_false", dest="trim_values")
    parser.add_argument("--drop-empty-rows", action="store_true")
    parser.add_argument(
        "--drop-duplicates",
        action="store_true",
        help="remove exact duplicate data rows using a temporary on-disk index",
    )
    parser.add_argument("--report", type=Path, help="optional JSON report destination")
    parser.set_defaults(normalize_headers=True, trim_values=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    delimiter = None if args.delimiter.lower() == "auto" else args.delimiter
    options = CleaningOptions(
        delimiter=delimiter,
        encoding=args.encoding,
        normalize_headers=args.normalize_headers,
        trim_values=args.trim_values,
        drop_empty_rows=args.drop_empty_rows,
        drop_duplicates=args.drop_duplicates,
    )
    try:
        report = clean_csv(args.input, args.output, options, args.report)
    except CleaningError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Cleaned CSV written to {report.output_file}")
    print(f"Rows: {report.rows_read} read, {report.rows_written} written")
    print(
        f"Repairs: {report.short_rows_padded} short rows padded, "
        f"{report.blank_cells} blank cells"
    )
    print(
        f"Removed: {report.empty_rows_dropped} empty rows, "
        f"{report.duplicate_rows_dropped} duplicate rows"
    )
    if args.report:
        print(f"JSON report written to {args.report.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())