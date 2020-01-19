# external modules
import requests
import json
import os
import sys
import pandas as pd


def measure_response(url):
    r = requests.get(url)
    print("Measured Time in Seconds of Download: %d " % r.elapsed.total_seconds())
    print ("Estimated size: " + str(sys.getsizeof(r.json()) / 1024) + "KB")


oneday_pm10_berlin = {"title":"24h_pm10_berlin", "url":"https://api.opensensemap.org/boxes/data?bbox=13.0883%2C52.3383%2C13.7612%2C52.6755&phenomenon=PM10&from-date=2019-12-27T23%3A00%3A00.000Z&to-date=2019-12-28T23%3A00%3A00.000Z&format=json&download=false"}

measure_response(oneday_pm10_berlin["url"])
