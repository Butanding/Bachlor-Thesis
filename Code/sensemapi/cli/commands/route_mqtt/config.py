# system modules
import logging
import configparser
from functools import partial
from collections import OrderedDict
import operator
import random
import itertools
import re
from urllib.parse import urlparse

# internal modules
import sensemapi
from sensemapi.cli.commands.route_mqtt.client import SelectiveMQTTClient

# external modules
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class ConfigurationError(ValueError):
    pass


class BrokerSectionError(ConfigurationError):
    pass


class Configuration(configparser.ConfigParser):
    """
    Class for configuration
    """

    BROKER_SECTION_PREFIX = "broker"
    """
    Prefix for sections specifying an MQTT broker
    """

    @property
    def opensensemap_account(self):
        """
        Set up a :any:`SenseMapAccount`
        """
        account = sensemapi.account.SenseMapAccount()
        if "opensensemap" in self:
            for a in ("username", "password", "email"):
                setattr(account, a, self["opensensemap"].get(a))
            hostname = self["opensensemap"].get("hostname")
            if hostname:
                account.api = "https://{}".format(hostname)
        return account

    @property
    def broker_sections(self):
        """
        Generator yielding source sections

        Yields:
            configparser.SectionProxy: the next source section
        """
        for name, section in self.items():
            if name.startswith(self.BROKER_SECTION_PREFIX):
                yield section

    @property
    def clients(self):
        """
        Generator yielding set-up clients from the sections

        Yields:
            paho.mqtt.client.Client: the set-up but unstarted clients
        """
        for section in self.broker_sections:
            client_name = section.get(
                "client-name",
                "sensemapi-{}".format(random.randint(1, 2 ** 16 - 1)),
            )
            client = SelectiveMQTTClient(client_name)
            client.username_pw_set(
                section.get("username"), section.get("password")
            )

            def regex_from_str(string):
                try:
                    return re.compile(string, re.IGNORECASE)
                except re.error as e:
                    raise BrokerSectionError(
                        "Invalid regular expression {}: {}".format(
                            repr(string), e
                        )
                    )

            client.parse_topic_regexes = tuple(
                map(
                    regex_from_str,
                    filter(
                        bool,
                        re.split(
                            r"\s*[\r\n]+\s*",
                            section.get("parse_topic", r"^(?P<quantity>.*)$"),
                        ),
                    ),
                )
            )

            client.parse_message_regexes = tuple(
                map(
                    regex_from_str,
                    filter(
                        bool,
                        re.split(
                            r"\s*[\r\n]+\s*",
                            section.get(
                                "parse_message", r"^(?P<value>[0-9.-]+)$"
                            ),
                        ),
                    ),
                )
            )

            client.subscribed_topics_when_connected = tuple(
                filter(
                    bool,
                    re.split(r"\s*[\r\n]+\s*", section.get("subscribe", "#")),
                )
            )

            client.sensebox_match = tuple(
                filter(
                    bool,
                    re.split(
                        r"\s*[\r\n]+\s*",
                        section.get(
                            "sensebox_match",
                            "{box}\n{sensebox}\n"
                            "{sensebox_id}\n{sensebox_name}",
                        ),
                    ),
                )
            )

            client.sensor_match = tuple(
                filter(
                    bool,
                    re.split(
                        r"\s*[\r\n]+\s*",
                        section.get(
                            "sensor_match",
                            "{sensor}\n{sensor_id}\n{sensor_title}",
                        ),
                    ),
                )
            )

            client.measurement_pattern = tuple(
                filter(
                    bool,
                    re.split(
                        r"\s*[\r\n]+\s*",
                        section.get(
                            "measurement", "{value}\n{measurement}\n{data}"
                        ),
                    ),
                )
            )

            client.minimum_match = tuple(
                filter(
                    bool,
                    map(
                        partial(re.split, r"\s*,\s*", maxsplit=1),
                        filter(
                            bool,
                            re.split(
                                r"\s*[\r\n]+\s*",
                                section.get("minimum_match", ""),
                            ),
                        ),
                    ),
                )
            )

            client.replacements = tuple(
                map(
                    operator.methodcaller("groupdict"),
                    filter(
                        bool,
                        map(
                            lambda s: re.fullmatch(
                                string=s,
                                pattern=(
                                    r"(?P<pattern>.*?)"
                                    r"\s+=\s+(?P<replacement>.*?)"
                                    r"(?:\s+[=-]+>+\s+(?P<new_key>\w+))?"
                                ),
                                flags=re.IGNORECASE,
                            ),
                            filter(
                                bool,
                                re.split(
                                    r"\s*[\r\n]+\s*",
                                    section.get("replace", ""),
                                ),
                            ),
                        ),
                    ),
                )
            )

            client.connect_async(
                section.get("hostname", "localhost"),
                section.getint("port", 1883),
            )
            yield client

    def add_section(self, name):
        """
        Add a new section with :any:`configparser.ConfigParser.add_section` but
        but if the name already exists, append something so that it doesn't
        exist.

        Args:
            name (str): the name of the new section

        Returns:
            Section : the newly created section
        """
        nonexistant_name = next(
            filter(
                lambda x: x not in self,
                itertools.chain(
                    (name,),
                    (
                        " ".join(map(str, (name, "nr.", nr)))
                        for nr in itertools.count(2)
                    ),
                ),
            )
        )
        configparser.ConfigParser.add_section(self, nonexistant_name)
        return self[nonexistant_name]
