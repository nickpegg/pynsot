"""
Exceptions
"""

from pynsot.vendor.slumber.exceptions import HttpClientError, HttpServerError


class NsotHttpError(HttpClientError):
    """Raised when an HTTP error is encountered."""


class DoesNotExist(NsotHttpError):
    """Raised when an object cannot be found."""
