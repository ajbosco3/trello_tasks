import datetime as dt

import requests
from dateutil import tz

from config import QUERYSTRING


class RangeDict(dict):
    def get(self, item, default=None):
        for key in self:
            if item in key:
                return self[key]
        return default

def sentence_case(string):
    first = string[0]
    rest = string[1:]
    title_str = f"{first.upper()}{rest}"
    return title_str

def localize_ts(timestamp):
    if timestamp:
        utc = tz.tzutc()
        ct = tz.gettz('America/Chicago')
        if type(timestamp) != dt.datetime:
            timestamp = dt.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=utc)
        timestamp = timestamp.astimezone(ct)
        return timestamp

def format_desc(desc_dict):
    print(desc_dict)
    desc_struct = []
    for title, val in desc_dict.items():
        title = sentence_case(title.replace("_"," "))
        desc_struct.append(f"**{title}:** {val}")
    desc = "#Stats\n{}".format('\n'.join(desc_struct))
    return desc

def request(r_type, url, **kwargs):
    querystring = QUERYSTRING.copy()
    r_type = r_type.upper()

    for key, val in kwargs.items():
        querystring[key] = val
    r = requests.request(r_type, url, params=querystring)
    if r_type == "GET":
        return r.json()
