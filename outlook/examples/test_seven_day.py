"""Run: python -m unittest discover -s outlook/examples -p test_seven_day.py"""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from seven_day import SAMPLE, flag_names, open_sample, point_forecast, select_day, validate


class SevenDayTests(unittest.TestCase):
    def setUp(self):
        with open_sample() as source:
            self.ds = source.isel(y=slice(0, 2), x=slice(0, 2)).load()

    def test_complete_seven_day_sample(self):
        validate(self.ds)
        self.assertEqual(self.ds.sizes['forecast_day'], 7)

    def test_incomplete_lead_rejected(self):
        self.ds.complete.values[3] = False
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            select_day(self.ds, 4)

    def test_invalid_lead_rejected(self):
        for day in (0, 8, -1):
            with self.assertRaises(ValueError):
                select_day(self.ds, day)

    def test_future_weather_rejected(self):
        self.ds.weather_cycle.values[0] = np.datetime64('2099-01-01')
        with self.assertRaisesRegex(ValueError, 'later than issuance'):
            validate(self.ds)

    def test_nonconsecutive_windows_rejected(self):
        self.ds.valid_start.values[1] += np.timedelta64(1, 'h')
        with self.assertRaises(ValueError):
            validate(self.ds)

    def test_zero_score_preserved_and_unavailable_masked(self):
        self.ds.outlook_index.values[:] = 0
        self.ds.outlook_category.values[:] = 1
        self.ds.outlook_category.values[1] = 0
        lat, lon = float(self.ds.latitude[0, 0]), float(self.ds.longitude[0, 0])
        result = point_forecast(self.ds, lat, lon)
        self.assertEqual(result['index'][0], 0)
        self.assertTrue(np.isnan(result['index'][1]))
        self.assertEqual(result.category[1], 'Unavailable')

    def test_outside_region_rejected(self):
        with self.assertRaises(ValueError):
            point_forecast(self.ds, 0, 0)

    def test_quality_flags(self):
        self.assertEqual(len(flag_names(self.ds, 64 | 16)), 2)

    def test_checksum_rejects_altered_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / SAMPLE.name
            path.write_bytes(b'changed')
            (path.parent / 'manifest.json').write_bytes((SAMPLE.parent / 'manifest.json').read_bytes())
            with self.assertRaisesRegex(ValueError, 'checksum'):
                open_sample(path)


if __name__ == '__main__':
    unittest.main()
