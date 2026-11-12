"""Regression checks for the original false-success problem and date-line handling."""
import math
import unittest

from T03_approach_validation import validate_feature
from validation_common import coordinate_pair, distance_nm


def feature(points=None, length=10, units='naut'):
    return {'type': 'Feature', 'geometry': {'type': 'LineString',
            'coordinates': points if points is not None else [[4, 52], [5, 53]]},
            'properties': {'length': length, 'units': units}}


class RouteValidationTests(unittest.TestCase):
    def test_actual_feature_is_accepted_without_features_key(self):
        points, length = validate_feature(feature())
        self.assertEqual(len(points), 2)
        self.assertEqual(length, 10)

    def test_missing_or_empty_route_rejected(self):
        for route in (None, {}, {'type': 'FeatureCollection', 'features': []}, feature([]), feature([[4, 52]])):
            with self.subTest(route=route), self.assertRaises(ValueError):
                validate_feature(route)

    def test_invalid_distance_rejected(self):
        for length in (0, -1, math.nan, math.inf, True, '10', None):
            with self.subTest(length=length), self.assertRaises(ValueError):
                validate_feature(feature(length=length))

    def test_wrong_units_rejected(self):
        with self.assertRaises(ValueError):
            validate_feature(feature(units='km'))

    def test_unwrapped_longitude_measured_without_moving_point(self):
        points, _ = validate_feature(feature([[289.8, -22.09], [300, -20]]))
        self.assertAlmostEqual(distance_nm(points[0], [-70.2, -22.09]), 0, places=8)

    def test_bad_route_latitude_rejected(self):
        with self.assertRaises(ValueError):
            validate_feature(feature([[4, 91], [5, 53]]))

    def test_input_coordinate_validation(self):
        for lon, lat in ((181, 0), (0, -91), (math.inf, 0), (True, 1)):
            with self.subTest(lon=lon, lat=lat), self.assertRaises(ValueError):
                coordinate_pair(lon, lat)


if __name__ == '__main__':
    unittest.main()
