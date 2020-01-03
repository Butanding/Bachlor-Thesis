# external modules
import requests
from requests.compat import json as requestsjson

try:  # requestsjson
    JSONDecodeError = requestsjson.JSONDecodeError
except AttributeError:  # normal json
    try:  # newer Python
        JSONDecodeError = requestsjson.errors.JSONDecodeError
    except AttributeError:  # older Python (3.4)
        JSONDecodeError = ValueError
