from blume import client, station, measurements
from blume.station import Station
import pandas as pd
from datetime import datetime, timedelta, timezone
from python3_sensemapi.sensemapi import client

example_to_date = datetime.utcnow()
example_from_date = example_to_date - timedelta(hours=5)

bbox_berlin = [13.0883, 52.3383, 13.7612, 52.6755]
bbox_muenster = [7.558594,51.926484,7.702789,51.980228]
senseMapiresponse = client.SenseMapClient().get_boxes(
    bbox=bbox_berlin,
    phenomenon="PM10",
    from_date=example_from_date,
    to_date=example_to_date)

#print(senseMapiresponse)

all_sensor_types = dict()
pm10_sensors = dict()
pm25_sensors = dict()

for senseBoxColl in senseMapiresponse:
    for sensor in senseBoxColl.sensors:
        print(sensor)
        if(sensor.title == "PM10"):
            if sensor.type in pm10_sensors:
                pm10_sensors[sensor.type] += 1
            else:
                pm10_sensors[sensor.type] = 1
        elif(sensor.title == "PM2.5"):
            if sensor.type in pm25_sensors:
                pm25_sensors[sensor.type] += 1
            else:
                pm25_sensors[sensor.type] = 1
        else:
            if sensor.title in all_sensor_types:
                if not (sensor.type in all_sensor_types[sensor.title]):
                    all_sensor_types[sensor.title].append(sensor.type)
            else:
                all_sensor_types[sensor.title] = [sensor.type]

for senseBoxColl in senseMapiresponse:
    has_temp = False
    has_humid = False
    has_pm10 = False
    for sensor in senseBoxColl.sensors:
        if (sensor.title == "PM10"):
            has_pm10 = True

    if has_pm10:
        for sensor in senseBoxColl.sensors:
            if "PM10" or "PM2.5" not in sensor.title:
                if sensor.title in pm10_sensors:
                    pm10_sensors[sensor.title] += 1
                else:
                    pm10_sensors[sensor.title] = 1



print("Übersicht über alle Sensoren gruppiert nach Phänomen \n {}".format(
    all_sensor_types))
print("Übersicht alle PM10 Sensoren nach Häufigkeit \n {}".format(pm10_sensors))
print("Übersicht alle PM2.5 Sensoren nach Häufigkeit \n {}".format(
    pm25_sensors))
# for senseBoxSensorData in senseMapiresponse:
#     list_of_sensorIds.append(senseBoxSensorData.sensor.id)
#
# list_of_sensor_types = list()
# for sensorId in list_of_sensorIds:
#     senseMapiresponse2 = client.SenseMapClient().get_box(sensorId)
#     list_of_sensor_types.append(senseMapiresponse2.sensors.by_title)
#
# print(list_of_sensor_types)
#final_df = pd.DataFrame([], columns=["PM10"])