# system modules
import collections
import csv
import datetime
import functools
import inspect
import json
import logging
import os
import re

from sensemapi.errors import *

# external modules

logger = logging.getLogger(__name__)


def catch(exceptions, f, *args, **kwargs):
    """
    Execute a callable, catch specific exceptions and return value accordingly

    Args:
        exceptions (dict): mapping of exceptions to return values
        f (callable): the function to call
        args, kwargs: arguments passed to the function

    Returns:
        the return value of ``f`` or the proper value in ``exceptions`` if an
        exception was raised
    """
    try:
        return f(*args, **kwargs)
    except BaseException as e:
        for exception, retval in exceptions.items():
            if issubclass(type(e), exception):
                return retval
        raise


OPENSENSEMAP_DATETIME_FORMAT_UTC_MS = "%Y-%m-%dT%H:%M:%S.%fZ"
OPENSENSEMAP_DATETIME_FORMAT_UTC = "%Y-%m-%dT%H:%M:%SZ"


def unique(iterable):
    """
    Generator yielding only unique elements

    Args:
        iterable (iterable): iterable of :any:`hash`-able objects
    """
    seen = set()
    for x in iterable:
        if x in seen:
            continue
        else:
            seen.add(x)
            yield x


def str2date(s):
    """
    Convert a string in OpenSenseMap-RFC3339 format to a Python
    :any:`datetime.datetime` object.

    Args:
        s (str) : the string to convert. Needs to be in OpenSenseMap-RFC3339
            format.

    Returns:
        datetime.datetime : the converted date
    """
    for fmt in [
        OPENSENSEMAP_DATETIME_FORMAT_UTC_MS,
        OPENSENSEMAP_DATETIME_FORMAT_UTC,
    ]:
        try:
            d = datetime.datetime.strptime(s, fmt)
            d = d.replace(tzinfo=datetime.timezone.utc)
            return d
        except ValueError:
            pass
    raise ValueError("Could not parse date '{}' string".format(s))


def date2str(d):
    """
    Stringify a :any:`datetime.datetime` object to RFC3339 format

    Args:
        d (datetime.datetime) : the datetime to convert

    Returns:
        str : the converted string
    """
    try:
        utc = d.astimezone(datetime.timezone.utc)
    except ValueError:
        utc = d.replace(tzinfo=datetime.timezone.utc)
    s = utc.strftime(OPENSENSEMAP_DATETIME_FORMAT_UTC_MS)
    return re.sub(
        string=s,
        pattern=r"(\.\d{3})\d{3}([a-z])$",
        repl=r"\1\2",
        flags=re.IGNORECASE,
    )


def pretty_json(d):  # pragma: no cover
    """
    Pretty-format a JSON dict

    Args:
        d (dict) : the JSON dict

    Returns:
        str : the formatted string
    """
    return json.dumps(d, sort_keys=True, indent=4)


def read_csv(f, *args, **kwargs):
    """
    Read CSV from file and return a dict

    Args:
        f (filehandle): file handle
        args, kwargs: arguments passed to :any:`csv.DictReader`

    Returns:
        dict : keys are column names, values are column data
    """
    d = {}
    csvreader = csv.DictReader(f, *args, **kwargs)

    def convert(x):
        try:
            return float(x)
        except ValueError:
            try:
                return str2date(x)
            except ValueError:
                return x

    d = dictlist_to_listdict(csvreader, fun=convert)
    return d


def write_csv(f, d, headersortkey=lambda x: x, *args, **kwargs):
    """
    Write CSV dict to file

    Args:
        f (filehandle): writeable file handle
        headersortkey (callable): ``key`` argument to :any:`sorted` to sort the
            header columns
        args, kwargs: arguments passed to :any:`csv.DictWriter`
    """
    csvwriter = csv.DictWriter(
        f, fieldnames=sorted(d.keys(), key=headersortkey), *args, **kwargs
    )
    L = listdict_to_dictlist(d)
    csvwriter.writeheader()
    for row in L:
        csvwriter.writerow(row)


def listdict_to_dictlist(d):
    """
    Convert a :any:`dict` of lists to a list of dicts

    Args:
        d (dict): the dict of lists

    Returns:
        list : list of dicts
    """
    return (dict(zip(d, t)) for t in zip(*d.values()))


def dictlist_to_listdict(l, fun=lambda x: x):
    """
    Convert a list of dicts to a dict of lists

    Args:
        l (list): the list of dicts
        fun (callable): callable to manipulate the values

    Returns:
        dict : dict of lists
    """
    d = collections.defaultdict(list)
    for e in l:
        for k, v in e.items():
            d[k].append(fun(v))
    return dict(d)


def location_dict(lat=None, lon=None, height=None):
    """
    Create a location dict from the single values

    Args:
        lat, lon, height (float, optional) : the position

    Returns:
        dict : the location dict

    Raises:
        ValueError : if not enough values are specified
    """
    if lat is not None and lon is not None:
        if height is not None:
            return {"lat": lat, "lng": lon, "height": height}
        else:
            return {"lat": lat, "lng": lon}
    else:
        raise ValueError("At least 'lat' and 'lon' need to be defined")


def simplegetter(fn):  # pragma: no cover
    """
    Property getter method decorator for easy getter setup. Getter methods
    decorated with this decorator should return the default value. When the
    property is requested, it is checked whether the internal attribute
    prefixed with ``_`` exists and if so it is returned. If not, it is set
    to the return value of the decorated method and then it is returned.

    Parameters
    ----------

    Returns
    -------

    callable
        The decorated callable
    """
    propname = fn.__name__
    attrname = "_{}".format(propname)
    try:
        inspect.getfullargspec(fn)[0]
    except KeyError:  # pragma: no cover
        raise ValueError(
            "`simplegetter` decorator can only be used for methods that take "
            "the object reference as first argument"
        )

    @property
    @functools.wraps(fn)
    def getter(self):
        try:
            return getattr(self, attrname)
        except AttributeError:
            fnval = fn(self)
            setattr(self, attrname, fnval)
        return getattr(self, attrname)

    return getter


def simplesetter(prop, del_on_exceptions=()):  # pragma: no cover
    """
    Property setter method decorator for easy setter setup. Setter methods
    decorated with this decorator should take the object reference and the new
    value as argument, modify the value as desired and return it. The return
    value will be stored in the internal attribute prefixed with
    ``_``.

    Parameters
    ----------

    prop : property
        the property
    del_on_exceptions : sequence of BaseException subclasses
        delete the internal attribute if any of these in
        :any:`exceptions` occur

    Returns
    -------

    callable
        The decorated callable
    """

    def simplesetter_decorator(fn):
        propname = fn.__name__
        attrname = "_{}".format(propname)
        try:
            inspect.getfullargspec(fn)[0]
            inspect.getfullargspec(fn)[1]
        except KeyError:  # pragma: no cover
            raise ValueError(
                "`simplegetter` decorator can only be used for methods that "
                "take the object reference as first argument and the new "
                "property value as second argument"
            )

        def setter(self, newval):
            try:
                converted = fn(self, newval)
                setattr(self, attrname, converted)
            except del_on_exceptions:
                try:
                    delattr(self, attrname)
                except AttributeError:
                    pass

        setter.__doc__ = fn.__doc__
        setter = prop.setter(setter)
        return setter

    return simplesetter_decorator


def needs_pandas(f):
    """
    Decorator for methods requiring :mod:`pandas` to be installed
    """

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            import pandas
        except ImportError:  # pragma: no cover
            raise NoPandasError
        f.__globals__["pandas"] = pandas
        return f(*args, **kwargs)

    return wrapper


def needs_cachecontrol(f):
    """
    Decorator for methods requiring :mod:`cachecontrol` to be installed
    """

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            import cachecontrol
        except ImportError:  # pragma: no cover
            raise NoCacheControl
        f.__globals__["cachecontrol"] = cachecontrol
        return f(*args, **kwargs)

    return wrapper
