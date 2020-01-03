# system modules
import logging
import threading
import json
import functools
import time
import datetime
import collections
from collections import defaultdict

# internal modules

# external modules

logger = logging.getLogger(__name__)


class UploadQueue(collections.deque):
    @property
    def bundle(self):
        return getattr(self, "_bundle", False)

    @bundle.setter
    def bundle(self, val):
        self._bundle = val

    @property
    def account(self):
        return self._account

    @account.setter
    def account(self, val):
        self._account = val

    @property
    def per_sensor_upload_interval(self):
        return getattr(self, "_per_sensor_upload_interval", 0)

    @per_sensor_upload_interval.setter
    def per_sensor_upload_interval(self, val):
        self._per_sensor_upload_interval = float(val)

    @property
    def last_upload(self):
        try:
            return self._last_upload
        except AttributeError:
            self._last_upload = defaultdict(lambda: defaultdict(float))
        return self._last_upload

    @property
    def lock(self):
        try:
            return self._lock
        except AttributeError:
            self._lock = threading.Lock()
        return self._lock

    def locked(decorated_function):
        """
        Decorator for methods that should be locked with UploadQueue.lock
        """

        @functools.wraps(decorated_function)
        def wrapper(self, *args, **kwargs):
            with self.lock:
                return decorated_function(self, *args, **kwargs)

        return wrapper

    def log_queue_len(self):
        logger.debug(
            "Now {n} datasets are "
            "queued for senseBoxes {box_names}".format(
                n=len(self),
                box_names=", ".join(
                    map(
                        repr,
                        sorted(
                            set(
                                map(
                                    lambda d: self.account.boxes.by_id[
                                        next(iter(d))
                                    ].name,
                                    self,
                                )
                            )
                        ),
                    )
                ),
            )
        )

    @locked
    def dataset(self, *args, **kwargs):
        """
        Generator yielding the next queued dataset and removing it from the
        queue
        """
        while self:
            logger.debug("Retrieving a queued dataset")
            ds = self.popleft(*args, **kwargs)
            for box_id, sensor in ds.items():
                for sensor_id, data in sensor.items():
                    self.last_upload[box_id][sensor_id] = time.time()
            self.log_queue_len()
            yield ds

    @locked
    def add(self, box_id, sensor_id, measurement):
        """
        Queue another measurement. If :any:`bundle` is ``True``, first prefer
        filling the next matching incomplete queued senseBox over just
        appending.
        """
        now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
        if (
            time.time() - self.last_upload[box_id][sensor_id]
            < self.per_sensor_upload_interval
        ):
            logger.debug(
                "Not queueing measurement {measurement} for "
                "sensor {sensor_id} of box {box_id}: "
                "still within {interval:.2f} seconds interval".format(
                    measurement=measurement,
                    box_id=box_id,
                    sensor_id=sensor_id,
                    interval=self.per_sensor_upload_interval,
                )
            )
            return
        if self.bundle:
            try:
                box = self.account.boxes.by_id[box_id]
            except KeyError:
                logger.error("No such senseBox {}".format(repr(box_id)))
                return
            incomplete_queued_box = filter(
                lambda sensor_measurements: (
                    set(sensor_measurements) < set(box.sensors.by_id)
                    and sensor_id in box.sensors.by_id
                    and sensor_id not in sensor_measurements
                ),
                map(lambda d: d[next(iter(d.keys()))], self),
            )
            incomplete_box = next(incomplete_queued_box, None)
            if incomplete_box:
                logger.debug(
                    "Queued data for senseBox '{box.name}' is "
                    "lacking a '{sensor.title}' measurement. "
                    "Filling it with {meas} "
                    "instead of queueing it at the end".format(
                        box=box,
                        sensor=box.sensors.by_id[sensor_id],
                        meas=measurement,
                    )
                )
                incomplete_box[sensor_id] = (now, measurement)
                return
        logger.debug(
            "Queueing {measurement} for upload "
            "to sensor '{sensor.title}' of senseBox '{box.name}'".format(
                measurement=measurement,
                sensor=self.account.boxes.by_id[box_id].sensors.by_id[
                    sensor_id
                ],
                box=self.account.boxes.by_id[box_id],
            )
        )
        if len(self) >= self.maxlen:
            logger.warning(
                "Queue is full. "
                "Oldest dataset {} will be dropped.".format(self[0])
            )
        self.append({box_id: {sensor_id: (now, measurement)}})
        self.log_queue_len()
