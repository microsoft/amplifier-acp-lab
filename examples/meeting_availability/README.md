# Common meeting availability (standalone example)

Python 3.11+; standard library only. From the repository root:

```sh
python3 examples/meeting_availability/availability.py examples/meeting_availability/example.csv --required Ada Bo
# start,end
# 2026-01-01T09:30:00Z,2026-01-01T10:30:00Z
python3 examples/meeting_availability/availability.py examples/meeting_availability/example.csv --required Ada Bo --minutes 30
python3 -m unittest discover -s examples/meeting_availability -p 'test_*.py' -v
```

Names and availability are fictional. Use `-` instead of a file to read stdin.
The default minimum is **45 minutes**, per the updated exercise requirement;
`--minutes 30` overrides it. Minutes must be a positive integer.

Input has the exact header `person,start,end`. Timestamps use
`YYYY-MM-DDTHH:MM[:SS[.ffffff]]Z` or an explicit `+HH:MM`/`-HH:MM` offset.
Invalid dates, naive timestamps, malformed rows, blank names, and an end before
its start (in absolute time) are errors. All rows are validated, including rows
for non-required people. Names are case-sensitive; surrounding whitespace in
CSV person names is stripped. Quote names containing commas normally in CSV,
and quote names containing spaces in shell arguments.

Availability is a union per person: overlapping and adjacent intervals are
merged **before** intersection or minimum-duration filtering. Output contains
sorted maximal common windows, not fixed-length meeting slots, normalized to
UTC with `Z`. Durations equal to the minimum qualify. Zero-length intervals
are accepted but contribute no availability. Duplicate rows/required names do
not change results. Missing required people or empty intersections produce only
`start,end` and exit 0. Invalid input/options exit 2 with an error on stderr and
no result CSV. At least one required participant is necessary.

This example does not infer timezones or expand recurring schedules, resolve
local DST ambiguity, or integrate with calendars. Supply explicit offsets for
each timestamp. It adds no dependencies or integration to the main lab package.
