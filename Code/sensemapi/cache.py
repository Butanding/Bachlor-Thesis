# system modules
import datetime
import functools
import inspect
import itertools
import os
import re
import sqlite3
from abc import ABC, abstractmethod, abstractproperty

from sensemapi.reprobject import ReprObject
from sensemapi.utils import *
from sensemapi.xdg import *

# external modules


class AuthentiCache(ABC, ReprObject):
    """
    Abstract base class for authentication caches

    Args:
        directory (str, optional): the cache directory
        name (str, optional): the cache name
    """

    def __init__(self, directory=None, name=None):
        frame = inspect.currentframe()
        args = inspect.getargvalues(frame)[0]
        for arg in args[1:]:
            val = locals().get(arg)
            if val is not None:
                setattr(self, arg, val)

    @simplegetter
    def directory(self):
        return XDGPackageDirectory("XDG_CACHE_HOME").path

    @simplesetter(directory)
    def directory(self, new):
        return Directory(new).path

    @simplegetter
    def name(self):
        return "authentication"

    @simplesetter(name)
    def name(self, new):  # pragma: no cover
        return str(new)

    @abstractproperty
    def suffix(self):
        pass

    @abstractmethod
    def get(
        self,
        conditions,
        all_inner=True,
        all_outer=True,
        match_inner=True,
        match_outer=True,
    ):
        """
        Given conditions, retrieve matching cache values

        Args:
            conditions (sequence of dict, optional):
                dictionaries mapping column names to expected values.
            all_inner (sequence of bool, optional): whether all conditions
                specified in a single condition in ``conditions`` should be
                matched together
            all_outer (sequence of bool, optional): whether all ``conditions``
                should be matched together
            match_inner (sequence of bool, optional): whether all conditions
                specified in a single condition in ``conditions`` should be
                matched (or negated)
            match_outer (sequence of bool, optional): whether all
                ``conditions`` should be matched (or negated)

        Returns:
            sequence : the matching entries
        """
        pass

    @abstractmethod
    def delete(self, condition=()):
        """
        Delete cache entr(y/ies) matching condition. If called without
        arguments, deletes the whole cache.
        """
        pass

    @abstractmethod
    def sync(self, cache):
        """
        Given cache values, update the cache where necessary and return
        up-to-date values.

        Args:
            cache (dict) : cache data with any of keys email, username, api,
                token, token_time, refresh_token, refresh_token_time. Keys that
                are not provided are ignored.

        Returns
            dict : the updated cache data
        """
        pass


class SQLiteAuthentiCache(AuthentiCache):
    """
    Authentication cache using :mod:`sqlite3` as storage.
    """

    @staticmethod
    def sanitize(string, brutally=False):
        return re.sub(r"\W" if brutally else "['\";]", "", string)

    @property
    def suffix(self):
        return "sqlite"

    @property
    def connection(self):
        with Directory(self.directory) as d:
            conn = sqlite3.connect(
                os.path.join(d, "{}.{}".format(self.name, self.suffix)),
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            conn.row_factory = sqlite3.Row
            return conn

    @property
    def table(self):
        return "authentication"

    @property
    def table_exists(self):
        with self.connection as conn:
            return any(
                self.table in row
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            )

    @property
    def tableheader(self):
        self.create_table()
        with self.connection as conn:
            cursor = conn.execute(
                "SELECT * from {cache.table}".format(cache=self)
            )
            return tuple(map(lambda x: x[0], cursor.description))

    @property
    def primary_keys(self):
        return ("email", "username", "api")

    def create_table(self):
        if not self.table_exists:
            with self.connection as conn:
                sql = (
                    "CREATE TABLE {cache.table} "
                    "(email, username, password, api, "
                    "token, token_time timestamp, "
                    "refresh_token, refresh_token_time timestamp, "
                    "PRIMARY KEY ({primary_keys}) "
                    ")"
                ).format(cache=self, primary_keys=",".join(self.primary_keys))
                logger.debug("SQL: {}".format(sql))
                conn.execute(sql)
                return True
        return False

    def sql_insert(self, row):
        """
        Generate SQL expression to insert

        Args:
            rows (dict): the row to insert with keys corresponding to the
                columns

        Returns:
            str, sequence : the SQL expression to use after
                ``INSERT INTO table...`` and the corresponding parameters
        """
        return (
            "({columns}) VALUES ({values})".format(
                columns=",".join(row.keys()), values=",".join("?" for c in row)
            ),
            tuple(row.values()),
        )

    def sql_update(self, old_row, new_row):
        """
        Generate SQL expression to update
        """
        assert old_row and new_row, "both old_row and new_row mustn't be empty"
        sql_cond, sql_cond_params = self.sql_condition(old_row)
        return (
            "SET {assignments} WHERE {condition}".format(
                assignments=",".join(map("{} = ?".format, new_row.keys())),
                condition=sql_cond,
            ),
            tuple(new_row.values()) + sql_cond_params,
        )

    def sql_condition(
        self,
        conditions=tuple(),
        all_inner=True,
        all_outer=True,
        match_inner=True,
        match_outer=True,
    ):
        """
        Generate an SQL conditional expression according to exact conditions.
        All arguments are :func:`itertools.cycle` d accordingly.

        Args:
            conditions (sequence of dict, optional):
                dictionaries mapping column names to expected values. If this
                sequence is empty, a condition that is always true is returned.
            all_inner (sequence of bool, optional): whether all conditions
                specified in a single condition in ``conditions`` should be
                matched together
            all_outer (sequence of bool, optional): whether all ``conditions``
                should be matched together
            match_inner (sequence of bool, optional): whether all conditions
                specified in a single condition in ``conditions`` should be
                matched (or negated)
            match_outer (sequence of bool, optional): whether all
                ``conditions`` should be matched (or negated)

        Returns:
            str, sequence : an SQL expression which can be used with ``WHERE``
                and the corresponding parameters
        """
        args = locals()
        # put the conditions into a dict
        conds = {
            pref: args.get(pref)
            for pref in (
                "all_inner",
                "all_outer",
                "match_inner",
                "match_outer",
            )
        }
        conds = {  # properly cycle all settings
            pref: itertools.cycle(val if hasattr(val, "__iter__") else (val,))
            for pref, val in conds.items()
        }
        conds["values"] = (
            (conditions,) if hasattr(conditions, "items") else conditions
        )
        sql_conditions, sql_params = [], []
        for cond in listdict_to_dictlist(conds):
            sanitized_values = {
                self.sanitize(k, brutally=True): self.sanitize(
                    v, brutally=False
                )
                if isinstance(v, str)
                else v
                for k, v in cond["values"].items()
                if k in self.tableheader
            }
            inner_sql_cond = (" AND " if cond["all_inner"] else " OR ").join(
                map(
                    "{} {} ?".format,
                    sanitized_values.keys(),
                    itertools.cycle(
                        ("IS" if cond["match_inner"] else "IS NOT",)
                    ),
                )
            ) or "1=1"
            sql_conditions.append(
                "{}({})".format(
                    "" if cond["match_outer"] else "NOT ", inner_sql_cond
                )
            )
            sql_params.extend(tuple(sanitized_values.values()))
        sql_condition = (
            functools.reduce(
                lambda x, y: (
                    " AND " if next(conds["all_outer"]) else " OR "
                ).join((x, y)),
                sql_conditions,
            )
            if sql_conditions
            else "1=1"
        )
        return sql_condition, tuple(sql_params)

    def matching_rows(self, condition):
        """
        Perform greedy matching, then less greedy matching to find matching
        rows.

        Args:
            condition (dict): dictionary of column names and values

        Returns:
            sequence : the matching row(s)
        """

        def two_primary_keys_and_api(seq):
            return (
                len(set(self.primary_keys).intersection(seq)) >= 2
                and "api" in seq
            )

        for i in range(len(condition) - 1):
            for comb in filter(
                two_primary_keys_and_api,
                itertools.combinations(condition, len(condition) - i),
            ):
                logger.debug("Checking combination {}".format(comb))
                cond = {k: condition.get(k) for k in comb}
                matching = self.get(cond)
                if matching:
                    logger.debug(
                        "Matching entr(y/ies) for "
                        "combination {}:\n{}".format(comb, matching)
                    )
                    return matching
                else:
                    logger.debug("No entries for combination {}".format(comb))
        return tuple()

    def get(self, *args, **kwargs):
        """
        Retrieve cache according to conditions. For arguments, see
        :meth:`sql_condition`.
        """
        sql_cond, sql_params = self.sql_condition(*args, **kwargs)
        with self.connection as conn:
            sql = "SELECT * FROM {cache.table} {condition}".format(
                condition=("WHERE " + sql_cond) if sql_cond else sql_cond,
                cache=self,
            )
            logger.debug("SQL:\n{}\nparameters: {}".format(sql, sql_params))
            return tuple(map(dict, conn.execute(sql, sql_params)))

    def delete(self, condition=()):
        sql_cond, sql_params = self.sql_condition(condition)
        with self.connection as conn:
            sql = "DELETE FROM {cache.table} {condition}".format(
                condition=("WHERE " + sql_cond) if sql_cond else sql_cond,
                cache=self,
            )
            logger.debug("SQL:\n{}\nparameters: {}".format(sql, sql_params))
            return conn.execute(sql, sql_params)

    def sync(self, cache):
        logger.debug("Trying to determine entry matching {}".format(cache))
        primary_key_equal = {
            k: v
            for k, v in cache.items()
            if k in self.primary_keys and v is not None
        }
        matching_rows = self.matching_rows(primary_key_equal)
        logger.debug("Matching cache entr(y/ies):\n{}".format(matching_rows))
        ancient = datetime.datetime.min
        if len(matching_rows) > 1:
            logger.warning(
                "There are duplicate rows:\n{}\n"
                "Using the first one.".format(matching_rows)
            )
        try:
            matching_row = matching_rows[0]
        except IndexError:
            matching_row = matching_rows
        if matching_row:
            to_save = cache.copy()
            our_to = matching_row.get("token")
            their_to = cache.get("token")
            our_reto = matching_row.get("refresh_token")
            their_reto = cache.get("refresh_token")
            our_toti = matching_row.get("token_time", ancient) or ancient
            our_retoti = (
                matching_row.get("refresh_token_time", ancient) or ancient
            )
            their_toti = cache.get("token_time", ancient) or ancient
            their_retoti = cache.get("refresh_token_time", ancient) or ancient
            their_to_younger = their_toti > our_toti
            logger.debug(
                "Given token '{}' from '{}' is {}newer than "
                "ours from ('{}').".format(
                    their_to,
                    their_toti,
                    "" if their_to_younger else "not ",
                    our_toti,
                )
            )
            if their_to_younger:
                logger.debug("Using newer given token '{}'".format(their_to))
                to_save["token"] = their_to
                to_save["token_time"] = their_toti
            else:
                logger.debug("Ignoring given token '{}'".format(their_to))
                to_save.pop("token", None)
                to_save.pop("token_time", None)
            their_reto_younger = their_retoti > our_retoti
            logger.debug(
                "Given refresh token '{}' from '{}' is {}newer than "
                "ours from ('{}').".format(
                    their_reto,
                    their_retoti,
                    "" if their_reto_younger else "not ",
                    our_retoti,
                )
            )
            if their_reto_younger:
                logger.debug(
                    "Using newer given refresh token '{}'".format(their_reto)
                )
                to_save["refresh_token"] = their_reto
                to_save["refresh_token_time"] = their_retoti
            else:
                logger.debug(
                    "Ignoring given refresh token '{}'".format(their_reto)
                )
                to_save.pop("refresh_token", None)
                to_save.pop("refresh_token_time", None)
            if to_save.items() <= matching_row.items():
                logger.debug(
                    "No need to update\n{}\nwith\n{},"
                    "\nno new information".format(matching_row, to_save)
                )
                return matching_row
            logger.debug(
                "Will update\n{}\nwith\n{}".format(matching_row, to_save)
            )
            sql_update, sql_params = self.sql_update(matching_row, to_save)
            sql = "UPDATE {cache.table} {update}".format(
                cache=self, update=sql_update
            )
            logger.debug("SQL:\n{}\nparameters:{}".format(sql, sql_params))
            with self.connection as conn:
                conn.execute(sql, sql_params)
            updated_row = matching_row.copy()
            updated_row.update(to_save)
            return updated_row
        else:
            logger.debug("Will create entry {}".format(cache))
            sql_insert_data, sql_params = self.sql_insert(cache)
            sql_insert = "INSERT INTO {cache.table} {data}".format(
                cache=self, data=sql_insert_data
            )
            logger.debug(
                "SQL:\n{}\nparameters: {}".format(sql_insert, sql_params)
            )
            with self.connection as conn:
                conn.execute(sql_insert, sql_params)
            return cache
