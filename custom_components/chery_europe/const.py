"""Constants for the Chery Europe integration."""

from datetime import timedelta

# Base component constants
NAME = "Chery Europe"
DOMAIN = "chery_europe"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.2.3"
ISSUE_URL = "https://github.com/Przemko92/chery-ha-integration/issues"

# Platforms
SENSOR = "sensor"
BINARY_SENSOR = "binary_sensor"
SWITCH = "switch"
LOCK = "lock"
CLIMATE = "climate"
TIME = "time"
NUMBER = "number"
COVER = "cover"
DEVICE_TRACKER = "device_tracker"
BUTTON = "button"
PLATFORMS = [
    SENSOR,
    BINARY_SENSOR,
    SWITCH,
    LOCK,
    CLIMATE,
    TIME,
    NUMBER,
    COVER,
    DEVICE_TRACKER,
    BUTTON,
]

# Services
SERVICE_SEND_COMMAND = "send_command"
SERVICE_SET_SCHEDULED_CHARGING = "set_scheduled_charging"
ATTR_VIN = "vin"
ATTR_COMMAND_ID = "command_id"
ATTR_PIN = "pin"
ATTR_START_TIME = "start_time"
ATTR_DURATION_HOURS = "duration_hours"
ATTR_ENABLED = "enabled"

# Configuration and options
CONF_LOGIN = "login"
CONF_CODE = "code"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_EXPIRES_IN = "expires_in"
CONF_TOKEN_OBTAINED_AT = "token_obtained_at"
CONF_BASE_URL = "base_url"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_DEVICE_ID = "device_id"
CONF_PIN = "pin"
CONF_PIN_CONFIRM = "pin_confirm"
CONF_ASK_FOR_PIN = "ask_for_pin"
CONF_POLL_NORMAL = "poll_normal_min"
CONF_POLL_CHARGING = "poll_charging_min"
CONF_POLL_HV = "poll_hv_min"
# SMS login (optional alternative to email). When phone is set, OTP uses sendSmsCode
# and the OAuth grant is grant_type=mobile (same legend BFF pattern as Omoda).
CONF_PHONE = "phone"
CONF_AREA_CODE = "area_code"
CONF_LOGIN_METHOD = "login_method"
LOGIN_METHOD_EMAIL = "email"
LOGIN_METHOD_SMS = "sms"
DEFAULT_AREA_CODE = "48"

DEFAULT_POLL_NORMAL_MIN = 15
DEFAULT_POLL_CHARGING_MIN = 2
DEFAULT_POLL_HV_MIN = 1
REFRESH_HV_WAIT_SECONDS = 25
# Seconds to wait between post-command polls. First delay is 5s so optimistic
# entity state (locks, covers, climate) is not overwritten by stale telemetry.
POST_COMMAND_REFRESH_DELAYS = (5, 10, 20)
STATUS_MAX_LEN = 255

# Login identity prefix used by the legend BFF email/SMS OTP grant.
LOGIN_MODULE = "APP-LOGIN"
LOGIN_EMAIL_PREFIX = f"{LOGIN_MODULE}@"
LOGIN_MOBILE_PREFIX = f"{LOGIN_MODULE}@"

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
# sendSmsCode sits behind Aliyun WAF (TLS fingerprint filter); see tls_client.py.
DEFAULT_SEND_SMS_CODE_ENDPOINT = "/api/marketing/v2/app/code/sendSmsCode"
DEFAULT_CHANNEL_ID = 5
API_TSP_LOGIN_PATH = "/api/tsp/v1/app/auth/login"
API_VMC_QUERY_LIST_PATH = "/api/tsp/v1/app/vmc/queryList"
API_VMC_SET_VEC_DEFAULT_PATH = "/api/tsp/v1/app/vmc/setVecDefault"
API_VMC_QUERY_AUTHORITY_PATH = "/api/tsp/v1/app/vmc/queryVehicleAuthority"
API_CPM_CHECK_PASSWORD_PATH = "/api/tsp/v1/app/cpm/checkPassword"
API_VAC_ADD_PATH = "/api/tsp/v1/app/vac/add"
DEFAULT_TSP_HOST = "https://tspconsole-eu.cheryinternational.com"
API_REALTIME_PATH = "/asr/manager/realtime"
API_QUERY_LOCATION_PATH = "/asc/vehicleControl/queryVehicleLocation"
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
HV_POLL_INTERVAL = timedelta(seconds=60)
CHARGING_POLL_INTERVAL = timedelta(seconds=120)
DRIVE_WATCH_INTERVAL = timedelta(seconds=180)
# Session keep-alive: Chery access tokens last ~12h (expires_in=43200) and the
# refresh_token rotates on every use. Periodic proactive refresh keeps the
# session alive across HA reloads without forcing a new OTP.
DEFAULT_SESSION_KEEPALIVE = timedelta(seconds=900)
TOKEN_REFRESH_QUOTA = 0.8
DEFAULT_TOKEN_EXPIRES_IN = 43200
DEFAULT_MQTT_HOST = "tspemqx-app-eu.cheryinternational.com"
DEFAULT_MQTT_PORT = 8083
MQTT_PASSWORD_SEED = "fa89db3abe8045919d70c6ed3cc65bc5"

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
