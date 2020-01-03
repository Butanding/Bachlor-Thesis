# system modules
import collections
import collections.abc
import datetime
import inspect
import itertools
import logging

from sensemapi.reprobject import ReprObject
from sensemapi.utils import *

# external modules


class senseBoxSensor(ReprObject):
    """
    Class representation of a senseBox sensor
    """

    def __init__(
        self,
        id=None,
        type=None,
        title=None,
        unit=None,
        icon=None,
        last_value=None,
        last_time=None,
    ):
        frame = inspect.currentframe()
        args = inspect.getargvalues(frame)[0]
        for arg in args[1:]:
            val = locals().get(arg)
            if val is not None:
                setattr(self, arg, val)

    @simplegetter
    def id(self):
        return None

    @simplesetter(id)
    def id(self, new):
        return new

    @simplegetter
    def type(self):
        return None

    @simplesetter(type)
    def type(self, new):
        return new

    @simplegetter
    def title(self):
        return None

    @simplesetter(title)
    def title(self, new):
        return new

    @simplegetter
    def unit(self):
        return None

    @simplesetter(unit)
    def unit(self, new):
        return new

    @simplegetter
    def icon(self):
        return None

    @simplesetter(icon)
    def icon(self, new):
        return new

    @simplegetter
    def last_value(self):
        return None

    @simplesetter(last_value)
    def last_value(self, new):
        return new

    @simplegetter
    def last_time(self):
        return None

    @simplesetter(last_time)
    def last_time(self, new):
        return (
            new
            if (isinstance(new, datetime.datetime) or new is None)
            else str2date(new)
        )

    @simplegetter
    def box(self):
        """
        The :class:`senseBox` this :class:`senseBoxSensor` belongs to.

        :type: :class:`senseBox`
        """
        return None

    @simplesetter(box)
    def box(self, new):
        return new

    def clear_metadata(self):
        """
        Set this sensors's metadata to :any:`None`. When uploading, this causes
        the sensor to be deleted.
        """
        for attr in (
            "title",
            "type",
            "unit",
            "icon",
            "last_time",
            "last_value",
        ):
            setattr(self, attr, None)

    def delete(self, really=False):
        """
        Delete this :class:`senseBoxSensor`.

        Args:
            really (bool, optional): Really delete this sensor?

        Returns:

        """
        assert self.id, "this sensor does not have an id"
        assert really, (
            "Refusing to delete sensor '{}' " "without really=True"
        ).format(self.id)
        assert (
            self.box
        ), "this sensor does not know what senseBox it belongs to"
        self.clear_metadata()
        return self.box.upload_metadata()

    def to_json_fallback(self, x):
        if isinstance(x, datetime.datetime):
            return date2str(x)
        return super().to_json_fallback(x)

    def update_from_api_json(self, d):
        """
        Update this :any:`senseBoxSensor` from a :any:`dict`

        Args:
            d (dict): the dictionary to update this :any:`senseBoxSensor` from
        """
        last_measurement = d.get("lastMeasurement", {}) or {}
        if "value" in last_measurement:
            last_value = last_measurement.get("value")
            self.last_value = (
                float(last_value) if last_value is not None else None
            )
        if "createdAt" in last_measurement:
            last_time = last_measurement.get("createdAt")
            self.last_time = (
                str2date(last_time) if last_time is not None else None
            )
        self.id = d.get("_id")
        self.type = d.get("sensorType")
        self.unit = d.get("unit")
        self.title = d.get("title")
        self.icon = d.get("icon")

    @classmethod
    def from_api_json(cls, d):
        """
        Create a :any:`senseBoxSensor` from a :any:`dict`.

        Args:
            d (dict): the dictionary to create the :any:`senseBoxSensor` from

        Returns:
            senseBoxSensor : the senseBox sensor
        """
        sensor = cls()
        sensor.update_from_api_json(d)
        return sensor

    def to_api_json(
        self, with_id=None, edited=False, new=False, deleted=False
    ):
        """
        Serialize the metadata of this :any:`senseBoxSensor` to a JSON dict
        for the API

        Args:
            with_id (bool, optional) : serialize the ids as well? Defaults to
                including the id if it is specified.
            edited (bool, optional): add a key to mark this sensor as edited?
            new (bool, optinal): add a key to mark this sensor as new?
            deleted (bool, optional): add a key to mark this sensor as deleted?

        Returns:
            dict : the JSON dict

        Raises:
            AssertionError : if arguments conflict or data is missing
        """
        d = {}
        if new:
            edited = True
            with_id = False
        elif edited:
            with_id = True
        if deleted:
            with_id = True
        assert not (
            deleted and edited
        ), "either 'deleted' OR 'edited'/'new' can be specified"
        if with_id is None:
            if self.id is not None:
                d["_id"] = self.id
        elif with_id:
            assert self.id is not None, "no sensor id specified"
            d["_id"] = self.id
        if edited:
            assert self.title is not None, "editing, but no sensor title given"
            assert self.type is not None, "editing, but no sensor type given"
            assert self.unit is not None, "editing, but no sensor unit given"
            assert self.icon is not None, "editing, but no sensor icon given"
            d["edited"] = True
        d["title"] = self.title
        d["sensorType"] = self.type
        d["unit"] = self.unit
        d["icon"] = self.icon
        if new:
            d["new"] = True
        if deleted:
            d["deleted"] = True
        return d

    def upload_measurement(self):
        """
        Upload the current measurement. Calls
        :any:`SenseMapClient.post_measurement`.
        """
        assert self.id, "the given sensor does not have an id"
        assert self.box, "the given sensor does not know its senseBox"
        assert self.box.id, "the given sensor's senseBox does not have an id"
        assert (
            self.last_value is not None
        ), "the given sensor does not have a last_value"
        assert (
            self.box.client
        ), "This sensor's senseBox does not have an associated client"
        post_kwargs = {}
        post_kwargs.update(
            box_id=self.box.id, sensor_id=self.id, value=float(self.last_value)
        )
        if self.box.exposure == "mobile":
            post_kwargs.update(
                lat=self.box.current_lat,
                lon=self.box.current_lon,
                height=self.box.current_height,
            )
        if self.last_time:
            post_kwargs.update(time=self.last_time)
        return self.box.client.post_measurement(**post_kwargs)

    def get_measurements(self, **kwargs):
        """
        Retrieve the 10000 latest measurements of this sensor

        Args:
            kwargs: arguments passed to :meth:`SenseMapClient.get_measurements`

        Returns:
            senseBoxSensorData : the retrieved data
        """
        assert self.id, "This sensor does not have an id"
        assert self.box, "This sensor does not know its senseBox"
        assert self.box.id, "This sensor's senseBox does not have an id"
        assert (
            self.box.client
        ), "This sensor's senseBox does not have an associated client"
        get_kwargs = kwargs.copy()
        get_kwargs.update(
            box_id=self.box.id,
            sensor_id=self.id,
            format="csv",
            delimiter="comma",
        )
        data = self.box.client.get_measurements(**get_kwargs)
        data.sensor = self
        return data

    def delete_measurements(self, **kwargs):
        """
        Delete this sensor's measurements

        Args:
            kwargs: arguments passed to
                :meth:`SenseMapAccount.delete_sensor_measurements`
        """
        assert self.id, "This sensor does not have an id"
        assert self.box, "This sensor does not know its senseBox"
        assert self.box.id, "This sensor's senseBox does not have an id"
        assert (
            self.box.client
        ), "This sensor's senseBox does not have an associated client"
        assert hasattr(
            self.box.client, "delete_sensor_measurements"
        ), "This sensor's box's client cannot delete sensor measurements"
        del_kwargs = kwargs.copy()
        del_kwargs.update({"box_id": self.box.id, "sensor_id": self.id})
        return self.box.client.delete_sensor_measurements(**del_kwargs)

    def __eq__(self, other):
        """
        Compare this :class:`senseBoxSensor` to another :class:`senseBoxsensor`
        and check if all metadata is equal.
        """
        for arg in inspect.getfullargspec(self.__init__)[0][1:]:
            if not getattr(self, arg) == getattr(other, arg):
                return False
        return True


class senseBoxSensorCollection(collections.abc.MutableSequence, ReprObject):
    """
    Container for multiple :any:`senseBoxSensor` s

    Args:
        sensors (sequence, optional): the :any:`senseBoxSensor` s
    """

    def __init__(self, sensors=[]):
        self.sensors = sensors

    @property
    def sensors(self):
        """
        The underlying :any:`senseBoxSensor` s

        :type: any:`list`
        :setter: also adds the :any:`senseBoxSensorCollection.box` to the
            given :any:`senseBoxSensor` s
        """
        try:
            self._sensors
        except AttributeError:
            self._sensors = []
        return self._sensors

    @sensors.setter
    def sensors(self, new_sensors):
        self._sensors = []
        for sensor in new_sensors:
            sensor.box = self.box
            self.append(sensor)

    @simplegetter
    def box(self):
        """
        The corresponding :class:`senseBox` these :class:`senseBoxSensor` s
        belong to.

        :type: :class:`senseBox` or :any:`None`
        """
        return None

    @simplesetter(box)
    def box(self, new):
        return new

    @property
    def by_id(self):
        """
        A :any:`dict` of these :any:`senseBoxSensor` s by their
        ids. Sensors without an id get assigned to counter key
        ``new_sensor_N``.

        :type: :any:`dict`
        """
        i = itertools.count(0)
        return {
            sensor.id
            if sensor.id
            else ("new_sensor_{}".format(next(i))): sensor
            for sensor in self
        }

    @property
    def by_title(self):
        """
        A :any:`dict` of these :any:`senseBoxSensor` s by their titles. Sensors
        without a title get assigned to counter key ``unnamed sensor N``.
        Duplicate names get a ``" Nr. N"`` appended.

        :type: :any:`dict`
        """
        unnamed = itertools.count(0)
        d = {}
        duplicates = collections.Counter()
        for sensor in self:
            if sensor.title:
                if sensor.title in d:
                    duplicates[sensor.title] += 1
                    d[
                        "{} Nr. {}".format(
                            sensor.title, duplicates[sensor.title] + 1
                        )
                    ] = sensor
                else:
                    d[sensor.title] = sensor
            else:
                d["unnamed sensor {}".format(next(unnamed))] = sensor
        return d

    # boring definitions of methods
    # I tried to use a decorator for this (https://gitlab.com/snippets/1742907)
    # but unfortunately it does not work exactly as it should
    def __getitem__(self, *args, **kwargs):
        return self.sensors.__getitem__(*args, **kwargs)

    def __setitem__(self, index, value):
        """
        Also adds the :any:`senseBoxSensorCollection.box` to the new sensor
        """
        value.box = self.box
        return self.sensors.__setitem__(index, value)

    def insert(self, index, value):
        """
        Also adds the :any:`senseBoxSensorCollection.box` to the new sensor
        """
        value.box = self.box
        return self.sensors.insert(index, value)

    def append(self, value):
        """
        Also adds the :any:`senseBoxSensorCollection.box` to the new sensor
        """
        value.box = self.box
        return self.sensors.append(value)

    def __delitem__(self, *args, **kwargs):
        return self.sensors.__delitem__(*args, **kwargs)

    def __len__(self, *args, **kwargs):
        return self.sensors.__len__(*args, **kwargs)

    def __eq__(self, other):
        return self.sensors == other.sensors

    def __getattr__(self, attr):
        """
        Retreives a box by looking its title up in
        :any:`senseBoxSensorCollection.by_title`.
        """
        try:
            return self.by_title[attr]
        except KeyError:
            raise AttributeError(
                "{} object does neither have an attribute '{}' "
                "nor a box with that title".format(
                    self.__class__.__name__, attr
                )
            )
