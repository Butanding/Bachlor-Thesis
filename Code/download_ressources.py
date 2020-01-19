import json
import sys, os
import glob
import logging
logging.getLogger().setLevel(logging.CRITICAL)

from requests import Session, Request
from datetime import datetime, date, time, timedelta, timezone
from posixpath import join as urljoin
import pandas as pd
import io
from blume import client, station, measurements
from blume.station import Station
from sensemapi import client as sense_client
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt

from sklearn import preprocessing, svm
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

import pytz
cet = pytz.timezone('CET')



def load_csv_by_date(phenomenon, month, year, compr=None):
    try:
        filename_month = "ressources/{}_Measurments_Berlin_Seconds_gzip_{}-{}.csv".format(phenomenon, month, year)
        curr_month_df = pd.read_csv(filename_month, index_col=0, parse_dates=True, compression=compr)
        logging.info("New Monthfile loaded = {}".format(filename_month))
        curr_month_df.sort_index(inplace=True)
    except FileNotFoundError:
        logging.warning("Could not find File {}, Returning Empty Dataframe instead".format(filename_month))
        curr_month_df = pd.DataFrame()
    return curr_month_df


def download_data(phenomenon, days_scope, to_date_req, stepsize, bbox,
                  verbose=logging.CRITICAL):
    # Configure Logging, print initial Info and initialize Variables
    logging.getLogger().setLevel(verbose)
    days_start = to_date_req - timedelta(days=days_scope)
    logging.info("Entering Download for Date-Range: {}-{}".format(days_start,
                                                                  to_date_req))
    complete_response = list()
    from_date_req = (to_date_req - timedelta(days=stepsize))

    # Load first Dataset-Month from Disk
    curr_month, curr_year = from_date_req.month, from_date_req.year
    curr_month_df = load_csv_by_date(phenomenon, curr_month, curr_year,
                                     compr="gzip")

    # Iterate over whole Date-Range
    for i in range(days_scope):
        logging.info(
            "Currently investigating Date: {} --> {}".format(from_date_req,
                                                             to_date_req))

        # If entering a new month, load the corresponding dataframe
        if (from_date_req.month != curr_month):
            curr_month, curr_year = from_date_req.month, from_date_req.year
            curr_month_df = load_csv_by_date(phenomenon, curr_month, curr_year,
                                             compr="gzip")

        # If that Day is already downloaded, skip it
        # > 5 Means, that sometimes there are some Measurements that Lap Over into the Next day to ignore them
        if not (len(curr_month_df.loc[
                    from_date_req.isoformat():to_date_req.isoformat()]) > 5):
            senseMapiresponse = sense_client.SenseMapClient().get_measurements_by_phenomenon(
                bbox=bbox,
                phenomenon=phenomenon,
                from_date=from_date_req,
                to_date=to_date_req)
            logging.info("Downloaded Data for the whole day of {}".format(
                from_date_req))
            complete_response.append(senseMapiresponse)

        # Increase Download-Variables to next-day
        from_date_req = (from_date_req - timedelta(days=stepsize))
        to_date_req = (to_date_req - timedelta(days=stepsize))

    days_downloaded = len(complete_response)
    days_skipped = days_scope - days_downloaded
    logging.info(
        "Downloaded Data for %d days and skipped Download for %d days" % (
        days_downloaded, days_skipped))

    # Disable Logging
    logging.getLogger().setLevel(logging.CRITICAL)

    return complete_response


def convert_day_list_to_df(day_response_list):
    # Load all PM10 Values from Berlin (OSeM) into DataFrame
    sensor_vals_df = [i.series for i in day_response_list]

    # Round up all Measurements to Seconds (= Remove Miliseconds)
    for sensor_val in sensor_vals_df:
        sensor_val.index = sensor_val.index.round('1s')

    # Remove Duplicates from each Sensor (In the rare Case of Multiple Measurements per Second)
    sensor_vals_df_nodups = list()
    for sensor_val in sensor_vals_df:
        sensor_vals_df_nodups.append(
            sensor_val[~sensor_val.index.duplicated(keep='last')])

    # Combine all Sensors to Global Matrix Grouped by Timestamp
    final_df = pd.concat(sensor_vals_df_nodups, axis=1)

    # Make Aware of Timezone and Convert to CET
    final_df = final_df.tz_localize('UTC')
    final_df = final_df.tz_convert('CET')

    # Return DataFrame
    return final_df

def log_matrix_info(dataframe, verbose):
    logging.getLogger().setLevel(logging.INFO)
    logging.info("First Time-Stamp Entry = {}".format(dataframe.index.min()))
    logging.info("Last Time-Stamp Entry = {}".format(dataframe.index.max()))
    logging.info("Shape of Global Matrix (Measurements, unique Sensors) = {}".format(dataframe.shape))
    logging.getLogger().setLevel(verbose)

def write_csv_by_month(phenomenon, data, verbose=logging.CRITICAL):

    # Configure Logging, print initial Info and initialize Variables
    logging.getLogger().setLevel(verbose)

    # Load all PM10 Values from Berlin (OSeM) into DataFrame
    sensor_vals_day = list()
    sensor_vals_df = list()

    # Convert every Sensor from every Day into a Series of Time-Value Pairs
    for day in data[:]:
        sensor_vals_day.append(convert_day_list_to_df(day))

    # Now Concatenate every Day to a global Matrix and Sort by Time
    sensor_vals_df = pd.concat(sensor_vals_day, sort=True)

    # If there is more than one month of data, split the data into monthly array
    months = [g for n, g in sensor_vals_df.groupby(pd.Grouper(freq='M'))]
    logging.info("------ Matrix Info of New Data ------")
    log_matrix_info(sensor_vals_df, verbose)
    logging.info("Amount of unique Months beeing processed = {}".format(
        len(months)))

    for df_month in months:
        # Get the Month and year of the first date in the Dataframe and load CSV for it
        curr_month, curr_year = df_month.iloc[:1, 1].index.month[0], \
                                df_month.iloc[:1, 1].index.year[0]
        logging.info(
            "Month beeing processed = {}-{}".format(curr_month, curr_year))
        current_month_df = load_csv_by_date(phenomenon, curr_month,
                                            curr_year, compr="gzip")

        # Now Concatenate existing Days to newly Downloaded Days and Sort by Time
        if len(current_month_df) > 0:
            logging.info("Concatenating New and Old data....")
            final_df = pd.concat([current_month_df, df_month], sort=True)
        else:
            final_df = sensor_vals_df

        # Check if there are some duplicates and remove them before writing to disk
        final_df = final_df.loc[~final_df.index.duplicated(keep="first")]

        # Print Some Info what just happened
        logging.info(
            "------ Matrix Info of New and Old Data for {}-{} ------".format(
                curr_month, curr_year))
        log_matrix_info(final_df, verbose)

        # Write Data to CSV
        filename = "ressources/{}_Measurments_Berlin_Seconds_gzip_{}-{}.csv".format(
            phenomenon, curr_month, curr_year)
        final_df.to_csv(filename, compression='gzip')

        # Disable Logging
        logging.getLogger().setLevel(logging.CRITICAL)

    # %reset_selective -f final_df


def convert_seconds_to_minutes(phenomenon, verbose=logging.CRITICAL):
    # Configure Logging, print initial Info and initialize Variables
    logging.getLogger().setLevel(verbose)
    hourly_df = pd.DataFrame()
    minute_df = pd.DataFrame()

    months_files = glob.glob(
        "ressources/{}_Measurments_Berlin_Seconds_gzip_*.csv".format(
            phenomenon))

    for month in months_files:
        curr_month_df = pd.read_csv(month, index_col=0, parse_dates=True,
                                    compression="gzip")

        # Check if there are some duplicates and remove them before writing to disk
        curr_month_df = curr_month_df.loc[
            ~curr_month_df.index.duplicated(keep="first")]

        logging.info("New Monthfile loaded = {}".format(month))
        logging.info("Resampling down to Minutes and Hours...")
        current_hourly_df = curr_month_df.resample('60T', label="right").mean()
        current_mins_df = curr_month_df.resample('1T').mean()

        logging.info("Concatenating new and old Data...")
        hourly_df = pd.concat([hourly_df, current_hourly_df], sort=True)
        minute_df = pd.concat([minute_df, current_mins_df], sort=True)

    logging.info("------ NEW HOURLY DF INFO -------")
    log_matrix_info(hourly_df, verbose)
    logging.info("------ NEW MINUTE DF INFO -------")
    log_matrix_info(minute_df, verbose)

    return hourly_df, minute_df


def write_to_csv(phenomenon, interval, data):
    data.to_csv(
        "ressources/{}_Measurments_Berlin_{}.cvs".format(phenomenon, interval))


def start_by_phenomenon(phenomenon):
    days_scope = 59
    stepsize = 1
    #Careful: The To-Date is always the end and useally will be ignored
    example_to_date = datetime.utcnow().replace(tzinfo=cet).date()
    bbox_berlin = [13.0883, 52.3383, 13.7612, 52.6755]

    #Download Data
    try:
        downloaded_data = download_data(phenomenon, days_scope, example_to_date, stepsize, bbox_berlin, verbose=logging.INFO)
    except json.decoder.JSONDecodeError:
        start_by_phenomenon(phenomenon)

    #Write Data to CSV by Month by Iterating Batches
    batch_size = 10
    for i in range(0, len(downloaded_data), batch_size):
        write_csv_by_month(phenomenon, downloaded_data[i:i+batch_size], verbose=logging.INFO)

    df_hours, df_minutes = convert_seconds_to_minutes(phenomenon, logging.INFO)
    write_to_csv(phenomenon, "Hours", df_hours)
    write_to_csv(phenomenon, "Minutes", df_minutes)

start_by_phenomenon("PM10")
start_by_phenomenon("Temperatur")
start_by_phenomenon("rel. Luftfeuchte")
