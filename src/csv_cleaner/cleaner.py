from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
import tempfile
import unicodedata
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


class CleaningError(ValueError):
    """Raised when the input cannot be cleaned without losing data."""


@dataclass(frozen=True)
class CleaningOptions:
    delimiter: str | None = None
    encoding: str = "utf-8-sig"
    normalize_headers: bool = True
    trim_values: bool = True
    drop_empty_rows: bool = False
    drop_duplicates: bool = False


@dataclass
class CleaningReport:
    input_file: str
    output_file: str
    generated_at: str
    delimiter: str
    rows_read: int
    rows_written: int
    short_rows_padded: int
    blank_cells: int
    empty_rows_dropped: int
    duplicate_rows_dropped: int
    headers_before: list[str]
    headers_after: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def clean_csv(
    input_path: Path,
    output_path: Path,
    options: CleaningOptions,
    report_path: Path | None = None,
) -> CleaningReport:
    source = input_path.expanduser().resolve()
    destination = output_path.expanduser().resolve()
    report_destination = report_path.expanduser().resolve() if report_path else None
    if not source.is_file():
        raise CleaningError(f"Input does not exist or is not a file: {source}")
    if source == destination:
        raise CleaningError("Input and output must be different files.")
    if report_destination in {source, destination}:
        raise CleaningError("The report path must be different from input and output.")
    if options.delimiter is not None and (
        len(options.delimiter) != 1 or options.delimiter in {"\r", "\n"}
    ):
        raise CleaningError("The delimiter must be one character.")

    temporary_output: Path | None = None
    try:
        with source.open("r", encoding=options.encoding, newline="") as input_file:
            sample = input_file.read(8192)
            if not sample:
                raise CleaningError("The input file is empty.")
            input_file.seek(0)
            delimiter = _choose_delimiter(sample, options.delimiter)
            reader = csv.reader(input_file, delimiter=delimiter, strict=True)
            try:
                original_headers = next(reader)
            except StopIteration as exc:
                raise CleaningError("The input file has no header row.") from exc
            if not original_headers or all(not cell.strip() for cell in original_headers):
                raise CleaningError("The input file has a blank header row.")

            headers = (
                normalize_headers(original_headers)
                if options.normalize_headers
                else list(original_headers)
            )
            report = CleaningReport(
                input_file=str(source),
                output_file=str(destination),
                generated_at=datetime.now(timezone.utc).isoformat(),
                delimiter=delimiter,
                rows_read=0,
                rows_written=0,
                short_rows_padded=0,
                blank_cells=0,
                empty_rows_dropped=0,
                duplicate_rows_dropped=0,
                headers_before=list(original_headers),
                headers_after=headers,
            )

            duplicate_context = (
                tempfile.TemporaryDirectory(prefix="csv-clean-")
                if options.drop_duplicates
                else nullcontext(None)
            )
            with duplicate_context as duplicate_dir:
                seen_db = None
                if options.drop_duplicates:
                    seen_db = sqlite3.connect(str(Path(duplicate_dir) / "seen.sqlite"))
                    seen_db.execute("CREATE TABLE seen (row_json TEXT PRIMARY KEY)")

                try:
                    with tempfile.NamedTemporaryFile(
                        mode="w",
                        encoding="utf-8",
                        newline="",
                        prefix=f".{destination.name}.",
                        suffix=".tmp",
                        dir=destination.parent,
                        delete=False,
                    ) as output_file:
                        temporary_output = Path(output_file.name)
                        writer = csv.writer(
                            output_file,
                            delimiter=delimiter,
                            lineterminator="\n",
                        )
                        writer.writerow(headers)

                        for row_number, row in enumerate(reader, start=2):
                            report.rows_read += 1
                            if len(row) > len(headers):
                                raise CleaningError(
                                    f"Row {row_number} has {len(row)} fields, but the header has "
                                    f"{len(headers)}. Output was not replaced."
                                )
                            if row and len(row) < len(headers):
                                report.short_rows_padded += 1
                                row.extend([""] * (len(headers) - len(row)))
                            if options.trim_values:
                                row = [value.strip() for value in row]
                            report.blank_cells += sum(value == "" for value in row)

                            if options.drop_empty_rows and all(value == "" for value in row):
                                report.empty_rows_dropped += 1
                                continue

                            if seen_db is not None:
                                row_json = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                                cursor = seen_db.execute(
                                    "INSERT OR IGNORE INTO seen(row_json) VALUES (?)", (row_json,)
                                )
                                if cursor.rowcount == 0:
                                    report.duplicate_rows_dropped += 1
                                    continue

                            writer.writerow(row)
                            report.rows_written += 1

                        output_file.flush()
                        os.fsync(output_file.fileno())
                    if seen_db is not None:
                        seen_db.commit()
                    os.replace(temporary_output, destination)
                    temporary_output = None
                finally:
                    if seen_db is not None:
                        seen_db.close()

    except CleaningError:
        raise
    except (OSError, UnicodeError, LookupError, csv.Error, sqlite3.Error) as exc:
        raise CleaningError(f"Could not clean CSV: {exc}") from exc
    finally:
        if temporary_output is not None:
            try:
                temporary_output.unlink(missing_ok=True)
            except OSError:
                pass

    if report_destination is not None:
        _write_json_report(report_destination, report.to_dict())
    return report


def normalize_headers(headers: list[str]) -> list[str]:
    normalized: list[str] = []
    used: set[str] = set()
    for index, original in enumerate(headers, start=1):
        text = unicodedata.normalize("NFKC", original).strip().casefold()
        name = re.sub(r"[^\w]+", "_", text, flags=re.UNICODE).strip("_")
        if not name:
            name = f"column_{index}"
        candidate = name
        suffix = 2
        while candidate in used:
            candidate = f"{name}_{suffix}"
            suffix += 1
        normalized.append(candidate)
        used.add(candidate)
    return normalized


def _choose_delimiter(sample: str, requested: str | None) -> str:
    if requested is not None:
        return requested
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error as exc:
        raise CleaningError(
            "Could not detect the CSV delimiter. Pass --delimiter with one of comma, semicolon, tab, or pipe."
        ) from exc


def _write_json_report(path: Path, report: dict) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as output:
            temporary = Path(output.name)
            json.dump(report, output, indent=2, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise CleaningError(f"CSV was cleaned, but the report could not be written: {exc}") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
