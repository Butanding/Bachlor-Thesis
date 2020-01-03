# system modules
import csv
import inspect
import io
import json
import logging

from sensemapi.errors import *
from sensemapi.reprobject import ReprObject
from sensemapi.utils import *

# external modules

logger = logging.getLogger(__name__)


class senseBoxSensorData(ReprObject):
    """
    Class holding data of a :class:`senseBoxSensor`

    Args:
        data (dict or str, optional): the data data. Either a CSV string or a
            :any:`dict` as returned by the API when downloading timeseries.
    """

    def __init__(self, data=None, sensor=None):
        frame = inspect.currentframe()
        args = inspect.getargvalues(frame)[0]
        for arg in args[1:]:
            val = locals().get(arg)
            if val is not None:
                setattr(self, arg, val)

    @simplegetter
    def data(self):
        """
        The data data

        :type: :any:`str` or :any:`dict`
        """

    @simplesetter(data)
    def data(self, new):
        return new

    @simplegetter
    def sensor(self):
        """
        The this data belongs to sensor

        :type: :any:`senseBoxSensor`
        """

    @simplesetter(sensor)
    def sensor(self, new):
        return new

    @classmethod
    def from_csv(cls, fh, **kwargs):
        """
        Create a :class:`senseBoxSensorData` object from a CSV string

        Args:
            fh (file-like object): file-like object (e.g. :class:`io.StringIO`)
            kwargs : further keyword arguments passed to
                :meth:`senseBoxSensorData.__init__`.

        Returns:
            senseBoxSensorData
        """
        data = read_csv(fh)
        if not data:
            data = {"createdAt": [], "value": []}
        assert len(data) == 2, "data does not have exactly two columns"
        for col in ("createdAt", "value"):
            assert col in data, "data does not have '{}' column".format(col)
        return cls(data=data)

    @property
    def csv(self):  # pragma: no cover
        """
        Serializes this data to CSV. **Warning**: This is **not** consistent
        with :meth:`senseBoxSensorData.from_csv`.

        Returns:
            str : the CSV data
        """
        csvfh = io.StringIO()
        write_csv(csvfh, self.data)
        return csvfh.getvalue()

    @property
    @needs_pandas
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
            series.name = '_'.join(filter(None,
                                          [self.sensor.id, self.sensor.title,
                                                 self.sensor.type, self.sensor.unit]))
        return series

    def __len__(self):
        """
        Return the number of data rows

        Raises:
            ValueError : If the lengths are strange
        """
        try:
            l1 = len(self.data["createdAt"])
            l2 = len(self.data["value"])
        except (KeyError, TypeError) as e:  # pragma: no cover
            raise ValueError("data is ill-formed: {}".format(e))
        if l1 == l2:
            return l1
        else:  # pragma: no cover
            raise ValueError(
                "'createdAt' has {} elements "
                "and 'value' has {} elements".format(l1, l2)
            )
