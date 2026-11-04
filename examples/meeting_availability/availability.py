"""Find maximal common availability using only the Python standard library."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import re
import sys
from typing import TextIO

Window = tuple[datetime, datetime]
# Deliberately require a date, time (seconds optional), and explicit UTC offset.
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})\Z")


def timestamp(value: str) -> datetime:
    if not STAMP.fullmatch(value):
        raise ValueError(f"invalid timezone-aware ISO timestamp: {value!r}")
    try:
        if value[-6:-5] in ("+", "-"):
            if int(value[-5:-3]) > 23 or int(value[-2:]) > 59:
                raise ValueError("invalid offset")
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"invalid timezone-aware ISO timestamp: {value!r}") from exc


def read_availability(source: TextIO) -> dict[str, list[Window]]:
    reader = csv.DictReader(source, strict=True)
    if reader.fieldnames != ["person", "start", "end"]:
        raise ValueError("CSV header must be person,start,end")
    result: dict[str, list[Window]] = {}
    try:
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"line {reader.line_num}: expected three fields")
            person = row["person"].strip()
            if not person:
                raise ValueError(f"line {reader.line_num}: person must not be empty")
            start, end = timestamp(row["start"]), timestamp(row["end"])
            if end < start:
                raise ValueError(f"line {reader.line_num}: end precedes start")
            result.setdefault(person, []).append((start, end))
    except csv.Error as exc:
        raise ValueError(f"line {reader.line_num}: malformed CSV: {exc}") from exc
    return result


def merge(windows: list[Window]) -> list[Window]:
    result: list[Window] = []
    for start, end in sorted(windows):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def common_windows(availability: dict[str, list[Window]], required: list[str],
                   minimum: timedelta = timedelta(minutes=45)) -> list[Window]:
    if not required or any(not person.strip() for person in required):
        raise ValueError("at least one nonempty required participant is needed")
    if minimum <= timedelta(0):
        raise ValueError("minimum duration must be positive")
    people = list(dict.fromkeys(required))
    common = merge(availability.get(people[0], []))
    for person in people[1:]:
        other = merge(availability.get(person, []))
        intersections: list[Window] = []
        i = j = 0
        while i < len(common) and j < len(other):
            a, b = common[i], other[j]
            start, end = max(a[0], b[0]), min(a[1], b[1])
            if start < end:
                intersections.append((start, end))
            if a[1] <= b[1]:
                i += 1
            else:
                j += 1
        common = merge(intersections)
    return [(start, end) for start, end in common if end - start >= minimum]


def positive_minutes(value: str) -> int:
    try:
        minutes = int(value)
        if minutes <= 0:
            raise ValueError
        timedelta(minutes=minutes)
        return minutes
    except (ValueError, OverflowError) as exc:
        raise argparse.ArgumentTypeError("minutes must be a positive integer in range") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", help="CSV path, or - for stdin")
    parser.add_argument("--required", nargs="+", required=True, metavar="PERSON")
    parser.add_argument("--minutes", type=positive_minutes, default=45)
    args = parser.parse_args(argv)
    try:
        if args.csv_file == "-":
            data = read_availability(sys.stdin)
        else:
            with open(args.csv_file, encoding="utf-8", newline="") as source:
                data = read_availability(source)
        windows = common_windows(data, args.required, timedelta(minutes=args.minutes))
    except (ValueError, OSError, UnicodeError) as exc:
        parser.error(str(exc))
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["start", "end"])
    for start, end in windows:
        writer.writerow([start.isoformat().replace("+00:00", "Z"),
                         end.isoformat().replace("+00:00", "Z")])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
