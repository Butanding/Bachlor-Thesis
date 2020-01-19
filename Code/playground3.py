import json
import sys
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


# set seaborn style to white
sns.set_style("white")


#current_df = pd.read_csv("ressources/PM10_Measurments_Berlin.cvs", index_col=0, parse_dates=True)
current_df = pd.DataFrame()
current_df.head(10)


days_scope = 1
stepsize = 1
example_to_date = datetime(2019, 12, 30).replace(tzinfo=cet)
example_from_date = example_to_date - timedelta(days=days_scope)
bbox_berlin = [13.0883, 52.3383, 13.7612, 52.6755]
complete_response = list()

# SenseMapi related
to_date_req = example_to_date
for i in range(days_scope):
    to_date_req = (to_date_req - timedelta(days=stepsize))
    from_date_req = (to_date_req - timedelta(days=stepsize))

    # If that Day is already downloaded, skip it
    senseMapiresponse = sense_client.SenseMapClient().get_measurements_by_phenomenon(
        bbox=bbox_berlin,
        phenomenon="PM10",
        from_date=from_date_req,
        to_date=to_date_req)
    print(senseMapiresponse)
    print("Downloaded Data for day {}".format(to_date_req))
    complete_response.append(senseMapiresponse)

days_downloaded = len(complete_response)
days_skipped = days_scope - days_downloaded
print("Downloaded Data for %d days and skipped Download for %d days" % (
days_downloaded, days_skipped))