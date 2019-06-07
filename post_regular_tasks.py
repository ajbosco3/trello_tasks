import datetime as dt
import json
import requests
from dateutil import tz
from collections import defaultdict

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

class TrelloBoard:
    def __init__(self, board_name):
        self.get_credentials()
        self.get_board_id(board_name)
        self.get_cards()
        self.get_labels()
        self.get_lists()
        self.import_tasks()

    def daily_update(self):
        self.archive_cards()
        self.post_tasks()
        self.update_today()
        self.rearrange_cards()
        self.sort_all_lists()

    def get_credentials(self):
        with open("credentials.json", "r") as f:
            creds = json.load(f)
        self.key = creds["key"]
        self.token = creds["token"]

    def get_board_id(self, board_name):
        url = "https://api.trello.com/1/members/me/boards"
        querystring = {
            "key": self.key,
            "token": self.token
        }
        r = requests.get(url, params=querystring)
        boards = r.json()
        board_id = [board["id"] for board in boards if board["name"] == board_name][0]
        self.board_id = board_id
        
    def get_cards(self):
        url = f"https://api.trello.com/1/boards/{self.board_id}/cards/"
        querystring = {
            "key": self.key,
            "token": self.token,
            "visible": "true"
        }
        r = requests.get(url, params=querystring)
        cards = r.json()
        
        names = [
            {
                "name": card["name"],
                "id": card["id"],
                "list": card["idList"],
                "labels": card["idLabels"],
                "due": localize_ts(card["due"]),
            }
            for card in cards]
        self.cards = names
        print("Fetched cards")

    def get_labels(self):
        url = f"https://api.trello.com/1/boards/{self.board_id}/labels/"
        querystring = {
            "key": self.key,
            "token": self.token
        }
        r = requests.get(url, params=querystring)
        labels = r.json()
        label_map = {label["name"]: label["id"] for label in labels}
        self.labels = label_map
        self.label_names = {id: name for name, id in self.labels.items()}
        print("Fetched labels")

    def get_lists(self):
        url = f"https://api.trello.com/1/boards/{self.board_id}/lists/"
        querystring = {
            "key": self.key,
            "token": self.token
        }
        r = requests.get(url, params=querystring)
        lists_ = r.json()
        lists = {list_["name"]: list_["id"] for list_ in lists_}
        self.lists = lists
        print("Fetched lists")

    def assign_list(self, due_date):
        today = localize_ts(dt.datetime.today())
        diff = (due_date - today).days
        diff_map = RangeDict({
            range(0,2): "Today",
            range(2,8): "This Week",
            range(8,30): "This Month"
        })
        card_list = diff_map.get(diff, "Beyond")
        return card_list
    
    def create_card(self, task):
        due_date = self.assign_due_date(task["date_info"])
        card_list = self.assign_list(localize_ts(due_date))
        list_id = self.lists[card_list]
        label_ids = [self.labels[label] for label in task["labels"]]
        card_name = task["name"]
        
        url = "https://api.trello.com/1/cards"
        querystring = {
            "idList": list_id,
            "name": card_name,
            "idLabels": label_ids,
            "due": due_date,
            "key": self.key,
            "token": self.token
        }
        requests.post(url, params=querystring)
        print(f"Posted card: {card_name} to list {card_list} (due {due_date.date()})")

    def assign_due_date(self, date_info):
        if date_info["last_complete"]:
            base = dt.datetime.strptime(date_info["last_complete"], "%Y-%m-%d")
        else:
            base = dt.datetime.today()
        base = base.replace(hour=23,minute=59,second=0)
        due_date = base + dt.timedelta(date_info["delta"])

        next_sunday = lambda x: x + dt.timedelta(6 - x.weekday() % 7)
        if date_info["advance"]:
            due_date = next_sunday(due_date)

        return due_date

    def import_tasks(self):
        with open("regular_tasks.json", "r") as f:
            self.tasks = json.load(f)
        self.task_names = [task["name"] for task in self.tasks]

    def post_tasks(self):
        for task in self.tasks:
            card_names = [card["name"] for card in self.cards]
            if task["name"] not in card_names:
                self.create_card(task)
            else:
                print(f"Card skipped: {task['name']}")

    def update_task_file(self):
        with open("regular_tasks.json", "w") as f:
            json.dump(self.tasks, f)

    def log_date(self, list_cards):
        for card in list_cards:
            due_date = card["due"].strftime("%Y-%m-%d")
            for i, task in enumerate(self.tasks):
                if card["name"] == task["name"]:
                    self.tasks[i]["date_info"]["last_complete"] = due_date

    def archive_cards(self, list_name="Done"):
        list_id = self.lists[list_name]
        list_cards = [card for card in self.cards if card["list"] == list_id]
        
        url = f"https://api.trello.com/1/lists/{list_id}/archiveAllCards"
        querystring = {
            "key": self.key,
            "token": self.token
        }
        requests.post(url, params=querystring)
        
        card_names = [card["name"] for card in list_cards]
        print(f"All cards archived in list {list_name}: {card_names}")
        self.log_date(list_cards)
        self.update_task_file()
        self.get_cards()

    def sort_list(self, card_list):
        prefer_order = lambda x: (
            not x["name"] == "Groceries",
            x["name"] in self.task_names,
            x["due"],
            self.label_names[x["labels"][0]],
            x["name"])
        card_list = sorted(card_list, key=prefer_order)

        for rank, card in enumerate(card_list, start=1):
            url = f"https://api.trello.com/1/cards/{card['id']}"
            querystring = {"key": self.key, "token": self.token, "pos": rank}
            requests.put(url, querystring)

    def rearrange_cards(self):
        self.get_cards()
        for card in self.cards:
            card_list = card["list"]
            new_list = self.lists[self.assign_list(card["due"])]
            if card_list != new_list:
                self.move_card(card["id"], new_list)
                print(f"Moved card {card['name']} to {new_list} (due {card['due']})")

    def move_card(self, card, new_list):
        url = f"https://api.trello.com/1/cards/{card}"
        querystring = {
            "key": self.key,
            "token": self.token,
            "idList": new_list
        }
        requests.put(url, params=querystring)


    def sort_all_lists(self):
        self.get_cards()
        groups = defaultdict(list)
        for card in self.cards:
            groups[card["list"]].append(card)
        for card_list in groups.values():
            self.sort_list(card_list)

    def add_task(self):
        name = input("Enter task name: ")
        labels = input("Enter label names, separated by comma: ").split(",")
        delta = int(input("Enter task frequency: "))
        advance = True if input("Date flexible? (Y/N): ").upper() == "Y" else False
        task = {
            "name": name,
            "labels": labels,
            "date_info": {
                "delta": delta,
                "advance": advance,
                "last_complete": None
            }
        }
        self.tasks.append(task)
        self.update_task_file()

    def update_today(self):
        self.get_cards()
        today_list = self.lists["Today"]
        today_cards = [card["id"] for card in self.cards if card["list"] == today_list]
        today = dt.datetime.today().replace(hour=23,minute=59,second=0)
        for card in today_cards:
            url = f"https://api.trello.com/1/cards/{card}"
            querystring = {
                "key": self.key,
                "token": self.token,
                "due": localize_ts(today)
            }
            requests.put(url, params=querystring)


def main(board_name = "To Do Test"):
    board = TrelloBoard(board_name)
    board.archive_cards()
    board.post_tasks()
    board.sort_all_lists()
    
if __name__ == "__main__":
    main()