# system modules
import collections
import inspect
import itertools
import logging

# external modules
import requests

from sensemapi import paths
from sensemapi.errors import *

# internal modules
from sensemapi.reprobject import ReprObject
from sensemapi.sensor import senseBoxSensor, senseBoxSensorCollection
from sensemapi.utils import *

logger = logging.getLogger(__name__)


class senseBox(ReprObject):
    """
    Class representation of a senseBox
    """

    def __init__(
        self,
        id=None,
        exposure=None,
        grouptag=None,
        description=None,
        name=None,
        sensors=None,
        image=None,
        current_lat=None,
        current_lon=None,
        current_height=None,
        weblink=None,
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
    def exposure(self):
        return None

    @simplesetter(exposure)
    def exposure(self, new):
        return new

    @simplegetter
    def grouptag(self):
        return None

    @simplesetter(grouptag)
    def grouptag(self, new):
        return new

    @simplegetter
    def description(self):
        return None

    @simplesetter(description)
    def description(self, new):
        return new

    @simplegetter
    def name(self):
        return None

    @simplesetter(name)
    def name(self, new):
        return new

    @property
    def sensors(self):
        try:
            self._sensors
        except AttributeError:
            self._sensors = senseBoxSensorCollection()
            self._sensors.box = self
        return self._sensors

    @sensors.setter
    def sensors(self, new):
        if hasattr(new, "sensors"):  # is already a senseBoxSensorCollection
            self._sensors = new
        else:
            self._sensors = senseBoxSensorCollection()
            self._sensors.box = self
            self._sensors.sensors = new

    @simplegetter
    def image(self):
        return None

    @simplesetter(image)
    def image(self, new):
        return new

    @simplegetter
    def weblink(self):
        return None

    @simplesetter(weblink)
    def weblink(self, new):
        return new

    @simplegetter
    def client(self):
        return None

    @simplesetter(client)
    def client(self, new):
        return new

    @simplegetter
    def current_lat(self):
        return None

    @simplesetter(current_lat)
    def current_lat(self, new):
        return new

    @simplegetter
    def current_lon(self):
        return None

    @simplesetter(current_lon)
    def current_lon(self, new):
        return new

    @simplegetter
    def current_height(self):
        return None

    @simplesetter(current_height)
    def current_height(self, new):
        return new

    @property
    def location(self):
        """
        A location object as used by the API

        :type: :any:`dict`
        """
        return location_dict(
            self.current_lat, self.current_lon, self.current_height
        )

    def new_sensor(self, *args, **kwargs):
        """
        Add a new :class:`senseBoxSensor` to this :class:`senseBox`

        Args:
            args, kwargs : arguments passed to :meth:`senseBoxSensor.__init__`

        Returns:
            senseBoxSensor : the newly created sensor
        """
        sensor = senseBoxSensor(*args, **kwargs)
        self.add_sensor(sensor)
        return sensor

    def add_sensor(self, sensor):
        """
        Add a :class:`senseBoxSensor` to this :class:`senseBox`

        Args:
            sensor (senseBoxSensor) : the sensor to add
        """
        self.sensors.append(sensor)

    def update_from_api_json(self, d):
        """
        Create a :class:`senseBox` from a :any:`dict`.

        Args:
            d (dict): the dictionary to update this :class:`senseBox` from
        """
        locfields = ["lng", "lat", "height"]
        coords = {k: None for k in locfields}
        coords.update(
            {
                k: v
                for k, v in zip(
                    locfields,
                    d.get("currentLocation", {}).get("coordinates", []),
                )
            }
            or d.get("location", {})
        )
        for sensor_json in d.get("sensors", []):
            sensor_json_copy = sensor_json.copy()
            sensor_id = sensor_json_copy.get("_id")
            own_sensor = self.sensors.by_id.get(sensor_id)
            if own_sensor:
                own_sensor.update_from_api_json(sensor_json_copy)
            else:
                sensor_json_copy.pop("_id", None)
                self.sensors.append(senseBoxSensor.from_api_json(sensor_json))
        self.id = d.get("_id")
        for arg in inspect.getfullargspec(self.__init__)[0][1:]:
            if arg in ("sensors",):
                continue
            if arg in d:
                old_val = getattr(self, arg)
                new_val = d[arg]
                if new_val != old_val:
                    logger.debug(
                        "Changing box {} from {} to {}".format(
                            arg, repr(old_val), repr(new_val)
                        )
                    )
                    setattr(self, arg, new_val)
        self.current_lat = coords.get("lat")
        self.current_lon = coords.get("lng")
        self.current_height = coords.get("height")
        self.weblink = d.get("weblink")

    @classmethod
    def from_api_json(cls, d):
        """
        Create a :class:`senseBox` from a :any:`dict`.

        Args:
            d (dict): the dictionary to create the :class:`senseBox` from

        Returns:
            senseBox : the senseBox
        """
        senseBox = cls()
        senseBox.update_from_api_json(d)
        return senseBox

    def to_api_json(self, with_id=True):
        """
        Serialize the metadata of this senseBox to a JSON dict for the API

        Args:
            with_id (bool, optional) : serialize the ids as well? Defaults to
                ``True``.

        Returns:
            dict : the JSON dict
        """
        box_json = {}
        if with_id:
            if self.id is not None:
                box_json["_id"] = self.id
        if self.name is not None:
            box_json["name"] = self.name
        if self.grouptag is not None:
            box_json["grouptag"] = self.grouptag
        box_json["location"] = {}
        if self.current_lat is not None:
            box_json["location"]["lat"] = float(self.current_lat)
        if self.current_lon is not None:
            box_json["location"]["lng"] = float(self.current_lon)
        if self.current_height is not None:
            box_json["location"]["height"] = float(self.current_height)
        if (
            "lat" not in box_json["location"]
            or "lng" not in box_json["location"]
        ):
            box_json.pop("location", None)
        if self.description is not None:
            box_json["description"] = self.description
        if self.weblink is not None:
            box_json["weblink"] = self.weblink
        if self.exposure is not None:
            box_json["exposure"] = self.exposure
        if self.sensors is not None:
            box_json["sensors"] = []
            for sensor in self.sensors:
                if sensor.id is None:
                    sensor_json = sensor.to_api_json(new=True)
                else:
                    if all(
                        [
                            v
                            for k, v in sensor.to_api_json().items()
                            if k != "_id"
                        ]
                    ):
                        sensor_json = sensor.to_api_json(edited=True)
                    else:
                        sensor_json = sensor.to_api_json(deleted=True)
                box_json["sensors"].append(sensor_json)
        return box_json

    def upload_metadata(self):
        """
        Upload the metadata of this :class:`senseBox` to the API. Tries to call
        :any:`SenseMapAccount.update_box_metadata`.

        Returns:
            True : if the updating went well

        Raises:
            NoClientError : if this senseBox does not have an associated
                :class:`senseBoxClient` in :any:`senseBox.client`
        """
        if self.client is None:
            raise NoClientError("This box does not have an associated client.")
        if not hasattr(self.client, "update_box_metadata"):
            raise NoClientError(
                "This box' client does is not able " "to update the metadata"
            )
        return self.client.update_box_metadata(self)

    def upload_as_new(self):
        """
        Upload this :class:`senseBox` as a new senseBox. Tries to call
        :any:`SenseMapAccount.new_box`.

        Returns:
            True : if the updating went well

        Raises:
            NoClientError : if this senseBox does not have an associated
                :class:`senseBoxClient` in :class:`senseBox.client`
        """
        if self.client is None:
            raise NoClientError("This box does not have an associated client.")
        if not hasattr(self.client, "new_box"):
            raise NoClientError(
                "This box' client does is not able " "to upload a new senseBox"
            )
        return self.client.new_box(self)

    def fetch_metadata(self):
        """
        Fetch the metadata

        Raises:
            NoClientError : if this senseBox does not have an associated
                :class:`senseBoxClient` in :class:`senseBox.client`
        """
        if self.client is None:
            raise NoClientError("This box does not have an associated client.")
        if not hasattr(self.client, "_get_box"):
            raise NoClientError(
                "This box' client does is not able " "to fetch boxes"
            )
        assert self.id, "this senseBox does not have an id"
        box_json = self.client._get_box(self.id)
        self.update_from_api_json(box_json)

    def delete(self, really=False):
        """
        Delete this senseBox and all of its sensors and measurements.

        Args:
            really (bool): Really delete this box? Defaults to ``False``.
        """
        if self.client is None:
            raise NoClientError("This box does not have an associated client.")
        if not hasattr(self.client, "delete_box"):
            raise NoClientError(
                "This box' client does is not able " "to delete boxes"
            )
        assert self.id, "this senseBox does not have an id"
        return self.client.delete_box(self.id, really=really)

    def __eq__(self, other):
        """
        Compare this :class:`senseBox` to another :class:`senseBox` and check
        if all metadata is equal.
        """
        for arg in inspect.getfullargspec(self.__init__)[0][1:]:
            if not getattr(self, arg) == getattr(other, arg):
                return False
        return True


class senseBoxCollection(collections.abc.MutableSequence, ReprObject):
    """
    Container for multiple :class:`senseBox` s

    Args:
        boxes (sequence, optional): the :class:`senseBox` s
    """

    def __init__(self, boxes=[]):
        self.boxes = boxes

    @property
    def boxes(self):
        """
        The underlying :class:`senseBox` es

        :type: :any:`list`
        :setter: also adds the :meth:`senseBoxCollection.client` to the
            given :class:`senseBox` s
        """
        try:
            self._boxes
        except AttributeError:
            self._boxes = []
        return self._boxes

    @boxes.setter
    def boxes(self, new_boxes):
        self._boxes = []
        for box in new_boxes:
            box.client = self.client
            self.append(box)

    @simplegetter
    def client(self):
        """
        The :class:`SenseMapClient` these :class:`senseBox` es belong to.

        :type: :class:`SenseMapClient` or :any:`None`
        """
        return None

    @simplesetter(client)
    def client(self, new):
        return new

    @property
    def by_id(self):
        """
        A :any:`dict` of these :class:`senseBox` es by their
        ids. boxes without an id get assigned to counter key
        ``new_sensor_N``.

        :type: :any:`dict`
        """
        i = itertools.count(0)
        return {
            box.id if box.id else ("new_box_{}".format(next(i))): box
            for box in self
        }

    @property
    def by_name(self):
        """
        A :any:`dict` of these :class:`senseBox` es by their names. Boxes
        without a name get assigned to counter key ``unnamed box N``.
        Duplicate names get a ``" Nr. N"`` appended.

        :type: :any:`dict`
        """
        unnamed = itertools.count(0)
        d = {}
        duplicates = collections.Counter()
        for box in self:
            if box.name:
                if box.name in d:
                    duplicates[box.name] += 1
                    d[
                        "{} Nr. {}".format(box.name, duplicates[box.name] + 1)
                    ] = box
                else:
                    d[box.name] = box
            else:
                d["Unnamed senseBox {}".format(next(unnamed))] = box
        return d

    @needs_pandas
    @property
    def series(self):
        """
        Convert the data to a :class:`pandas.Series`

        Returns:
            pandas.Series : the data as series
        """
        series = pandas.Series(
            data=self.data["value"], index=self.data["createdAt"]
        )
        if self.sensor:
            series.name = "{} ({}) [{}]".format(
                self.sensor.title, self.sensor.type, self.sensor.unit
            )
        return series

    def __getitem__(self, *args, **kwargs):
        return self.boxes.__getitem__(*args, **kwargs)

    def __setitem__(self, index, value):
        """
        Also adds the :any:`senseBoxCollection.client` to the new box
        """
        value.client = self.client
        return self.boxes.__setitem__(index, value)

    def insert(self, index, value):
        """
        Also adds the :any:`senseBoxCollection.client` to the new box
        """
        value.client = self.client
        return self.boxes.insert(index, value)

    def append(self, value):
        """
        Also adds the :any:`senseBoxCollection.client` to the new box
        """
        value.client = self.client
        return self.boxes.append(value)

    def __delitem__(self, *args, **kwargs):
        return self.boxes.__delitem__(*args, **kwargs)

    def __len__(self, *args, **kwargs):
        return self.boxes.__len__(*args, **kwargs)

    def __eq__(self, other):
        return self.boxes == other.boxes

    def __getattr__(self, attr):
        """
        Retreives a box by looking its title up in
        :any:`senseBoxCollection.by_name`.
        """
        try:
            return self.by_name[attr]
        except KeyError:
            raise AttributeError(
                "{} object does neither have an attribute '{}' "
                "nor a box with that title".format(
                    self.__class__.__name__, attr
                )
            )
