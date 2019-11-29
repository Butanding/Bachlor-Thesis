from blume import client, station, measurements
from blume.station import Station
import pandas as pd
from datetime import datetime, timedelta, timezone
from python3_sensemapi.sensemapi import client

# Initially load all Stations from local storage (JSON)
station.init_stations()
# Source all available Information from local storage to pandas df
station_collection = Station.station_collection

# read measurement of a specific station
station_ids = [station.id for station in station_collection]
all_station_measurements = measurements.read_measurements_by_station_id_list(
    station_ids)

# from all measurements, get pandas series and combine to global matrix
df_local = [m.dataframe for m in all_station_measurements]
df_global = pd.concat(df_local, axis=1)

example_date = pd.Timestamp(2019, 10, 30, 12)
example_mean = df_global.loc[example_date]

print("Gesamt Berliner Feinstaubmittelwert am {} von {} bis {} Uhr"
    .format(
    example_date.strftime('%d.%m.%Y'),
    (example_date - timedelta(hours=1)).strftime('%H'),
    example_date.strftime('%H')
    )
)

print("Umweltbundesamt\t= {}"
    .format(example_mean.mean())
)

example_to_date = datetime(
    2019, 10, 30, 12, 00, 00, 000, tzinfo=timezone.utc
)
example_from_date = example_to_date - timedelta(hours=1)

bbox_berlin = [13.0883, 52.3383, 13.7612, 52.6755]
senseMapiresponse = client.SenseMapClient().get_measurements_by_phenomenon(
    bbox=bbox_berlin,
    phenomenon="PM10",
    from_date=example_from_date,
    to_date=example_to_date)
sensor_vals_df = [pd.to_numeric(i.series) for i in senseMapiresponse]
final_df = pd.DataFrame([], columns=["PM10"])

temp = list()
for sensor in sensor_vals_df:
    temp.append(pd.DataFrame({"PM10": sensor.values}))

final_df = pd.concat(temp, ignore_index=True)

print("OpenSenseMap\t= {}"
    .format(final_df.mean().values[0])
)
