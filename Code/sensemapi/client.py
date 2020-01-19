# system modules
import functools
import inspect
import io
import itertools
import json
import logging
import math
import re
import time
from contextlib import contextmanager
from posixpath import join as urljoin

# external modules
import requests

# internal modules
from sensemapi import compat, paths
from sensemapi.errors import *
from sensemapi.reprobject import ReprObject
from sensemapi.senseBox import senseBox, senseBoxCollection
from sensemapi.senseBoxSensorData import senseBoxSensorData
from sensemapi.sensor import senseBoxSensor
from sensemapi.utils import *

logger = logging.getLogger(__name__)


class SenseMapClient(ReprObject):
    """
    Client to interface the `OpenSenseMap API <https://api.opensensemap.org>`_

    Args:
        api (str, optional): the api server to use. You may use
            :any:`OPENSENSEMAP_API_LIVE` (default) or
            :any:`OPENSENSEMAP_API_TEST` for testing purposes.
        connection_timeout (float, optional): default connection timeout
            for requests in seconds. Default is no timeout.
        request_cache (cachecontrol.adapter.CacheControl, optional):
            request cache
        response_timeout (float, optional): default response timeout
            for requests in seconds. Default is no timeout.
    """

    def __init__(
        self,
        api=paths.OPENSENSEMAP_API_LIVE,
        connection_timeout=None,
        response_timeout=None,
        request_cache=None,
    ):
        frame = inspect.currentframe()
        args = inspect.getargvalues(frame)[0]
        for arg in args[1:]:
            val = locals().get(arg)
            if val is not None:
                setattr(self, arg, val)

    RETRY_AFTER_HEADER_REGEX = re.compile("retry.*after$", re.IGNORECASE)
    """
    Regex used to determine the header field containing the time to wait until
    issuing the next request
    """

    def modifies_session(decorated_function):
        """
        Decorator for methods that require closing and deleting the
        :any:`SenseMapClient.session` because they modify it.
        """

        @functools.wraps(decorated_function)
        def wrapper(self, *args, **kwargs):
            if hasattr(self, "_session"):
                logger.debug(
                    "Closing and deleting existing session "
                    "because {} was called".format(decorated_function)
                )
                self._session.close()
                del self._session
            return decorated_function(self, *args, **kwargs)

        return wrapper

    @simplegetter
    def api(self):
        return None

    @api.setter
    @modifies_session
    def api(self, new):
        self._api = new

    @simplegetter
    def connection_timeout(self):
        return None

    @simplesetter(connection_timeout)
    def connection_timeout(self, new):
        return new if new is None else float(new)

    @simplegetter
    def response_timeout(self):
        return None

    @simplesetter(response_timeout)
    def response_timeout(self, new):
        return new if new is None else float(new)

    @simplegetter
    @needs_cachecontrol
    def cache_heuristic(self):
        from sensemapi.heuristic import CacheHeuristic

        return CacheHeuristic()

    @cache_heuristic.setter
    @modifies_session
    def cache_heuristic(self, new):
        self._cache_heuristic = new

    @simplegetter
    def session(self):
        session = requests.session()
        if self.request_cache:
            try:
                from cachecontrol.adapter import CacheControlAdapter

                adapter = CacheControlAdapter(
                    cache=self.application.request_cache
                    if self.application
                    else self.request_cache,
                    heuristic=self.cache_heuristic,
                    cacheable_methods=("GET",),
                )
                if self.api:
                    # we will only cache GET requests to the /boxes path
                    session.mount(urljoin(self.api, paths.BOXES), adapter)
                else:
                    logger.warning(
                        "No API is set. "
                        "Mounting cache adapter for whole http(s):// schema"
                    )
                    for schema in ("http://", "https://"):
                        session.mount(schema, adapter)
            except ImportError:
                logger.warning(
                    "CacheControl is not available. Cannot use cache."
                )
        return session

    @session.setter
    @modifies_session
    def session(self, new):
        self._session = new

    @simplegetter
    def request_cache(self):
        return None

    @request_cache.setter
    @modifies_session
    def request_cache(self, new):
        self._request_cache = new

    @property
    @contextmanager
    def no_cache(self):
        """
        Context manager to disable caching temporarily by setting the default
        'Cache-Control' header to 'no-cache'.
        """
        old_cache_control = self.session.headers.get("Cache-Control")
        logger.debug(
            "Temporarily setting default 'Cache-Control' header to 'no-cache'"
        )
        self.session.headers.update({"Cache-Control": "no-cache"})
        yield
        if old_cache_control:
            logger.debug(
                "Resetting default 'Cache-Control' header "
                "from '{}' to {}".format(
                    self.session.headers.get("Cache-Control"),
                    old_cache_control,
                )
            )
        else:
            logger.debug("Removing default 'Cache-Control' header")
        self.session.headers.pop("Cache-Control")

    def retry_after_time_if_too_many_requests(decorated_function):
        """
        Decorator to call a decorated method, catching an
        :any:`OpenSenseMapAPITooManyRequestsError`, trying to determine how
        long to wait from the error message, waiting that time and then
        retries.
        """

        @functools.wraps(decorated_function)
        def wrapper(self, *args, **kwargs):
            try:
                return decorated_function(self, *args, **kwargs)
            except OpenSenseMapAPITooManyRequestsError as e:
                logger.debug(e)
                m = re.search(
                    pattern=r"(?:(?P<seconds>\d+\.\d+)\s*s)|"
                    r"(?:(?P<milliseconds>\d+\.\d+)\s*ms)",
                    string=str(e),
                )
                try:
                    d = m.groupdict()
                    retry_after_seconds = 0
                    seconds = d.get("seconds")
                    milliseconds = d.get("milliseconds")
                    if seconds:
                        retry_after_seconds += float(seconds)
                    if milliseconds:
                        retry_after_seconds += float(milliseconds) / 1000
                except (AttributeError, ValueError, KeyError, IndexError):
                    raise OpenSenseMapAPITooManyRequestsError(
                        "Could not determine " "time to wait until next retry."
                    )
                logger.debug(
                    "Waiting {} seconds until retry...".format(
                        retry_after_seconds
                    )
                )
                time.sleep(retry_after_seconds)
            logger.debug(
                "Now trying again to call {}".format(decorated_function)
            )
            return decorated_function(self, *args, **kwargs)

        return wrapper

    @retry_after_time_if_too_many_requests
    def request(self, method, *args, **kwargs):
        """
        Wrapper around corresponding methods of :mod:`requests`, raising
        specific exceptions depending of the response.

        Args:
            method (str): the method to use. Needs to be a method of
                :any:`requests`.
            args, kwargs : arguments passed to the method

        Returns:
            requests.models.Response : the request response

        Raises:
            OpenSenseMapAPITooManyRequestsError : if the client issued too many
                requests
        """
        request_kwargs = {
            "timeout": (self.connection_timeout, self.response_timeout)
        }
        request_kwargs.update(kwargs)
        response = self.session.request(method, *args, **request_kwargs)
        logger.debug(
            "API responded [status code {}]:\n"
            "Headers:\n{}\nPayload:\n{}".format(
                response.status_code, response.headers, response.text
            )
        )
        # too many requests
        if response.status_code == 429:
            headers = response.headers.copy()
            retry_after_header = next(
                filter(self.RETRY_AFTER_HEADER_REGEX.search, headers.keys()),
                None,
            )
            retry_after = headers.get(retry_after_header)
            raise OpenSenseMapAPITooManyRequestsError(
                "retry after {}".format(retry_after) if retry_after else ""
            )
        try:
            logger.debug(
                "API responded JSON [status code {}]:\n{}".format(
                    response.status_code, response.json()
                )
            )
        except compat.JSONDecodeError:
            pass
        return response

    def _get_box(self, id, format=None):
        """
        Issue the request to retreive a single senseBox

        Args:
            id (str) : the senseBox id to retreive
            format (str, optional): one of ``"json"`` and ``"geojson"``

        Returns:
            dict : the API response
        """
        response = self.request(
            "get",
            urljoin(self.api, paths.BOXES, id),
            params={"format": format} if format else {},
        )
        response_json = response.json()
        if response.status_code == 200:
            return response_json
        else:
            message = response_json.get("message")
            raise OpenSenseMapAPIError(
                "Could not retreive with id '{}'{}".format(
                    id, ": {}".format(message) if message else ""
                )
            )

    def get_box(self, id):
        """
        Retreive one :class:`senseBox`

        Args:
            id (str) : the :class:`senseBox` id to retreive

        Returns:
            senseBox : the retreived senseBox
        """
        box = senseBox.from_api_json(self._get_box(id=id, format="json"))
        box.client = self
        return box

    def post_measurement(
        self,
        box_id,
        sensor_id,
        value,
        time=None,
        lat=None,
        lon=None,
        height=None,
    ):
        """
        Issue a request to upload a new measurement

        Args:
            box_id (str) : the senseBox id
            sensor_id (str) : the sensor's id
            value (float) : the current measurement value
            time (datetime.datetime, optional) : the time of the measurement
            lat, lon, height (float,optional) : the current position

        Returns:
            True : on success
        """
        assert box_id is not None, "box_id must  be defined"
        assert sensor_id is not None, "sensor_id must  be defined"
        d = {}
        d["value"] = float(value)
        if time:
            d["createdAt"] = date2str(time)
        try:
            d["location"] = location_dict(lat, lon, height)
        except ValueError:
            pass
        logger.debug("Sending Request with JSON:\n{}".format(pretty_json(d)))
        response = self.request(
            "post", urljoin(self.api, paths.BOXES, box_id, sensor_id), json=d
        )
        try:
            response_json = response.json()
        except compat.JSONDecodeError:  # pragma: no cover
            raise OpenSenseMapAPIError(
                "Posting measurement didn't work: {}".format(response.text)
            )
        if hasattr(response_json, "get"):  # is a dict
            message = response_json.get("message")
            raise OpenSenseMapAPIError(
                "Posting measurement didn't work{}".format(
                    ": " + message or ""
                )
            )
        else:  # no dict
            if re.search(r"measurement\s+saved\s+in\s+box", response_json):
                return True

    @classmethod
    @needs_pandas
    def dataframe_to_csv_for_upload(self, df, discard_incomplete=False):
        """
        Convert a dataframe to csv for the upload

        Args:
            df (pandas.DataFrame): a dataframe with the at least the
                columns ``sensor_id`` (string), ``value`` (float) and
                optionally ``time`` (datetime), ``lat`` (float) **and** ``lon``
                (float) and ``height`` (float).
            discard_incomplete (bool, optional): use as much data as possible.
                If ``True``, drops parts of incomplete datasets for the API to
                accept the data. If ``False`` (default), raises
                :any:`ValueError` if the dataset is incomplete.

        Returns:
            str : the csv string

        Raises
            ValueError : if ``discard_incomplete=False`` and any row is
                incomplete
        """
        data = df.copy()
        # convert time to utc
        if "time" in data:
            try:  # timezone-unaware
                data["time"] = data["time"].dt.tz_localize("UTC")
            except TypeError:  # already timezone-aware
                data["time"] = data["time"].dt.tz_convert("UTC")
        duplicated = list(
            df["sensor_id"][df["sensor_id"].duplicated(keep=False)].unique()
        )
        if duplicated:
            raise ValueError(
                "The sensor id{s1} {ids} occur{s2} more than once. "
                "Posting 'multiple' new measurements does not mean "
                "'upload of timeseries'".format(
                    s1="s" if len(duplicated) > 1 else "",
                    s2="" if len(duplicated) > 1 else "s",
                    ids=",".join(duplicated),
                )
            )
        groups = list(
            itertools.accumulate(
                (
                    ("sensor_id", "value"),
                    ("time",),
                    ("lon", "lat"),
                    ("height",),
                )
            )
        )
        csv_string = ""
        for group, smaller_group in zip(
            reversed(groups), list(reversed(groups))[1:] + [[]]
        ):
            logger.debug("current group: {}".format(group))
            logger.debug("smaller group: {}".format(smaller_group))
            try:
                part = data[list(group)]
            except KeyError as e:
                logger.debug("data is missing columns {}".format(e))
                continue
            subset = set(group) - set(smaller_group)
            part_smaller_kept = part.dropna(
                axis="index", how="all", subset=subset
            )
            part_smaller_dropped = part.drop(part_smaller_kept.index)
            if not part_smaller_dropped.empty:
                logger.debug(
                    "These {} rows are incomplete "
                    "and obviously for smaller group {}:\n{}".format(
                        len(part_smaller_dropped.index),
                        subset,
                        part_smaller_dropped,
                    )
                )
            part_kept = part_smaller_kept.dropna(axis="index", how="any")
            part_dropped = part_smaller_kept.drop(part_kept.index)
            if not part_dropped.empty:
                logger.warning(
                    "These {} rows are incomplete, "
                    "this {} data will be discarded:\n{}".format(
                        len(part_dropped.index), subset, part_dropped
                    )
                )
                if not discard_incomplete:
                    raise ValueError(
                        "In these rows, "
                        "none of columns {} must be NaN:\n{}".format(
                            smaller_group, part_dropped
                        )
                    )
            logger.debug(
                "Keeping these {} rows for group {}:\n{}".format(
                    len(part_kept.index), group, part_kept
                )
            )
            if part_kept.empty:
                continue
            csv_string += part_kept.to_csv(
                header=False,
                index=False,
                sep=",",
                date_format=OPENSENSEMAP_DATETIME_FORMAT_UTC,
            )
            data.drop(part_kept.index, inplace=True)
        if not data.empty:
            logger.warning(
                "Skipping these {} rows of data "
                "due to missing information:\n{}".format(len(data.index), data)
            )
        return csv_string

    def post_measurements(
        self, box_id, measurements, discard_incomplete=False
    ):
        """
        Post multiple measurements to sensors in a :class:`senseBox`

        Args:
            box_id (str): the senseBox id
            measurements (pandas.DataFrame): a dataframe with the at least the
                columns ``sensor_id`` (string), ``value`` (float) and
                optionally ``time`` (datetime), ``lat`` (float) **and** ``lon``
                (float) and ``height`` (float).
            discard_incomplete (bool, optional): use as much data as possible.
                If ``True``, drops parts of incomplete datasets for the API to
                accept the data. If ``False`` (default), raises
                :any:`ValueError` if the dataset is incomplete.

        Returns:
            bool : whether the upload was successful
        """
        csv_string = self.dataframe_to_csv_for_upload(
            measurements, discard_incomplete=discard_incomplete
        )
        logger.debug(
            "Attempting to upload CSV data to senseBox '{}':\n{}".format(
                box_id, csv_string
            )
        )
        response = self.request(
            "post",
            url=urljoin(self.api, paths.BOXES, box_id, "data"),
            headers={"content-type": "text/csv"},
            data=csv_string,
        )
        if response.status_code == requests.codes.CREATED:
            return True
        try:
            response_json = response.json()
        except compat.JSONDecodeError:  # pragma: no cover
            raise OpenSenseMapAPIError(
                "Posting measurement didn't work: {}".format(response.text)
            )
        message = response_json.get("message")
        raise OpenSenseMapAPIError(
            "Posting measurement didn't work{}".format(": " + message or "")
        )

    def get_measurements(
        self,
        box_id,
        sensor_id,
        from_date=None,
        to_date=None,
        format=None,
        download=None,
        outliers=None,
        outlier_window=None,
        delimiter=None,
    ):
        """
        Retrieve the 10000 latest measurements for a sensor

        Args:
            box_id (str): the senseBox id
            sensor_id (str): the sensor id
            from_date (datetime.datetime, optional): beginning date of
                measurement data (default: 48 hours ago from now)
            to_date (datetime.datetime, optional): end date of measurement data
                (default: now)
            format (str, optional): either ``"json"`` (default) or ``"csv"``
            outliers (bool, optional): add outlier marker `isOutlier` to data?
            outlier_window (int, optional):
                outlier window size (1-50, default: 15)
            delimiter (str, optional): either ``"comma"`` (default) or
                ``"semicolon"``

        Returns:
            senseBoxSensorData : the retrieved data
        """
        assert box_id is not None, "box_id must  be defined"
        assert sensor_id is not None, "sensor_id must  be defined"
        d = {}
        if from_date is not None:
            d["from-date"] = date2str(from_date)
        if to_date is not None:
            d["to-date"] = date2str(to_date)
        if format is not None:
            d["format"] = str(format)
        if outliers is not None:
            d["outliers"] = bool(outliers)
        if outlier_window is not None:
            d["outlier-window"] = int(outlier_window)
        logger.debug(
            "Sending GET request with parameters:\n{}".format(pretty_json(d))
        )
        response = self.request(
            "get",
            urljoin(self.api, paths.BOXES, box_id, "data", sensor_id),
            params=d,
        )
        try:
            response_json = response.json()
            raise NotImplementedError(
                "Parsing JSON-formatted measurements "
                "is not yet implemented. Use format='csv'"
            )
        except compat.JSONDecodeError:
            return senseBoxSensorData.from_csv(io.StringIO(response.text))

    def get_boxes(
        self,
        bbox=None,
        from_date=None,
        to_date=None,
        phenomenon=None,
        grouptag=None,
        minimal=False,
        exposure=None,
    ):
        """
                Get all senseBoxes that match certain criteria.
                Description: https://docs.opensensemap.org/#api-Boxes-getBox


                Args:
                    bbox (list): the coordinates of the area of interest in the
                        following order: longitude southwest,
                        latitude southwest, longitude northeast,
                        latitude northeast
                    from_date (datetime.datetime, optional): if to_date is
                        provided, this is the beginning date of boxes data
                        (if to_date is not provided, boxes that submitted data
                        around this time, +/- 4 hours, are returned)
                    to_date (datetime.datetime, optional): if from_date is
                        provided, this is the ending date of boxes(if from_date
                         is not provided, boxes that submitted data around
                         this time, +/- 4 hours, are returned)
                    phenomenon (str, optional): A sensor phenomenon
                        (determined by sensor name) such as temperature,
                        humidity or UV intensity. Requirement: from_date or
                        to_date must at least be provided, otherwise
                        'phenomenon' will be ignored.
                    grouptag (set, optional): only return boxes with this
                        grouptag, allows to specify multiple strings in one
                        list
                    minimal (bool, optional): if specified, only a minimal
                        set of box metadata is returned for fast response.
                        Default is ``False``
                    exposure (list, optional): Only include boxes with this
                        exposure. Allows to specify multiple strings in one
                        list. Allowed values: "indoor",
                            "outdoor", "mobile", "unknown"
                Returns:
                    senseBoxCollection : the API-Response converted to
                    SenseBox-Objects stored in a List
                """
        assert bbox, "bbox must  be defined"

        d = {"bbox": ",".join(map(str, map(float, bbox)))}

        dates = list()
        if to_date:
            dates.append(from_date)
            if from_date:
                dates.append(to_date)

        if dates:
            d["date"] = ",".join(map(date2str, dates))
        if phenomenon is not None:
            if not d.get("date"):
                raise ValueError(
                    "Missing Value to_date or from_date required for "
                    "usage of phenomenon"
                )
            d["phenomenon"] = phenomenon
        if grouptag is not None:
            d["grouptag"] = ",".join(
                map(
                    str, (grouptag,) if isinstance(grouptag, str) else grouptag
                )
            )
        d["minimal"] = json.dumps(minimal)
        if exposure is not None:
            d["exposure"] = ",".join(
                map(
                    str, (exposure,) if isinstance(exposure, str) else exposure
                )
            )

        logger.debug(
            "Sending GET request with parameters:\n{}".format(pretty_json(d))
        )

        response = self.request(
            "get", urljoin(self.api, paths.BOXES), params=d
        )

        response_json = response.json()

        if response.status_code == 200:
            return senseBoxCollection(
                map(senseBox.from_api_json, response_json)
            )
        else:
            message = response_json
            raise OpenSenseMapAPIError(
                "Could not retreive boxes{}".format(
                    ": {}".format(message) if message else ""
                )
            )

    def get_measurements_by_phenomenon(
        self,
        boxId=None,
        phenomenon=None,
        bbox=None,
        from_date=None,
        to_date=None,
        exposure=None,
    ):
        """
        Get latest measurements-values for a phenomenon in a specific area
        Description: https://docs.opensensemap.org/#api-Boxes-getBox


        Args:
            boxId (list): One or multiple BoxIDs in a List
                Requirement: Exclusivly boxId or bbox must be set
            bbox (list): the coordinates of the area of interest
                in the following order: longitude southwest, latitude
                southwest, longitude northeast, latitude northeast
                Requirement: Exclusivly boxId or bbox must be set
            phenomenon (str): the name of the single phenomenon
                you want to download the data for, such as temperature,
                humidity or UV intensity.
            from_date (datetime.datetime, optional):
                Beginning date of measurement data
                default: 2 days ago from now
            to_date (datetime.datetime, optional):
                End date of measurement data
                default: now
            exposure (list, optional): Only include boxes with this exposure.
                Allows to specify multiple strings in one list.
                Allowed values: "indoor", "outdoor", "mobile", "unknown"
        Returns:
            senseBoxCollection : the API-Response converted to
                SenseBox-Objects stored in a List
        """
        assert (boxId is not None) is not (
            bbox is not None
        ), "either boxId or bbox must be set, but not both"
        assert phenomenon, "phenomenon must be defined"
        assert isinstance(phenomenon, str), (
            "only a single phenomenon must " "be provided as string"
        )

        d = {}
        if bbox:
            d["bbox"] = ",".join(map(str, map(float, bbox)))
        if boxId:
            d["boxid"] = ",".join(
                map(str, (boxId,) if isinstance(boxId, str) else boxId)
            )
        d["phenomenon"] = phenomenon
        if from_date:
            d["from-date"] = date2str(from_date)
        if to_date:
            d["to-date"] = date2str(to_date)
        if exposure:
            d["exposure"] = ",".join(
                map(
                    str, (exposure,) if isinstance(exposure, str) else exposure
                )
            )
        # JSON is easier to convert to SenseBoxSensorData
        d["format"] = "json"
        # Disable Download-Format Header in Response
        d["download"] = json.dumps(False)

        logger.debug(
            "Sending GET request with parameters:\n{}".format(pretty_json(d))
        )


        response = self.request(
            "get", urljoin(self.api, paths.BOXES, paths.DATA), params=d,
        )
        
        response_json = response.json()
        response_json.sort(key=lambda x: x["sensorId"])
        sensor_data_collection = []

        for k, v in itertools.groupby(
            response_json, key=lambda x: x["sensorId"]
        ):
            measurement_vals = list(v)
            sensor_data_format = {
                "createdAt": [datetime.datetime.strptime(d["createdAt"],
                                                         '%Y-%m-%dT%H:%M:%S.%fZ') for d in measurement_vals],
                "value": [float(d["value"]) for d in measurement_vals],
            }

            current_sensor = senseBoxSensor(id=k, title=d["phenomenon"])
            sensor_data_collection.append(
                senseBoxSensorData(
                    data=sensor_data_format, sensor=current_sensor
                )
            )

        return sensor_data_collection

    def __del__(self):
        """
        Class destructor. Calls :meth:`requests.Session.close` on
        :any:`SenseMapClient.session`.
        """
        self.session.close()
