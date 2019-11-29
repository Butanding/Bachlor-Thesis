from blume import paths
import json


def init_stations():
    """
    Reads all Stations from Disk, converts to Station Objects and
    :return: (list(dict)) All Stations
    """
    with open(paths.STATIONS_DB, "r") as json_file:
        data = json.load(json_file)

    for station_item in data:
        temp = Station(
            id=station_item["id"],
            name=station_item["name"],
            exposure=station_item["exposure"],
            lat=station_item["lat"],
            lon=station_item["lon"]
        )

class Station(object):
    """
    Class representation of a station
    """
    station_collection = list()

    def __init__(
            self,
            id=None,
            name=None,
            exposure=None,
            lat=None,
            lon=None,
    ):
        self.id = id
        self.name = name
        self.exposure = exposure
        self.lat = lat
        self.lon = lon
        Station.station_collection.append(self)
