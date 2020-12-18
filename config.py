import json
from pathlib import Path

base_path = Path(__file__).parent

def get_credentials():
    base_path = Path(__file__).parent
    with open((base_path / "credentials.json"), "r") as f:
        creds = json.load(f)
    return creds

QUERYSTRING = get_credentials()
EXEMPT = ["Epics"]
TASK_FILE = (base_path / "tasks.json")