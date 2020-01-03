# system modules
import collections
import datetime
import functools
import glob
import hashlib
import inspect
import itertools
import json
import logging
import os
import re
import time
from contextlib import contextmanager
from posixpath import join as urljoin

# external modules
import requests

# internal modules
from sensemapi import compat, paths
from sensemapi.client import SenseMapClient
from sensemapi.errors import *
from sensemapi.senseBox import senseBox, senseBoxCollection
from sensemapi.utils import *
from sensemapi.xdg import *

logger = logging.getLogger(__name__)


class SenseMapAccount(SenseMapClient):
    """
    Client to interface an `OpenSenseMap <https://opensensemap.org>`_ account
    via the `OpenSenseMap API <https://api.opensensemap.org>`_

    Args:
        email (str, optional): the user's login email address
        username (str, optional): the user's login name
        password (str, optional): the user's login password
        api (str, optional): the api server to use. You may use
            :any:`OPENSENSEMAP_API_LIVE` (default) or
            :any:`OPENSENSEMAP_API_TEST` for testing purposes.
        token (str, optional): the JSON Web Token
        token_time (str, optional): retrieval time of the JSON Web Token
        refresh_token (str, optional): the refresh JSON Web Token
        refresh_token_time (str, optional): retrieval time of the refresh JSON
            Web Token
        auth_cache (AuthentiCache, optional): The authentication cache to use.
            Defaults to no cache.
        request_cache (cachecontrol.adapter.CacheControlAdapter, optional):
            request cache. Defaults to no cache.
        cache_password (bool, optional): cache the password (in plain text)?
            Defaults to ``False``. Only used if ``auth_cache`` is set.
        connection_timeout (float, optional): default connection timeout
            for requests in seconds. Default is no timeout.
        response_timeout (float, optional): default response timeout
            for requests in seconds. Default is no timeout.
    """

    def __init__(
        self,
        email=None,
        username=None,
        password=None,
        token=None,
        token_time=None,
        refresh_token=None,
        refresh_token_time=None,
        api=None,
        cache_password=None,
        auth_cache=None,
        request_cache=None,
        connection_timeout=None,
        response_timeout=None,
    ):
        frame = inspect.currentframe()
        args = inspect.getargvalues(frame)[0]
        for arg in args[1:]:
            val = locals().get(arg)
            if val is not None:
                setattr(self, arg, val)

    def sync_auth_cache_afterwards(decorated_function):
        """
        Decorator for methods to call :meth:`sync_auth_cache` after
        completition
        """

        @functools.wraps(decorated_function)
        def wrapper(self, *args, **kwargs):
            ret = decorated_function(self, *args, **kwargs)
            if self.auth_cache:
                logger.debug(
                    "calling sync_auth_cache after {}".format(
                        decorated_function
                    )
                )
                self.sync_auth_cache()
            return ret

        return wrapper

    @simplegetter
    def api(self):
        return paths.OPENSENSEMAP_API_LIVE

    @api.setter
    @sync_auth_cache_afterwards
    @SenseMapClient.modifies_session
    def api(self, new):
        self._api = new

    @simplegetter
    def email(self):
        return None

    @email.setter
    @sync_auth_cache_afterwards
    def email(self, new):
        self._email = new

    @simplegetter
    def username(self):
        return None

    @username.setter
    @sync_auth_cache_afterwards
    def username(self, new):
        self._username = new

    @simplegetter
    def password(self):
        return None

    @password.setter
    @sync_auth_cache_afterwards
    def password(self, new):
        self._password = new

    @simplegetter
    def role(self):
        return None

    @simplesetter(role)
    def role(self, new):
        return new

    @simplegetter
    def language(self):
        return None

    @simplesetter(language)
    def language(self, new):
        return new

    @simplegetter
    def application(self):
        return None

    @application.setter
    def application(self, app):
        self._application = app

    @simplegetter
    def auth_cache(self):
        return None

    @auth_cache.setter
    @sync_auth_cache_afterwards
    def auth_cache(self, new):
        if new:
            if all(map(lambda x: hasattr(new, x), ("get", "sync"))):
                self._cache = new
            else:
                if self.application:
                    if self.application.auth_cache:
                        self._cache = self.application.auth_cache
                    else:
                        raise ValueError(
                            "{} object is not suitable as cache and "
                            "this account's associated application does not "
                            "have a cache".format(type(new).__name__).format(
                                new
                            )
                        )
                else:
                    raise ValueError(
                        "{} object is not suitable as cache and "
                        "this account does not have an associated "
                        "application".format(type(new).__name__).format(new)
                    )
        self._auth_cache = new

    @property
    def request_cache(self):
        """
        The request cache for this account.

        :getter: if a cache has already been set on this account, return it.
            Otherwise, return this account's application's
            :meth:`SenseMapApplication.request_cache` if available.
        """
        try:
            return self._request_cache
        except AttributeError:
            if self.application:
                return self.application.request_cache
            else:
                return None

    @request_cache.setter
    def request_cache(self, new):
        self._request_cache = new

    @simplegetter
    def cache_password(self):
        return False

    @cache_password.setter
    @sync_auth_cache_afterwards
    def cache_password(self, new):
        self._cache_password = bool(new)

    @property
    def boxes(self):
        try:
            self._boxes
        except AttributeError:
            self._boxes = senseBoxCollection()
            self._boxes.client = self
        return self._boxes

    @boxes.setter
    def boxes(self, new):  # pragma: no cover
        if hasattr(new, "boxes"):  # is already a senseBoxCollection
            self._boxes = new
        else:
            self._boxes = senseBoxCollection()
            self._boxes.client = self
            self._boxes.boxes = new

    @simplegetter
    def token(self):
        return None

    @simplesetter(token)
    def token(self, new):
        if not new:
            self.token_time = None
        return new

    @simplegetter
    def refresh_token(self):
        return None

    @simplesetter(refresh_token)
    def refresh_token(self, new):
        if not new:
            self.refresh_token_time = None
        return new

    @simplegetter
    def token_time(self):
        return None

    @simplesetter(token_time)
    def token_time(self, new):
        return new

    @simplegetter
    def refresh_token_time(self):
        return None

    @simplesetter(refresh_token_time)
    def refresh_token_time(self, new):
        return new

    @property
    def authorization_header(self):
        """
        Authorization header

        :type: :any:`dict`
        :getter: Return a :mod:`requests`-compatible header-dict containing the
            authorization token. :any:`sign_in` if necessary.
        """
        if not self.token:
            self.sign_in()
        return {"Authorization": "Bearer {}".format(self.token)}

    @property
    def authenticache(self):
        """
        The authentication :any:`dict` to cache

        :type: :any:`dict`
        """
        authenticache = {}
        for attr in (
            "token",
            "refresh_token",
            "token_time",
            "refresh_token_time",
            "password",
            "username",
            "email",
            "api",
        ):
            value = getattr(self, attr)
            authenticache.update({attr: value})
        if not self.cache_password:
            authenticache["password"] = None
        elif not self.password:
            authenticache.pop("password", None)
        return authenticache

    @contextmanager
    def pause_caching(self):
        """
        Context manager for pausing the caching temporarily
        """
        auth_cache = self.auth_cache
        if self.auth_cache:
            logger.debug("Pausing the cache temporarily")
            self.auth_cache = None
        yield
        if self.auth_cache is not auth_cache:
            self.auth_cache = auth_cache

    def delete_cache(self):
        """
        Delete the cache for this account
        """
        login = {
            attr: getattr(self, attr)
            for attr in ("email", "username", "api")
            if getattr(self, attr)
        }
        full_cache = self.authenticache
        full_cache.update(login)
        if self.auth_cache:
            self.auth_cache.delete(full_cache)

    def sync_auth_cache(self):
        """
        Synchronize with the :any:`auth_cache`
        """
        if not self.auth_cache:
            return False
        login = {
            attr: getattr(self, attr)
            for attr in ("email", "username", "api")
            if getattr(self, attr)
        }
        matching = self.auth_cache.get(conditions=login)
        our_cache = self.authenticache
        our_cache.update(login)
        updated = self.auth_cache.sync(our_cache)
        for k, v in updated.items():
            val = getattr(self, k)
            if val != v:
                if k == "password" and not self.cache_password:
                    continue
                if not v and val:
                    logger.debug("Emptying the {} due to cache".format(k))
                setattr(self, k, v)

    def request(self, *args, **kwargs):
        """
        Wrapper around :any:`SenseMapClient.request` that handles some more
        corner cases

        Raises:
            OpenSenseMapAPIOutdatedTokenError : if the tokens are outdated
            OpenSenseMapAPIAuthenticationError : if access is prohibited
        """
        response = super().request(*args, **kwargs)
        # forbidden
        if response.status_code == 403:
            try:
                response_json = response.json()
            except compat.JSONDecodeError:  # pragma: no cover
                response_json = {}
            code = response_json.get("code", "")
            message = response_json.get("message", "")
            if re.search("invalid.+jwt", message.lower()) or re.search(
                r"refresh\s+token.+invalid.+too.+old", message.lower()
            ):
                raise OpenSenseMapAPIOutdatedTokenError(
                    (code + ": " if code else "" + message)
                )
            if re.search(r"user.+password.+not\s+valid", message.lower()):
                raise OpenSenseMapAPIInvalidCredentialsError(message)
            # something else went wrong
            raise OpenSenseMapAPIAuthenticationError(
                (code + ": " if code else "" + message)
            )  # pragma: no cover
        return response

    @sync_auth_cache_afterwards
    def sign_in(self):
        """
        Sign in with the user's credentials.

        Returns:
            True : if the login process was successful

        Raises:
            NoEmailError: if no email is set
            NoUserError: if no username is set
            NoPasswordError: if no password is set
            OpenSenseMapAPIInvalidCredentialsError : wrong credentials
            OpenSenseMapAPIAuthenticationError : if the login did not work
        """
        if self.email is None and self.username is None:
            raise NoUserError("Cannot sign_in: no username or email specified")
        if self.password is None:
            raise NoPasswordError("Cannot sign in: no user password specified")
        response = self.request(
            "post",
            urljoin(self.api, paths.SIGN_IN),
            json={
                "email": self.email or self.username,
                "password": self.password,
            },
        )
        response_json = response.json()
        try:
            message = response_json["message"]
            self.token = response_json["token"]
            self.token_time = datetime.datetime.utcnow()
            self.refresh_token = response_json["refreshToken"]
            self.refresh_token_time = datetime.datetime.utcnow()
            data = response_json["data"]
            user = data["user"]
        except KeyError as e:  # pragma: no cover
            raise OpenSenseMapAPIResponseError(
                "API response did not contain {}".format(e)
            )
        self.read_user_details(user)
        return True

    @sync_auth_cache_afterwards
    def sign_out(self):
        """
        Sign out the user

        Returns:
            True : if the logout process was successful

        Raises:
            OpenSenseMapAPIOutdatedTokenError : if the logout did not work
        """
        if self.token:
            response = self.request(
                "post",
                urljoin(self.api, paths.SIGN_OUT),
                headers=self.authorization_header,
            )
            response_json = response.json()
            try:
                code = response_json["code"]
                message = response_json["message"]
                if code != "Ok":  # pragma: no cover
                    raise OpenSenseMapAPIError(
                        "Logout did not work" + (": " + message or "")
                    )
            except KeyError as e:  # pragma: no cover
                raise OpenSenseMapAPIResponseError(
                    "API response did not contain {}".format(e)
                )
        self.token = None
        self.refresh_token = None
        self.token_time = datetime.datetime.now()
        self.refresh_token_time = datetime.datetime.utcnow()
        return True

    def refresh_tokens(self):
        """
        :any:`_refresh_tokens` and :any:`sign_in` again if necessary.

        Returns:
            True : if the refreshing was successful

        Raises:
            OpenSenseMapAPIAuthenticationError : if refreshing didn't work
        """
        try:
            self._refresh_tokens()
        except OpenSenseMapAPIOutdatedTokenError:
            logger.debug("Tokens are outdated. Signing in...")
            self.sign_in()
        return True

    @sync_auth_cache_afterwards
    def _refresh_tokens(self):
        """
        Attempt to refresh the tokens

        Returns:
            True : if the refreshing was successful

        Raises:
            OpenSenseMapAPIOutdatedTokenError : the refresh token is outdated
        """
        assert (
            self.refresh_token
        ), "No refresh token available. Please sign_in()"
        response = self.request(
            "post",
            urljoin(self.api, paths.REFRESH),
            headers=self.authorization_header,
            json={"token": self.refresh_token},
        )
        response_json = response.json()
        try:
            code = response_json["code"]
            message = response_json["message"]
            if code == "Forbidden":  # pragma: no cover
                if re.search("token.+invalid.+too.+old", message.lower()):
                    raise OpenSenseMapAPIOutdatedTokenError(
                        message + ". You should actually never see this."
                    )
            if code != "Authorized":  # pragma: no cover
                raise OpenSenseMapAPIError(
                    "Refreshing tokens did not work" + (": " + message or "")
                )
            self.token = response_json["token"]
            self.token_time = datetime.datetime.utcnow()
            self.refresh_token = response_json["refreshToken"]
            self.refresh_token_time = datetime.datetime.utcnow()
        except KeyError as e:  # pragma: no cover
            raise OpenSenseMapAPIResponseError(
                "API response did not contain {}".format(e)
            )
        return True

    def refresh_and_retry_on_outdated_tokens(decorated_function):
        """
        Decorator to call a decorated method, catching an
        :any:`OpenSenseMapAPIOutdatedTokenError`, then doing
        :any:`refresh_tokens` and then retries.
        """

        @functools.wraps(decorated_function)
        def wrapper(self, *args, **kwargs):
            try:
                return decorated_function(self, *args, **kwargs)
            except OpenSenseMapAPIOutdatedTokenError:
                logger.debug("Tokens are outdated. Refreshing tokens...")
                self.refresh_tokens()
            logger.debug(
                "Now trying again to call {}".format(decorated_function)
            )
            return decorated_function(self, *args, **kwargs)

        return wrapper

    def get_box(self, id):
        """
        Call :any:`SenseMapClient.get_box` and update own boxes if present

        Args:
            id (str) : the senseBox id to retreive

        Returns:
            senseBox : the retreived senseBox
        """
        box = super().get_box(id)
        logger.debug("Downloaded box '{}':\n{}".format(box.id, box))
        try:
            own_box = self.boxes.by_id[box.id]
            logger.debug(
                "We already have box '{}', updating it!".format(box.id)
            )
            own_box.update_from_api_json(box.to_api_json())
            for sensor, own_sensor in zip(box.sensors, own_box.sensors):
                own_sensor.update_from_json(sensor.to_json())
        except KeyError:  # pragma: no cover
            pass
        return box

    def get_own_boxes(self):
        """
        Run :any:`get_details` to fetch the current box ids and then
        call :any:`get_box` on all of them.

        Returns:
            senseBoxCollection : all own boxes
        """
        self.get_details()
        for box in self.boxes:
            self.get_box(box.id)
        return self.boxes

    @refresh_and_retry_on_outdated_tokens
    def get_details(self):
        """
        Get the user details

        Returns:
            True : if the retrieval was successful

        Raises:
            OpenSenseMapAPIError : if the retreival did not work
        """
        response = self.request(
            "get",
            urljoin(self.api, paths.USER_DETAILS),
            headers=self.authorization_header,
        )
        response_json = response.json()
        try:
            code = response_json["code"]
            message = response_json.get("message")
            if code != "Ok":  # pragma: no cover
                raise OpenSenseMapAPIError(
                    "Retrieving user details did not work"
                    + (": " + message or "")
                )
            data = response_json["data"]
        except KeyError as e:  # pragma: no cover
            raise OpenSenseMapAPIResponseError(
                "API response did not contain {}".format(e)
            )
        try:
            user = data["me"]
        except KeyError as e:  # pragma: no cover
            raise OpenSenseMapAPIResponseError(
                "API response data did not contain {}".format(e)
            )
        self.read_user_details(user)
        return True

    @refresh_and_retry_on_outdated_tokens
    def update_box_metadata(self, box):
        """
        Update metadata of a :class:`senseBox`

        Args:
            box (senseBox) : the box to update

        Returns:
            True : if the updating went well
        """
        box_json = box.to_api_json(with_id=True)
        logger.debug(
            "Uploading senseBox metadata:\n{}".format(pretty_json(box_json))
        )
        response = self.request(
            "put",
            urljoin(self.api, paths.BOXES, box.id),
            headers=self.authorization_header,
            json=box_json,
        )
        response_json = response.json()
        try:
            code = response_json["code"]
            message = response_json.get("message", "")
            if code != "Ok":
                raise OpenSenseMapAPIError(
                    "Could not update senseBox with id '{}'{}".format(
                        box.id, ": {}".format(message) if message else ""
                    )
                )
            data = response_json["data"]
        except KeyError as e:  # pragma: no cover
            raise OpenSenseMapAPIResponseError(
                "Response did not contain {}".format(e)
            )
        # only keep edited boxes, not deleted and new ones
        edited_boxes_ids = set(
            sensor_json.get("_id")
            for sensor_json in box_json.get("sensors", [])
            if (sensor_json.get("edited") and not sensor_json.get("new"))
        )
        box.sensors = [
            sensor for sensor in box.sensors if sensor.id in edited_boxes_ids
        ]
        # update the box data
        box.update_from_api_json(data)

    @refresh_and_retry_on_outdated_tokens
    def new_box(self, box):
        """
        Upload a new :class:`senseBox`

        Args:
            box (senseBox) : the box to upload

        Returns:
            senseBox : the responded new senseBox
        """
        assert box.exposure, "new box needs 'exposure'"
        assert box.current_lat, "new box needs 'current_lat'"
        assert box.current_lon, "new box needs 'current_lon'"
        assert box.name, "new box needs 'name'"
        assert box.sensors, "new box needs at least one sensor"
        box_json = box.to_api_json(with_id=False)
        logger.debug(
            "Uploading new senseBox:\n{}".format(pretty_json(box_json))
        )
        response = self.request(
            "post",
            urljoin(self.api, paths.BOXES),
            headers=self.authorization_header,
            json=box_json,
        )
        response_json = response.json()
        try:
            message = response_json.get("message", "")
            if "successfully" not in message:  # pragma: no cover
                raise OpenSenseMapAPIError(
                    "Could not post new senseBox{}".format(
                        ": {}".format(message) if message else ""
                    )
                )
            data = response_json["data"]
        except KeyError as e:  # pragma: no cover
            raise OpenSenseMapAPIResponseError(
                "Response did not contain {}".format(e)
            )
        data.update({"description": box.description, "image": box.image})
        box.update_from_api_json(data)
        box.client = self
        new_box = senseBox.from_api_json(data)
        logger.debug("new box:\n{}".format(new_box))
        self.get_details()
        return self.get_box(id=new_box.id)

    @refresh_and_retry_on_outdated_tokens
    def delete_box(self, box_id, really=False):
        """
        Mark a senseBox for deletion. This will also delete all the
        measurements. Deletion does not happen immediately. Also calls
        :any:`get_details`.

        Args:
            box_id (str) : the :any:`senseBox.id`
            really (bool, optional): really delete this box? Defaults to
                ``False``.

        Returns:
            True : if the marking for deletion went well
        """
        assert (
            really
        ), "Refusing to delete box '{}' without really=True".format(box_id)
        response = self.request(
            "delete",
            urljoin(self.api, paths.BOXES, box_id),
            headers=self.authorization_header,
            json={"password": self.password},
        )
        try:
            response_json = response.json()
            code = response_json.get("code", "")
            message = response_json.get("message", "")
            if re.search("user.+not.+own.+box", message.lower()):
                raise OpenSenseMapAPIPermissionError(
                    message or "User does not own box '{}'".format(box_id)
                )
            if (
                not response.status_code == requests.codes.OK
            ):  # pragma: no cover
                raise OpenSenseMapAPIError(
                    "Could not mark senseBox '{}' for deletion{}".format(
                        box_id, ": {}".format(message) if message else ""
                    )
                )
        except compat.JSONDecodeError:  # pragma: no cover
            raise OpenSenseMapAPIResponseError("Response is not JSON")
        except KeyError as e:  # pragma: no cover
            raise OpenSenseMapAPIResponseError(
                "Response did not contain {}".format(e)
            )
        self.get_details()
        return True

    @refresh_and_retry_on_outdated_tokens
    def upload_current_measurement(self, box, sensor):
        """
        Upload the current measurements of a given sensor of a given senseBox

        Args:
            box_id (str) : the :any:`senseBox.id`
            really (bool, optional): really delete this box? Defaults to
                ``False``.

        Returns:
            True : if the upload went well
        """
        assert box.id, "box has no 'id'"
        assert sensor.id, "sensor has no 'id'"
        response = self.request(
            "post",
            urljoin(self.api, paths.BOXES, box.id, sensor.id),
            headers=self.authorization_header,
            json={},
        )
        response_json = response.json()
        message = response_json.get("message", "")
        if re.search("user.+not.+own.+box", message.lower()):
            raise OpenSenseMapAPIPermissionError(
                message or "User does not own box '{}'".format(box_id)
            )
        if not response.status_code == requests.codes.OK:
            raise OpenSenseMapAPIError(
                "Could not mark senseBox '{}' for deletion{}".format(
                    box_id, ": {}".format(message) if message else ""
                )
            )
        self.get_details()
        return True

    def read_user_details(self, user_details, exception=OpenSenseMapAPIError):
        """
        Read user details into object properties

        Args:
            user_details (dict): the user details as returned by the API
            exception (Exception): the exception to raise if the data is
                ill-formed

        Returns:
            True : if everything is alright

        Raises:
            ``exception`` : if the data is ill-formed
        """
        try:
            username = user_details["name"]
            email = user_details["email"]
            if self.username != username:
                if self.username is not None:
                    logger.warning(
                        "The real username '{}' is different from "
                        "the configured username '{}'".format(
                            username, self.username
                        )
                    )
                self.username = username
            if self.email != email:
                if self.email is not None:
                    logger.warning(
                        "The real email '{}' is different from "
                        "the configured email '{}'".format(email, self.email)
                    )
                self.email = email
            if not user_details["emailIsConfirmed"]:
                logger.warning("The email '{}' is unconfirmed!".format(email))
            self.role = user_details["role"]
            self.language = user_details["language"]
            for own_box in self.boxes:
                if own_box.id not in user_details["boxes"]:
                    self.boxes.remove(own_box)
            for box_id in user_details["boxes"]:
                if box_id not in self.boxes.by_id:
                    box = senseBox(id=box_id)
                    self.boxes.append(box)
        except KeyError as e:  # pragma: no cover
            raise exception("user information did not contain {}".format(e))
        return True

    @refresh_and_retry_on_outdated_tokens
    def delete_sensor_measurements(
        self,
        box_id,
        sensor_id,
        timestamps=None,
        from_date=None,
        to_date=None,
        all=None,
        really=False,
    ):
        """
        Issue a request to delete measurements from a sensor

        Args:
            box_id (str): the senseBox id
            sensor_id (str): the sensor id
            to_date, from_date (datetime.datetime, optional): start and end
                dates to delete the data
            timestamps (list of datetime.datetime, optional): timestamps to
                delete
            all (bool, optional): delete all measurements?
            really (bool, optional): really delete the measurements?

        Returns:
            bool : whether the deletion worked
        """
        assert really, (
            "Refusing to delete measurements from sensor "
            "'{}' without really=True"
        ).format(sensor_id)
        d = {}
        if from_date is not None:
            d.update({"from-date": date2str(from_date)})
        if to_date is not None:
            d.update({"to-date": date2str(to_date)})
        if all is not None:
            d.update({"deleteAllMeasurements": bool(all)})
        if timestamps is not None:
            d.update({"timestamps": [date2str(x) for x in timestamps]})
        logger.debug("Request payload:\n{}".format(pretty_json(d)))
        response = self.request(
            "delete",
            urljoin(self.api, paths.BOXES, box_id, sensor_id, "measurements"),
            headers=self.authorization_header,
            json=d,
        )
        response_json = response.json()
        message = response_json.get("message", "")
        if not response.status_code == requests.codes.OK:  # pragma: no cover
            raise OpenSenseMapAPIError(
                "Could not delete measurements from sensor '{}'".format(box_id)
                + ": {}".format(message)
                if message
                else ""
            )
        return True

    def __del__(self):
        """
        Class deconstructor. Calls :any:`sign_out`.
        """
        if not self.auth_cache:
            try:
                self.sign_out()
            except (
                SenseMapiError,
                requests.exceptions.ConnectionError,
            ):  # pragma: no cover
                pass
        super().__del__()


class SenseMapAccountCollection(collections.abc.MutableSequence, ReprObject):
    """
    Container for multiple :any:`SenseMapAccount` s

    Args:
        accounts (sequence, optional): the :any:`SenseMapAccount` s
    """

    def __init__(self, accounts=[]):
        self.accounts = accounts

    @property
    def accounts(self):
        """
        The underlying :class:`SenseMapAccount` s

        :type: any:`list`
        :setter: also adds the :meth:`SenseMapCollection.client` to the
            given :class:`SenseMapAccount` s
        """
        try:
            self._accounts
        except AttributeError:
            self._accounts = []
        return self._accounts

    @accounts.setter
    def accounts(self, new_accounts):
        self._accounts = []
        for account in new_accounts:
            account.application = self.application
            self.append(account)

    @simplegetter
    def application(self):
        """
        The :class:`SenseMapApplication` these :class:`SenseMapAccount` s
        belong to.

        :type: :class:`SenseMapApplication` or :any:`None`
        :setter: sets the
        """
        return None

    @application.setter
    def application(self, new):
        for account in self:
            account.application = new
        self._application = new
        for account in self:
            account.application = self.application

    @property
    def by_username(self):
        """
        A :any:`dict` of these :any:`SenseMapAccount` s by their usernames.
        Accounts without a username get assigned to counter key ``account
        without username N``.
        Duplicate names get a ``" Nr. N"`` appended.

        :type: :any:`dict`
        """
        unnamed = itertools.count(0)
        d = {}
        duplicates = collections.Counter()
        for account in self:
            if account.username:
                if account.username in d:
                    duplicates[account.name] += 1
                    d[
                        "{} Nr. {}".format(
                            account.username, duplicates[account.username] + 1
                        )
                    ] = account
                else:
                    d[account.username] = account
            else:
                d[
                    "account without username {}".format(next(unnamed))
                ] = account
        return d

    def __getitem__(self, *args, **kwargs):
        return self.accounts.__getitem__(*args, **kwargs)

    def __setitem__(self, index, value):
        """
        Also adds the :any:`SenseMapAccountCollection.application` to the new
        account
        """
        value.application = self.application
        return self.accounts.__setitem__(index, value)

    def insert(self, index, value):
        """
        Also adds the :any:`SenseMapAccountCollection.application` to the new
        account
        """
        value.application = self.application
        return self.accounts.insert(index, value)

    def append(self, value):
        """
        Also adds the :any:`SenseMapAccountCollection.application` to the new
        account
        """
        value.application = self.application
        return self.accounts.append(value)

    def __delitem__(self, *args, **kwargs):
        return self.accounts.__delitem__(*args, **kwargs)

    def __len__(self, *args, **kwargs):
        return self.accounts.__len__(*args, **kwargs)

    def __eq__(self, other):
        return self.accounts == other.accounts

    def __getattr__(self, attr):
        """
        Retreives an account by looking its title up in
        :any:`SenseMapAccountCollection.by_username`.
        """
        try:
            return self.by_username[attr]
        except KeyError:
            raise AttributeError(
                "{} object does neither have an attribute '{}' "
                "nor an account with that title".format(
                    self.__class__.__name__, attr
                )
            )
