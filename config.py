import json

with open("credentials.json", "r") as f:
    creds = json.load(f)

QUERYSTRING = creds
EXEMPT = ["Epics"]