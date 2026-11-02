"""Run: python -m unittest discover -s outlook/examples -p test_seven_day.py"""
import tempfile
import unittest
from pathlib import Path

import numpy as np
from seven_day import (SAMPLE, county_statistics, flag_names, open_sample,
                       point_forecast, schedule, select_update, validate)


class SevenDayTests(unittest.TestCase):
    def setUp(self):
        with open_sample() as source:
            self.ds = source.isel(y=slice(0, 2), x=slice(0, 2)).load()

    def test_july_local_issuances_and_fixed_target(self):
        validate(self.ds)
        times = schedule(self.ds)
        self.assertEqual(times.issued_PDT.dt.day.tolist(), list(range(8, 15)))
        self.assertTrue((times.issued_PDT.dt.hour == 20).all())
        self.assertTrue((times.valid_start_PDT.dt.day == 15).all())
        self.assertTrue((times.valid_start_PDT.dt.hour == 5).all())
        self.assertEqual(times.forecast_day.tolist(), list(range(7, 0, -1)))

    def test_incomplete_update_rejected(self):
        self.ds.complete.values[3] = False
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            select_update(self.ds, 3)

    def test_invalid_update_rejected(self):
        for index in (-1, 7):
            with self.assertRaises(ValueError):
                select_update(self.ds, index)

    def test_future_weather_rejected(self):
        self.ds.weather_cycle.values[0] = np.datetime64('2099-01-01')
        with self.assertRaisesRegex(ValueError, 'later than issuance'):
            validate(self.ds)

    def test_varying_target_rejected(self):
        self.ds.valid_start.values[1] += np.timedelta64(24, 'h')
        with self.assertRaises(ValueError):
            validate(self.ds)

    def test_wrong_leads_rejected(self):
        self.ds.forecast_day.values[0] = 6
        with self.assertRaises(ValueError):
            validate(self.ds)

    def test_zero_score_and_unavailable(self):
        self.ds.outlook_index.values[:] = 0
        self.ds.outlook_category.values[:] = 1
        self.ds.outlook_category.values[1] = 0
        result = point_forecast(self.ds, float(self.ds.latitude[0, 0]), float(self.ds.longitude[0, 0]))
        self.assertEqual(result['index'][0], 0)
        self.assertTrue(np.isnan(result['index'][1]))

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

    def test_matches_presentation_county_and_crosswhite(self):
        with open_sample() as ds:
            actual = county_statistics(ds).county_high_or_above_pct
            expected = [40.0, 36.4, 2.8, 1.8, 1.2, 22.6, 52.0]
            np.testing.assert_allclose(actual, expected, atol=.05, rtol=0)
            values = point_forecast(ds, 44.803333, -120.199167)
            self.assertEqual(values.category_code.tolist(), [5, 5, 3, 3, 3, 4, 4])


if __name__ == '__main__':
    unittest.main()
