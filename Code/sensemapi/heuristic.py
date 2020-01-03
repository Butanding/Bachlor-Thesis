# system modules
import logging
import calendar
import datetime
from email.utils import parsedate, formatdate

# internal modules
from sensemapi.utils import *

# external modules
from cachecontrol.heuristics import BaseHeuristic
from cachecontrol.cache import BaseCache

logger = logging.getLogger(__name__)


class CacheHeuristic(BaseHeuristic):
    """
    Heuristic to mock cache-control and expires header for API responses
    """

    def update_headers(self, response):
        if "date" in response.headers:
            date = parsedate(response.headers["date"])
        else:
            logger.info("No 'date' in headers. Using current time.")
            date = datetime.datetime.utcnow().timetuple()
        expires = datetime.datetime(*date[:6]) + datetime.timedelta(days=7)
        extra_headers = {
            "expires": formatdate(calendar.timegm(expires.timetuple())),
            "cache-control": "public",
        }
        return extra_headers

    def warning(self, response):
        msg = "Automatically cached! Response might be stale."
        return "110 - '{}'".format(msg)
