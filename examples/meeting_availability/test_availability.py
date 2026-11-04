"""Run with unittest discovery; no third-party dependencies."""
import io
from pathlib import Path
import subprocess
import sys
import unittest
from datetime import timedelta
from availability import common_windows, read_availability, timestamp


def load(rows):
    return read_availability(io.StringIO('person,start,end\n' + rows))


class AvailabilityTests(unittest.TestCase):
    def test_maximal_union_offsets_unsorted(self):
        data = load('Ada,2026-01-01T11:00Z,2026-01-01T12:00Z\n'
                    'Ada,2026-01-01T09:00Z,2026-01-01T10:30Z\n'
                    'Ada,2026-01-01T10:00Z,2026-01-01T11:00Z\n'
                    'Bo,2026-01-01T11:30+02:00,2026-01-01T13:30+02:00\n')
        self.assertEqual(common_windows(data, ['Ada', 'Bo']), [
            (timestamp('2026-01-01T09:30Z'), timestamp('2026-01-01T11:30Z'))])

    def test_default_45_explicit_30_sorted_windows(self):
        data = load('Ada,2026-01-01T09:00Z,2026-01-01T12:00Z\n'
                    'Bo,2026-01-01T11:00Z,2026-01-01T11:45Z\n'
                    'Bo,2026-01-01T10:00Z,2026-01-01T10:29Z\n'
                    'Bo,2026-01-01T09:00Z,2026-01-01T09:30Z\n')
        windows = common_windows(data, ['Ada', 'Bo'], timedelta(minutes=30))
        self.assertEqual(windows, [
            (timestamp('2026-01-01T09:00Z'), timestamp('2026-01-01T09:30Z')),
            (timestamp('2026-01-01T11:00Z'), timestamp('2026-01-01T11:45Z'))])
        self.assertEqual(common_windows(data, ['Ada', 'Bo']), windows[1:])

    def test_empty_missing_touching(self):
        data = load('Ada,2026-01-01T09:00Z,2026-01-01T10:00Z\n'
                    'Bo,2026-01-01T10:00Z,2026-01-01T11:00Z\n')
        for people in [['Ada', 'Bo'], ['Ada', 'Missing']]:
            self.assertEqual(common_windows(data, people), [])
        self.assertEqual(common_windows({}, ['Ada']), [])

    def test_single_duplicate_zero_length(self):
        data = load('Ada,2026-01-01T09:00Z,2026-01-01T10:00Z\n'
                    'Ada,2026-01-01T09:00Z,2026-01-01T10:00Z\n'
                    'Ada,2026-01-01T11:00Z,2026-01-01T11:00Z\n')
        self.assertEqual(len(common_windows(data, ['Ada', 'Ada'])), 1)

    def test_merge_before_duration_filter(self):
        data = load('Ada,2026-01-01T09:00Z,2026-01-01T09:20Z\n'
                    'Ada,2026-01-01T09:20Z,2026-01-01T09:40Z\n')
        self.assertEqual(len(common_windows(data, ['Ada'], timedelta(minutes=30))), 1)

    def test_three_people_fractional_seconds(self):
        data = load('Ada,2026-01-01T09:00Z,2026-01-01T12:00Z\n'
                    'Bo,2026-01-01T09:30Z,2026-01-01T11:00Z\n'
                    'Cy,2026-01-01T10:00:00.500Z,2026-01-01T12:00Z\n')
        self.assertEqual(common_windows(data, ['Ada', 'Bo', 'Cy']), [
            (timestamp('2026-01-01T10:00:00.500Z'), timestamp('2026-01-01T11:00Z'))])

    def test_invalid_timestamps(self):
        for value in ['2026-01-01', '2026-01-01T09:00', 'garbage',
                      '2026-02-30T09:00Z', '2026-01-01T09:00+00:60',
                      '2026-01-01T25:00Z', '2026-01-01T09:00+24:00']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                timestamp(value)

    def test_end_before_start_absolute_time(self):
        with self.assertRaises(ValueError):
            load('Ada,2026-01-01T10:00Z,2026-01-01T10:30+01:00\n')

    def test_bad_csv_and_nonrequired_rows(self):
        for text in ['', 'name,start,end\n', 'person,start,end\nAda,a\n',
                     'person,start,end\nAda,a,b,c\n', 'person,start,end\nOther,x,y\n',
                     'person,start,end\n"Ada,a,b\n',
                     'person,start,end\n ,2026-01-01T09:00Z,2026-01-01T10:00Z\n']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                read_availability(io.StringIO(text))

    def test_invalid_options(self):
        for people, duration in [([], 45), ([''], 45), (['Ada'], 0), (['Ada'], -1)]:
            with self.assertRaises(ValueError):
                common_windows({}, people, timedelta(minutes=duration))

    def cli(self, *args, input=None):
        return subprocess.run([sys.executable, str(Path(__file__).with_name('availability.py')),
                               *args], input=input, capture_output=True, text=True)

    def test_cli_example_and_empty(self):
        example = str(Path(__file__).with_name('example.csv'))
        result = self.cli(example, '--required', 'Ada', 'Bo')
        self.assertEqual((result.returncode, result.stdout),
                         (0, 'start,end\n2026-01-01T09:30:00Z,2026-01-01T10:30:00Z\n'))
        result = self.cli(example, '--required', 'Missing')
        self.assertEqual((result.returncode, result.stdout), (0, 'start,end\n'))

    def test_cli_default_and_override(self):
        rows = 'person,start,end\nAda,2026-01-01T09:00Z,2026-01-01T09:30Z\n'
        self.assertEqual(self.cli('-', '--required', 'Ada', input=rows).stdout, 'start,end\n')
        result = self.cli('-', '--required', 'Ada', '--minutes', '30', input=rows)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, 'start,end\n2026-01-01T09:00:00Z,2026-01-01T09:30:00Z\n')

    def test_cli_failures(self):
        for args in [[], ['--minutes', '0'], ['--minutes', 'huge'], ['--minutes', '-1']]:
            result = self.cli('-', '--required', 'Ada', *args, input='person,start,end\nAda,x,y\n')
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
        self.assertEqual(self.cli('nonexistent.csv', '--required', 'Ada').returncode, 2)


if __name__ == '__main__':
    unittest.main()
