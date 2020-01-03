class SenseMapiError(Exception):
    """
    Base Exception class for package errors
    """


class NoCredentialsError(SenseMapiError):
    """
    Base SenseMapiError class raised whenever credentials are missing
    """


class NoUserError(NoCredentialsError):
    """
    SenseMapiError raised when no user/email is available
    """


class NoEmailError(NoUserError):
    """
    SenseMapiError raised when no email is available
    """


class NoUsernameError(NoUserError):
    """
    SenseMapiError raised when no user is available
    """


class NoPasswordError(NoCredentialsError):
    """
    SenseMapiError raised when no password is available
    """


class OpenSenseMapAPIError(SenseMapiError):
    """
    Base SenseMapiError class raised whenever something is strange
    """

    pass


class OpenSenseMapAPIResponseError(SenseMapiError):
    """
    SenseMapiError raised when the API responded something strange
    """

    pass


class OpenSenseMapAPIAuthenticationError(OpenSenseMapAPIError):
    """
    SenseMapiError raised when the authentication failed
    """

    pass


class OpenSenseMapAPIInvalidCredentialsError(
    OpenSenseMapAPIAuthenticationError
):
    """
    SenseMapiError raised when the login failed due to invalid credentials
    """

    pass


class OpenSenseMapAPIOutdatedTokenError(OpenSenseMapAPIAuthenticationError):
    """
    SenseMapiError raised when a token is outdated
    """

    pass


class OpenSenseMapAPITooManyRequestsError(OpenSenseMapAPIError):
    """
    SenseMapiError raised when a client issues too many requests
    """

    pass


class OpenSenseMapAPIPermissionError(OpenSenseMapAPIAuthenticationError):
    """
    SenseMapiError raised when the account does not have certain permissions
    """

    pass


class NoClientError(SenseMapiError):
    pass


class ConfirmationError(SenseMapiError):
    pass


class NoPandasError(ImportError):
    """
    SenseMapiError raised when no :mod:`pandas` was found
    """

    def __init__(self, message=""):
        super().__init__(message or "pandas is not installed")


class NoCacheControl(ImportError):
    """
    SenseMapiError raised when no :mod:`cachecontrol` was found
    """

    def __init__(self, message=""):
        super().__init__(message or "cachecontrol is not installed")
