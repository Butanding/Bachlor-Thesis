import os

import pandas
import pandas as pd

from blume import paths
from datetime import datetime
import json


class Measurements(object):
    """
    Class representation of list of measurements
    """

    def __init__(
            self,
            stationId=None,
            createdAt=None,
            value=None
    ):
        self.stationId = stationId
        self.createdAt = createdAt
        self.value = value

    def dict_from_class(cls):
        return dict(
            (key, value)
            for (key, value) in cls.__dict__.items()
        )

    @classmethod
    def from_json(cls, data):
        return cls(**data)

    def read_measurements_from_json(self):
        filename = paths.STATIONS_DATA + str(self.stationId)
        with open(filename, "r") as infile:
            json_data = json.load(infile)
        return Measurements.from_json(json_data)

    def write_measurement_to_json(self):
        filename = paths.STATIONS_DATA + str(self.stationId)
        ##File exists
        if os.path.isfile(filename):
            measurements = self.read_measurements_from_json()
            for i in range(len(self.createdAt)):
                #Check if timestamp already present
                if not (self.createdAt[i] in measurements.createdAt):
                    measurements.createdAt.append(self.createdAt[i])
                    measurements.value.append(self.value[i])
            with open(filename, "w+") as outfile:
                json.dump(measurements.dict_from_class(), outfile, indent=4)
        ##File does not exist yet
        else:
            with open(filename, "w+") as outfile:
                json.dump(self.dict_from_class(), outfile, indent=4)

    @property
    def dataframe(self):
        """
        Convert the data to a :class:`pandas.Series`

        Returns:
            pandas.Series : the data as series
            "2019-10-29T15:00:00",
        """
        converted_date = pd.to_datetime(self.createdAt,
                                        format='%Y-%m-%dT%H:%M:%S',
                                        errors='ignore')
        series = pandas.Series(
            data=self.value, index=converted_date
        )
        return pd.DataFrame({self.stationId: series})



def read_measurements_by_station_id_list(stationIds):
    all_stations_measurements = list()
    for stationId in stationIds:
        filename = paths.STATIONS_DATA + str(stationId)
        if os.path.isfile(filename):
            with open(filename, "r") as infile:
                json_data = json.load(infile)
            all_stations_measurements.append(Measurements.from_json(json_data))
        else:
            raise ValueError("Station ID {} is not available".format(stationId))
    write_statistics(len(all_stations_measurements[0].value))
    return all_stations_measurements

def write_statistics(current_measurements_count):
    """
    Writes out some statistics to a file in ressources
    Mainly, how many measurements from all Sensors there are
    :param current_measurements_count:
    :return:
    """
    with open(paths.STATISTICS_DATA, "r") as json_file:
        data = json.load(json_file)
    now = datetime.utcnow().isoformat()
    data['measurement_per_station'].append([now, current_measurements_count])
    with open(paths.STATISTICS_DATA, "w+") as outfile:
        json.dump(data, outfile, indent=4)
