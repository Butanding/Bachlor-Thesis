import json
from requests import Session, Request
from datetime import datetime, date, time, timedelta, timezone
from posixpath import join as urljoin
import pandas as pd
import io
from blume import client, station, measurements
from blume.station import Station
from sensemapi import client as sense_client

from blume import client, station, measurements
from blume.station import Station
import pandas as pd
from datetime import datetime, timedelta, timezone
from sensemapi import client



box_ids = list()
sensor_ids = list()

# SenseMapi related
example_to_date = datetime.utcnow() - timedelta(days=8)
example_from_date = example_to_date - timedelta(days=1)

bbox_berlin = [13.0883, 52.3383, 13.7612, 52.6755]
senseMapiresponse = client.SenseMapClient().get_boxes(
    bbox=bbox_berlin,
    phenomenon="PM10",
    from_date=example_from_date,
    to_date=example_to_date)

for senseBoxColl in senseMapiresponse:
    for sensor in senseBoxColl.sensors:
        if(sensor.title == "PM10"):
            if not senseBoxColl.id in box_ids:
                box_ids.append(senseBoxColl.id)
                sensor_ids.append(sensor.id)


measurements_data = list()
#for j in range(len(sensor_ids)):
for j in range(4):
    # SenseMapi related
    example_to_date = datetime.utcnow()
    example_from_date = example_to_date - timedelta(days=30)

    bbox_berlin = [13.0883, 52.3383, 13.7612, 52.6755]
    senseMapiresponse = client.SenseMapClient().get_measurements(
        box_id=box_ids[j],
        sensor_id=sensor_ids[j],
        from_date=example_from_date,
        to_date=example_to_date,
        format="csv")

    measurements_data.append(senseMapiresponse)


print(sensor_ids)