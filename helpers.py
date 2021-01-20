import datetime as dt
from pathlib import Path
import json

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

def snake_case(string):
    lower = string.lower()
    snake = lower.replace(" ", "_")
    return snake

def localize_ts(timestamp):
    if timestamp:
        utc = tz.tzutc()
        ct = tz.gettz('America/Chicago')
        if type(timestamp) != dt.datetime:
            timestamp = dt.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=utc)
        timestamp = timestamp.astimezone(ct)
        return timestamp

def format_desc(desc_dict):
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
    else:
        return r

def format_tasks(tasks):
    task_output = []
    for _, task in tasks.items():
        task_dict = task.__dict__.copy()
        for key in task.__dict__:
            if key.startswith("_"):
                del task_dict[key]
        task_output.append(task_dict)
    return task_output

def date_handler(record_val):
    if isinstance(record_val, (dt.date, dt.datetime)):
        return record_val.__str__()

def make_hyperlink(name, link):
    hyperlink = f"[{name}]({link})"
    return hyperlink

def hyperlink_split(hyperlink):
    if hyperlink.startswith("["):
        name_raw, link_raw = hyperlink.split("](")
        name = name_raw.replace("[", "")
        link = link_raw.replace(")", "")
    else:
        name = hyperlink
        link = ''
    return name, link