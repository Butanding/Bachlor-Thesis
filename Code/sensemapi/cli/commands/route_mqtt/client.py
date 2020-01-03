# system modules
import logging
from functools import reduce, partial
import datetime
import collections
import itertools
import operator
import re

# internal modules
import sensemapi

# external modules
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class SelectiveMQTTClient(mqtt.Client):
    @property
    def opensensemap_account(self):
        return getattr(
            self, "_opensensemap_account", sensemapi.account.SenseMapAccount
        )

    @opensensemap_account.setter
    def opensensemap_account(self, val):
        self._opensensemap_account = val

    @property
    def subscribed_topics_when_connected(self):
        return getattr(self, "_subscribed_topics_when_connected", ("#",))

    @subscribed_topics_when_connected.setter
    def subscribed_topics_when_connected(self, topics):
        self._subscribed_topics_when_connected = topics

    @property
    def parse_topic_regexes(self):
        return getattr(self, "_parse_topic_regexes", (re.compile(r"^.*$"),))

    @parse_topic_regexes.setter
    def parse_topic_regexes(self, value):
        self._parse_topic_regexes = value

    @property
    def parse_message_regexes(self):
        return getattr(self, "_parse_message_regexes", (re.compile(r"^.*$"),))

    @parse_message_regexes.setter
    def parse_message_regexes(self, value):
        self._parse_message_regexes = value

    @property
    def sensebox_match(self):
        return getattr(
            self,
            "_sensebox_match",
            (r"{box}", r"{sensebox}", "{sensebox_id}", "{sensebox_name}"),
        )

    @sensebox_match.setter
    def sensebox_match(self, value):
        self._sensebox_match = value

    @property
    def sensor_match(self):
        return getattr(
            self,
            "_sensor_match",
            (r"{sensor}", "{sensor_id}", "{sensor_name}"),
        )

    @sensor_match.setter
    def sensor_match(self, value):
        self._sensor_match = value

    @property
    def measurement_pattern(self):
        return getattr(
            self,
            "_measurement_pattern",
            ("{value}", "{measurement}", "{data}"),
        )

    @measurement_pattern.setter
    def measurement_pattern(self, value):
        self._measurement_pattern = value

    @property
    def minimum_match(self):
        return getattr(self, "_minimum_match", tuple())

    @minimum_match.setter
    def minimum_match(self, value):
        self._minimum_match = value

    @property
    def replacements(self):
        return getattr(self, "_replacements", tuple())

    @replacements.setter
    def replacements(self, value):
        self._replacements = value

    @property
    def opensensemap_upload_queue(self):
        try:
            return self._opensensemap_upload_queue
        except AttributeError:
            self._opensensemap_upload_queue = collections.deque()
        return self._opensensemap_upload_queue

    @opensensemap_upload_queue.setter
    def opensensemap_upload_queue(self, value):
        self._opensensemap_upload_queue = value

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(
                "Client {client._client_id} now connected to "
                "{client._host}:{client._port}".format(client=self)
            )
            logger.info(
                "Subscribing client {client._client_id} on "
                "{client._host}:{client._port} to topics "
                "{topics}".format(
                    client=self,
                    topics=", ".join(
                        map(repr, self.subscribed_topics_when_connected)
                    ),
                )
            )
            self.subscribe(
                list(
                    map(
                        lambda x: (x, 0), self.subscribed_topics_when_connected
                    )
                )
            )
        else:
            logger.error(
                "Client {client._client_id} couldn't connect to "
                "{client._host}:{client._port}: result code {rc}".format(
                    rc=rc, client=self
                )
            )

    def on_disconnect(self, client, userdata, flags):
        logger.info(
            "Client {client._client_id} now disconnected from "
            "{client._host}:{client._port}".format(client=self)
        )

    def on_subscribe(self, client, obj, mid, granted_qos):
        logger.info(
            "Client {client._client_id} on "
            "{client._host}:{client._port} now subscribed "
            "to topics {topics} ".format(
                client=self,
                topics=", ".join(
                    map(repr, self.subscribed_topics_when_connected)
                ),
            )
        )

    @staticmethod
    def fmtfill(s, **info):
        """
        Fill a :any:`str.format` expression and if a key was not given, return
        ``None``
        """
        try:
            return s.format(**info)
        except KeyError as e:
            logger.debug(
                "Skipping pattern {} "
                "due to missing parse information {} in {}".format(
                    repr(s), repr(next(iter(e.args), "???")), info
                )
            )
            return None

    @classmethod
    def fmt2regex(cls, s, **info):
        """
        format a given string with :any:`fmtfill` and turn it into a regular
        expression and return ``None`` if anything didn't work.
        """
        pattern = cls.fmtfill(s, **{k: re.escape(v) for k, v in info.items()})
        if not pattern:
            return None
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            logger.warning(
                "Formatting pattern {raw} "
                " with parsed information {parsed} yields an invalid "
                " regular expression {pat}: {error}".format(
                    raw=s, parsed=info, error=e, pat=repr(pattern)
                )
            )
            return None
        return regex

    @staticmethod
    def to_float(s):
        """
        Converts a given argument to :any:`float` and if it didn't work,
        returns ``None``
        """
        try:
            return float(s)
        except BaseException:
            return None

    @staticmethod
    def sensor_matches(
        sensor,
        sensebox_match_regexes=tuple(),
        sensor_match_regexes=tuple(),
        regex_matches={
            k: any
            for k in (
                "name",
                "description",
                "grouptag",
                "title",
                "type",
                "unit",
            )
        },
    ):
        """
        Determine if a :any:`senseBoxSensor` matches

        Args:
            sensor (sensemapi.sensor.senseBoxSensor): the sensor to check
            sensebox_match_regexes, sensor_match_regexes (
                sequence of re.compile): regexes for senseBox and the sensor
                metadata to match
            regex_match (dict of callable): Mapping of attribute names to
                callables like :any:`any` or :any:`all` indicating how many
                regexes should match. The default maps all attributes
                (``name``,``description``,``grouptag``,``title``, ``type`` and
                ``unit``)  to :any:`any` which means that for each attribute
                at least one regex has to match.
        """
        return all(  # all conditions must be fulfilled
            map(  # yields whether enough regexes matched for this attribute
                lambda afor: afor[1](
                    map(  # matches regexes against the value of the attribute
                        operator.methodcaller(
                            "search",
                            getattr(afor[2], afor[0])
                            if getattr(afor[2], afor[0])
                            else "",
                        ),
                        afor[3],  # gets the regexes for this attribute
                    )
                ),
                map(  # yields (attr, fun, sensor_or_box, regexes)
                    lambda af: af
                    + next(  # returns (sensor_or_box, regexes)
                        filter(
                            bool,
                            map(
                                lambda xr: xr
                                if hasattr(xr[0], af[0])
                                else None,
                                zip(
                                    (sensor, sensor.box),
                                    (
                                        sensor_match_regexes,
                                        sensebox_match_regexes,
                                    ),
                                ),
                            ),
                        )
                    ),
                    regex_matches.items(),  # yields (attr, fun) pairs
                ),
            )
        )

    def find_matching_sensor(self, **info):
        """
        Given parsed info determine a matching sensor

        Args:
            **info: information to fill the pattern formats with
        """
        sensebox_match_regexes = tuple(
            filter(
                bool,
                (map(partial(self.fmt2regex, **info), self.sensebox_match)),
            )
        )

        logger.debug(
            "Regular expressions to find a matching senseBox: {}".format(
                ", ".join(
                    map(
                        repr,
                        map(
                            operator.attrgetter("pattern"),
                            sensebox_match_regexes,
                        ),
                    )
                )
            )
        )

        sensor_match_regexes = tuple(
            filter(
                bool, (map(partial(self.fmt2regex, **info), self.sensor_match))
            )
        )

        logger.debug(
            "Regular expressions to find a matching sensor: {}".format(
                ", ".join(
                    map(
                        repr,
                        map(
                            operator.attrgetter("pattern"),
                            sensor_match_regexes,
                        ),
                    )
                )
            )
        )

        attributes = (
            "title",
            "name",
            "type",
            "unit",
            "grouptag",
            "description",
        )
        multi_matches = {}
        for combination in filter(
            lambda comb: all(
                set(m).issubset(set(comb)) for m in self.minimum_match
            ),
            itertools.chain.from_iterable(
                tuple(
                    itertools.combinations(attributes, n)
                    for n in range(1, len(attributes) + 1)
                )[::-1]
            ),
        ):
            regex_matches = {a: any for a in combination}
            matching_sensors = tuple(
                filter(
                    partial(
                        self.sensor_matches,
                        sensor_match_regexes=sensor_match_regexes,
                        sensebox_match_regexes=sensebox_match_regexes,
                        regex_matches=regex_matches,
                    ),
                    itertools.chain.from_iterable(
                        map(
                            operator.attrgetter("sensors"),
                            self.opensensemap_account.boxes,
                        )
                    ),
                )
            )
            if not matching_sensors:
                continue
            elif len(matching_sensors) == 1:
                sensor = next(iter(matching_sensors))
                logger.debug(
                    "Found a matching sensor '{sensor.title}' ({sensor.type}) "
                    " [{sensor.unit}] of senseBox '{sensor.box.name}' "
                    "fulfilling condition to match {conditions} with "
                    "sensor matching patterns {sensor_patterns} and "
                    "senseBox matching patterns {box_patterns}".format(
                        sensor=sensor,
                        conditions=" and ".join(
                            (
                                "{a} with {f} regexes".format(
                                    f=f.__name__, a=repr(a)
                                )
                                for a, f in regex_matches.items()
                            )
                        ),
                        sensor_patterns=", ".join(
                            map(
                                repr,
                                map(
                                    operator.attrgetter("pattern"),
                                    sensor_match_regexes,
                                ),
                            )
                        ),
                        box_patterns=", ".join(
                            map(
                                repr,
                                map(
                                    operator.attrgetter("pattern"),
                                    sensebox_match_regexes,
                                ),
                            )
                        ),
                    )
                )
                return sensor
            else:
                multi_matches[combination] = matching_sensors

        logger.warning(
            "Couldn't find any exclusively matching sensor with "
            "sensor matching patterns {sensor_patterns} and "
            "senseBox matching patterns {box_patterns}: {explanation}".format(
                sensor_patterns=", ".join(
                    map(
                        repr,
                        map(
                            operator.attrgetter("pattern"),
                            sensor_match_regexes,
                        ),
                    )
                ),
                box_patterns=", ".join(
                    map(
                        repr,
                        map(
                            operator.attrgetter("pattern"),
                            sensebox_match_regexes,
                        ),
                    )
                ),
                explanation=(
                    "too many matches:\n"
                    + (
                        "\n".join(
                            "- Matching {comb}:\n{sensors}".format(
                                comb=" and ".join(map(repr, c)),
                                sensors="\n".join(
                                    map(
                                        lambda x: "  - in senseBox "
                                        "'{s.box.name}': "
                                        "{s.title} "
                                        "({s.type}) "
                                        "[{s.unit}]".format(s=x),
                                        s,
                                    )
                                ),
                            )
                            for c, s in multi_matches.items()
                        )
                    )
                )
                if multi_matches
                else "no matching sensors found",
            )
        )

    def on_message(self, client, obj, msg):
        logger.debug(
            "Client {client._client_id} on "
            "{client._host}:{client._port} recieved message in topic "
            "{msg.topic}: {msg.payload}".format(client=self, msg=msg)
        )
        if not self.opensensemap_account.token:
            logger.warning(
                "OpenSenseMap account is not logged in yet. "
                "Cannot search senseBoxes for matches. "
                "Dropping message '{msg.topic}' {msg.payload}".format(msg=msg)
            )
            return
        topic, message = msg.topic, msg.payload.decode(errors="ignore")
        parsedict = reduce(  # merge all named captured groups
            lambda x, y: {**x, **y},
            map(  # drop unmatched groups
                lambda d: dict(filter(lambda i: i[1] is not None, d.items())),
                map(  # extract the named captured groups
                    operator.methodcaller("groupdict"),
                    filter(  # only consider successful matches
                        bool,
                        map(  # do the match
                            lambda sr: sr[1].search(sr[0]),
                            # iterate over both message and topic parsing
                            # regexes. With the topic being parsed last, groups
                            # matched there will override same-name groups
                            # matched in the message
                            itertools.chain(
                                itertools.zip_longest(
                                    tuple(),
                                    self.parse_message_regexes,
                                    fillvalue=message,
                                ),
                                itertools.zip_longest(
                                    tuple(),
                                    self.parse_topic_regexes,
                                    fillvalue=topic,
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            {},  # return an empty dict when there are no matches
        )
        logger.debug(
            "information parsed from topic "
            "{topic} and message {message}: {parsed}".format(
                topic=repr(topic), message=repr(message), parsed=parsedict
            )
        )

        parsedict_escaped = {k: re.escape(v) for k, v in parsedict.items()}
        for repl_dict in self.replacements:
            match_template, replace_template = (
                repl_dict["pattern"],
                repl_dict["replacement"],
            )
            try:
                match_pattern = match_template.format(**parsedict_escaped)
                replace_pattern = replace_template.format(**parsedict_escaped)
            except KeyError as e:
                logger.debug(
                    "Skipping replacement/match template {template}"
                    " due to missing key {key}".format(
                        template=repr(match_template), key=next(iter(e.args))
                    )
                )
                continue
            except BaseException as e:
                logger.error(
                    "Could not format replacement/match pattern {pattern}: "
                    "{etype}: {error}".format(
                        pattern=repr(match_pattern),
                        etype=type(e).__name__,
                        error=e,
                    )
                )
                continue
            parsedict_update = {}
            for key, value in parsedict.items():
                try:
                    new_value, n_replacements = re.subn(
                        string=value,
                        pattern=match_pattern,
                        repl=replace_pattern,
                        flags=re.IGNORECASE,
                    )
                except BaseException as e:
                    logger.error(
                        "Could not apply replacement "
                        "{pattern} --> {replacement} on {key} value {value}: "
                        "{etype}: {error}".format(
                            pattern=repr(match_pattern),
                            replacement=repr(replace_pattern),
                            key=repr(key),
                            value=repr(value),
                            etype=type(e).__name__,
                            error=e,
                        )
                    )
                    continue
                if not n_replacements:
                    continue
                new_key = repl_dict.get("new_key")
                if not new_key:
                    new_key = key
                if new_key in parsedict or new_key in parsedict_update:
                    logger.debug(
                        "Replacing {key} value "
                        "{value} with {new_value}".format(
                            key=repr(new_key),
                            value=repr(value),
                            new_value=repr(new_value),
                        )
                    )
                else:
                    logger.debug(
                        "Adding new key {key} with value {new_value}".format(
                            key=repr(new_key), new_value=repr(new_value)
                        )
                    )
                parsedict_update[new_key] = new_value
            parsedict.update(parsedict_update)

        measurement = next(
            filter(
                lambda x: x is not None,
                map(
                    self.to_float,
                    filter(
                        bool,
                        map(
                            partial(self.fmtfill, **parsedict),
                            self.measurement_pattern,
                        ),
                    ),
                ),
            ),
            None,
        )
        if measurement is None:
            logger.error(
                "Don't know what to use as measurement. "
                "None of the measurement patterns ({}) yielded something "
                "usable as a number".format(
                    ", ".join(
                        map(
                            " ==> ".join,
                            zip(
                                map(repr, self.measurement_pattern),
                                map(
                                    repr,
                                    map(
                                        partial(self.fmtfill, **parsedict),
                                        self.measurement_pattern,
                                    ),
                                ),
                            ),
                        )
                    )
                )
            )
            return None

        logger.debug("Measurement: {}".format(measurement))

        matching_sensor = self.find_matching_sensor(**parsedict)
        if not matching_sensor:
            return None

        logger.debug(
            "Passing {measurement} for upload "
            "to sensor '{sensor.title}' of "
            "senseBox '{box.name}' to queue".format(
                measurement=measurement,
                sensor=matching_sensor,
                box=matching_sensor.box,
            )
        )
        self.opensensemap_upload_queue.add(
            matching_sensor.box.id, matching_sensor.id, measurement
        )
