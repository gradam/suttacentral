import babel.dates
import os
import time

import config

def format_date(value, format='short', locale=config.default_locale):
    return babel.dates.format_date(value, format=format, locale=locale)

def format_datetime(value, format='short', locale=config.default_locale):
    rfc3339 = format == 'rfc3339'
    if rfc3339:
        format = 'yyyy-MM-ddTHH:mm:ssZ'
    datetime = babel.dates.format_datetime(value, format=format, locale=locale)
    if rfc3339:
        datetime = datetime[:-2] + ':' + datetime[-2:]
    return datetime

def format_time(value, format='short', locale=config.default_locale):
    return babel.dates.format_time(value, format=format, locale=locale)

def set_timezone(tz=None):
    if not tz:
        tz = config.timezone
    os.environ['TZ'] = tz
    time.tzset()