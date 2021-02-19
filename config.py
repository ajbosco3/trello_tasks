import json
from pathlib import Path

base_path = Path(__file__).parent

def get_credentials():
    base_path = Path(__file__).parent
    with open((base_path / "credentials.json"), "r") as f:
        creds = json.load(f)
    return creds

QUERYSTRING = get_credentials()
EXEMPT = ["Projects"]
TASK_FILE = (base_path / "tasks.json")
LABEL_PRIORITY = {
    "Critical": 1,
    "This Week": 2,
    "Maybe": 3,
    "Desk": 4,
    "Later": 5,
    "Project": 6
}
SORT_ORDER = lambda x: (
    x.priority[1],
    x.priority[0],
    x.pos
)