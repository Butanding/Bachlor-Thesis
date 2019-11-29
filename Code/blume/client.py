import json
from requests import Session, Request
from datetime import datetime, date, time, timedelta
from posixpath import join as urljoin
import pandas as pd
import io
from blume import paths, station
from blume.measurements import Measurements


def get_blume_measurments(stationgroup="all",
                          period="1h",
                          end=datetime.utcnow() - timedelta(hours=2),
                          start=datetime.utcnow() - timedelta(
                              hours=2) - timedelta(days=30)):
    """
    Returns the Measurements from BLUME Website
    Args:
        stationgroup (str): the position of the station
            allowed values: "all", "background", "traffic", "suburb"
            default is "all"
        period (str): the frequency of the measurment periods
            allowed values: "1h", "24h", "1m", "1y"
        end (datetime.datetime): the end of the measurement period
        start (datetime.datetime): the beginning of the measurement period
    Returns:
        pandas.dataframe: The Measurements as Pandas-Dataframe
    """

    url_base_path = "https://luftdaten.berlin.de/core/pm10.csv?"
    url_params = {}
    url_params["stationgroup"] = stationgroup
    url_params["period"] = period

    url_params["timespan"] = "custom&" \
                             "start[Bdate]D=" + start.strftime("%d.%m.%Y") \
                             + "&start[Bhour]D=" + start.strftime("%H") + "&" \
                                                                          "end[Bdate]D=" + end.strftime(
        "%d.%m.%Y") \
                             + "&end[Bhour]D=" + end.strftime("%H")

    request = Request("get", url_base_path, params=url_params)
    prepared = request.prepare()

    # Manipulate Request because website wants unsafe characters
    prepared.url = prepared.url.replace("%26", "&")
    prepared.url = prepared.url.replace("%3D", "=")
    prepared.url = prepared.url.replace("DD", "D")
    prepared.url = prepared.url.replace("BB", "B")

    session = Session()
    response = session.send(prepared)

    # Before Returning, write Backup to CSV-File
    filename = "{}-to-{}.csv".format(start.strftime("%d.%m.%Y_%Hh"),
                                     end.strftime(
                                         "%d.%m.%Y_%Hh"))
    with open(paths.BACKUP_CSV + filename, 'wb') as f:
        f.write(response.content)

    csv_data = response.content
    df = pd.read_csv(io.StringIO(csv_data.decode('utf-8')), sep=";")


    return df

def clean_data(df):
    #Remove unnecessary Headers
    df = df.iloc[3:]

    #clean up columns and only remain station id and date
    converted = list()
    for station_title in df.columns[1:]:
        converted.append(int(station_title[:3]))
    converted.insert(0, "Date")
    df.columns = converted

    #convert date strings to proper timestamps
    cleand_dates = list()
    for date in df["Date"]:
        cleand_dates.append(
            pd.to_datetime(date, format='%d.%m.%Y %H:%M', errors='ignore').isoformat())
    df["Date"] = cleand_dates

    #convert all values to numeric
    cols = df.columns.drop('Date')
    df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')

    return df

def create_measurements(df):
    """
    Create Measurment Objects and return them as List
    :param df:
    :return: (list) of measurement Objects
    """
    cols = df.columns.drop('Date')
    test = df[cols]
    list_of_measurement_instances = list()
    for column in test:
        new_measurement = Measurements(stationId=df[column].name,
                                       createdAt=list(df.iloc[:, 0]),
                                       value=list(df[column]))
        new_measurement.write_measurement_to_json()
        list_of_measurement_instances.append(new_measurement)
    return list_of_measurement_instances
