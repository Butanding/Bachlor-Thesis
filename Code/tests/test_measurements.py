import unittest

from blume.measurements import Measurements
from blume import measurements

class BlumeGeneralFunctionTest(unittest.TestCase):
    test_data = {
        "stationId": 9999,
        "createdAt": [
            "2019-10-29T15:00:00",
            "2019-10-29T16:00:00",
            "2019-10-29T17:00:00",
            "2019-10-29T18:00:00",
            "2019-10-29T19:00:00",
            "2019-10-29T20:00:00",
            "2019-10-29T21:00:00",
            "2019-10-29T22:00:00",
            "2019-10-29T23:00:00"
                        ],
        "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
    }

    def test_init_object(self):
        test_object = Measurements(
            stationId = self.test_data["stationId"],
            createdAt = self.test_data["createdAt"],
            value = self.test_data["value"]
        )
        assert test_object is not None
        return test_object

    def test_write_to_json(self):
        test_object = self.test_init_object()
        test_object.write_measurement_to_json()

    def test_read_from_json(self):
        test_object = self.test_init_object()
        test_object.write_measurement_to_json()
        test_object.read_measurements_from_json()

    def test_create_series(self):
        test_object = self.test_init_object()
        df = test_object.dataframe
        print(df.dtypes)
        print(df.head(5))

    def test_read_by_stationId(self):
        test = measurements.read_measurements_by_station_id(10)
        with self.assertRaises(ValueError):
            measurements.read_measurements_by_station_id(0)


