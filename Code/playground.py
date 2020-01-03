import json
from requests import Session, Request
from datetime import datetime, date, time, timedelta, timezone
from posixpath import join as urljoin
import pandas as pd
import io
from blume import client, station, measurements
from blume.station import Station
from sensemapi import client as sense_client

#Scrape newest/available data from the Blume-Website
df = client.get_blume_measurments()
df = client.clean_data(df)

#Create Measurements and append to local storage of data (JSON)
online_measurement = client.create_measurements(df)

#Initially load all Stations from local storage (JSON)
station.init_stations()
#Source all available Information from local storage to pandas df
station_collection = Station.station_collection

#get all available station ids and use them to get all measurements from all
# stations
station_ids = [station.id for station in station_collection]
all_station_measurements = measurements.read_measurements_by_station_id_list(
    station_ids)

#from all measurements, get pandas series and combine to global matrix
df_local = [m.dataframe for m in all_station_measurements]
df_global = pd.concat(df_local, axis=1)

#SenseMapi related
example_to_date = datetime(2019, 11, 14, 21, 00, 00, 000, tzinfo=timezone.utc)
example_from_date = example_to_date - timedelta(hours=1)
bbox_berlin = [13.0883, 52.3383, 13.7612, 52.6755]
#BLUME related
example_date = pd.Timestamp(example_to_date).tz_convert("UTC")

example_mean = df_global.loc[example_date]

senseMapiresponse = sense_client.SenseMapClient().get_measurements_by_phenomenon(
    bbox=bbox_berlin,
    phenomenon="PM10",
    from_date=example_from_date,
    to_date=example_to_date)

# Load all PM10 Values from Berlin (OSeM) into DataFrame

sensor_vals_df = [i.series for i in senseMapiresponse]
final_df = pd.concat(sensor_vals_df, axis=1)


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
print("OpenSenseMap\t= {}"
    .format(final_df.mean().mean())
)