# system modules
import collections
import configparser
import copy
import functools
import itertools
import logging
import os
import re

from sensemapi.account import SenseMapAccount, SenseMapAccountCollection
from sensemapi.cache import SQLiteAuthentiCache
from sensemapi.reprobject import ReprObject
from sensemapi.utils import *
from sensemapi.xdg import *

# external modules


logger = logging.getLogger(__name__)


class SenseMapApplication(ReprObject):
    """
    Class for applications using :mod:`sensemapi`
    """

    def __init__(self, name=None, version=None, accounts=None):
        frame = inspect.currentframe()
        args = inspect.getargvalues(frame)[0]
        for arg in args[1:]:
            val = locals().get(arg)
            if val is not None:
                setattr(self, arg, val)
        self.read_config()

    @simplegetter
    def name(self):
        return self.__class__.__name__

    @property
    def sanitized_name(self):
        return re.sub("--+", "-", re.sub(r"\W", "-", self.name)).lower()

    @simplesetter(name)
    def name(self, new):
        return str(new or self.__class__.__name__)

    @simplegetter
    def version(self):
        return None

    @simplesetter(version)
    def version(self, new):
        return new

    @simplegetter
    def config(self):
        return configparser.ConfigParser()

    @simplesetter(config)
    def config(self, new):
        return new

    @property
    def app_config(self):
        if "application" not in self.config:
            self.config.add_section("application")
        return self.config["application"]

    @simplegetter
    def accounts(self):
        accounts = SenseMapAccountCollection()
        accounts.application = self
        return accounts

    @simplesetter(accounts)
    def accounts(self, new):
        new.application = self
        return new

    @property
    def current_account_index(self):
        try:
            index = self._current_account_index
        except AttributeError:
            index = None
        if self.accounts:
            if index not in range(len(self.accounts)):
                index = 0
                self._current_account_index = index
            else:
                # use the setter to save the changes
                self.current_account_index = index
        else:
            index = None
            self._current_account_index = index
        return self._current_account_index

    @current_account_index.setter
    def current_account_index(self, new):
        try:
            self.accounts[new]
        except (IndexError, ValueError, KeyError, TypeError) as e:
            logger.warning(
                "Cannot use '{}' as current account index: {}".format(new, e)
            )
            new = 0 if self.accounts else None
        self._current_account_index = new
        old_current_account_index = self.app_config.getint(
            "current_account_index"
        )
        if new is not None:
            self.app_config["current_account_index"] = str(new)
        else:
            self.app_config.pop("current_account_index", None)
        if old_current_account_index != new:
            self.write_config()

    @property
    def current_account(self):
        if len(self.accounts):
            if self.current_account_index is not None:
                try:
                    return self.accounts[self.current_account_index]
                except (IndexError, ValueError, KeyError, TypeError):
                    if hasattr(self, "_current_account_index"):
                        del self._current_account_index
                return self.accounts[self.current_account_index]
        else:
            return None

    @current_account.setter
    def current_account(self, new):
        self.current_account_index = self.accounts.index(new)

    @simplegetter
    def auth_cache(self):
        return SQLiteAuthentiCache(
            directory=XDGPackageDirectory(
                "XDG_CACHE_HOME", packagename=self.name
            ).path
        )

    @simplegetter
    def request_cache(self):
        return None

    @request_cache.setter
    def request_cache(self, new):
        self._request_cache = new
        for account in self.accounts:
            account.request_cache = self.request_cache

    @property
    def config_file(self):
        with XDGPackageDirectory(
            "XDG_CONFIG_HOME", packagename=self.sanitized_name
        ) as configdir:
            return os.path.join(
                configdir, "{}.conf".format(self.sanitized_name)
            )

    def read_config(self):
        try:
            with open(self.config_file) as fh:
                logger.debug(
                    "Reading from configuration file '{}'".format(
                        self.config_file
                    )
                )
                self.config.read_file(fh)
        except (FileNotFoundError):
            logger.info(
                "Configuration file '{}' does not exist.".format(
                    self.config_file
                )
            )
            return False
        del self.accounts[:]
        for section_name in self.config:
            if "account" in section_name:
                section = self.config[section_name]
                account = SenseMapAccount(
                    email=section.get("email") or None,
                    username=section.get("username") or None,
                    api=section.get("api") or None,
                    cache_password=section.getboolean("cache_password"),
                    auth_cache=self.auth_cache
                    if section.getboolean("auth_cache")
                    else None,
                )
                self.accounts.append(account)
        self.current_account_index = self.app_config.getint(
            "current_account_index"
        )

    def write_config(self):
        # remove all account sections from the configuration
        for section_name in list(self.config):
            if "account" in section_name:
                self.config.remove_section(section_name)
        # fill the account sections
        nr = itertools.count(0)
        for account in self.accounts:
            section_name = "account:{}".format(next(nr))
            self.config.add_section(section_name)
            section = self.config[section_name]
            for option in (
                "email",
                "username",
                "api",
                "auth_cache",
                "cache_password",
            ):
                val = getattr(account, option)
                if val is None:
                    continue
                elif isinstance(val, bool) or not isinstance(val, str):
                    section[option] = "yes" if bool(val) else "no"
                elif val:
                    section[option] = str(val)
        # write the config
        with open(self.config_file, "w") as fh:
            logger.debug(
                "Writing configuration file '{}'".format(self.config_file)
            )
            self.config.write(fh)
        return True

    def __del__(self):
        self.write_config()
