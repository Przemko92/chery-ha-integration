"""Constants for the Chery Europe integration."""

from datetime import timedelta

# Base component constants
NAME = "Chery Europe"
DOMAIN = "chery_europe"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.2.0"
ISSUE_URL = "https://github.com/Przemko92/home-assistant-chery-europe/issues"

# Platforms
SENSOR = "sensor"
BINARY_SENSOR = "binary_sensor"
SWITCH = "switch"
LOCK = "lock"
CLIMATE = "climate"
TIME = "time"
NUMBER = "number"
PLATFORMS = [SENSOR, BINARY_SENSOR, SWITCH, LOCK, CLIMATE, TIME, NUMBER]

# Services
SERVICE_SEND_COMMAND = "send_command"
ATTR_VIN = "vin"
ATTR_COMMAND_ID = "command_id"
ATTR_PIN = "pin"

# Configuration and options
CONF_LOGIN = "login"
CONF_CODE = "code"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_BASE_URL = "base_url"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_DEVICE_ID = "device_id"
CONF_PIN = "pin"

# Login identity prefix used by the legend BFF email OTP grant.
LOGIN_MODULE = "APP-LOGIN"
LOGIN_EMAIL_PREFIX = f"{LOGIN_MODULE}@"

# Identity header constants (from chery.txt app capture)
HEADER_AGENT = "android"
HEADER_VERSION = "1.0.6"
HEADER_DEPT_ID = "48"
HEADER_TENANT_ID = "300001"
HEADER_TENANT_CODE = "300001"
HEADER_CLIENT_TOC = "Y"
HEADER_CONTENT_TYPE = "application/json; charset=UTF-8"
HEADER_FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"
HEADER_NONCE = "chery_legend_h5"

# OAuth2 request headers (from the real app capture).
HEADER_ACCEPT = "application/json, text/plain, */*"
HEADER_ACCEPT_LANGUAGE = "pl-PL"
HEADER_ACCEPT_ENCODING = "gzip, deflate"

# OAuth2 Basic auth credential for the "legend" BFF (base64 of "legendApp:legendApp").
# Used for the /api/auth/oauth2/token form-urlencoded login and refresh requests.
HEADER_BASIC_AUTH = "Basic bGVnZW5kQXBwOmxlZ2VuZEFwcA=="

DEFAULT_BASE_URL = "https://eu-chery.cheryinternational.com"
DEFAULT_LOGIN_ENDPOINT = "/api/auth/oauth2/token"
# v3 (used by the mobile app) expects Aliyun captchaVerification tokens.
# v2 accepts AJ-Captcha tokens from ``/api/code/create`` (same as Omoda).
DEFAULT_SEND_MAIL_CODE_ENDPOINT = "/api/marketing/v2/app/code/sendMailCode"
DEFAULT_CHANNEL_ID = 5
API_TSP_LOGIN_PATH = "/api/tsp/v1/app/auth/login"
API_VMC_QUERY_LIST_PATH = "/api/tsp/v1/app/vmc/queryList"
API_VMC_SET_VEC_DEFAULT_PATH = "/api/tsp/v1/app/vmc/setVecDefault"
API_CPM_CHECK_PASSWORD_PATH = "/api/tsp/v1/app/cpm/checkPassword"
API_VAC_ADD_PATH = "/api/tsp/v1/app/vac/add"
DEFAULT_TSP_HOST = "https://tspconsole-eu.cheryinternational.com"
API_REALTIME_PATH = "/asr/manager/realtime"
TSP_CODE_OK = "000000"
TSP_CODE_ASLEEP = "A07900"
DEFAULT_USER_AGENT = "CheryEurope/1.0.4 Flutter/Dio"

# Bootstrap endpoint discovered from the decompiled app. The app calls this
# unauthenticated endpoint first to learn the active TSP domain, OAuth client
# credentials, tenant and channel before any login/API request.
DEFAULT_ENV_URL = (
    "https://eu-chery.cheryinternational.com/api/tsp/v1/app/env/defaultEnv"
)

# Defaults
DEFAULT_SCAN_INTERVAL = timedelta(minutes=15)

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
