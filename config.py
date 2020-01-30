import json
from pathlib import Path
from helpers import get_credentials

base_path = Path(__file__).parent

QUERYSTRING = get_credentials()
EXEMPT = ["Epics"]
TASK_FILE = (base_path / "regular_tasks_test.json")