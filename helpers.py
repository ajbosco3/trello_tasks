from dateutil import tz
import requests
import config

class RangeDict(dict):
    def get(self, item, default=None):
        for key in self:
            if item in key:
                return self[key]
        return default

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
        title = title_case(title.replace("_"," "))
        desc_struct.append(f"**{title}:** {val}")
    desc = "#Stats\n{}".format('\n'.join(desc_struct))
    return desc