import datetime as dt
import json
import requests
from dateutil import tz

class RangeDict(dict):
    def get(self, item, default=None):
        for key in self:
            if item in key:
                return self[key]
        return default

def localize_ts(timestamp):
    utc = tz.tzutc()
    ct = tz.gettz('America/Chicago')
    timestamp = dt.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=utc)
    timestamp = timestamp.astimezone(ct)
    return timestamp

class TrelloBoard:
    def __init__(self, board_name):
        self.get_credentials()
        self.board_id = self.get_board_id(board_name)
        self.cards = self.get_cards()
        self.labels = self.get_labels()
        self.lists = self.get_lists()
        self.tasks = self.import_tasks()

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
        return board_id
        
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
                "due": localize_ts(card["due"])
            }
            for card in cards]
        print("Fetched cards")
        return names

    def get_labels(self):
        url = f"https://api.trello.com/1/boards/{self.board_id}/labels/"
        querystring = {
            "key": self.key,
            "token": self.token
        }
        r = requests.get(url, params=querystring)
        labels = r.json()
        label_map = {label["name"]: label["id"] for label in labels}
        print("Fetched labels")
        return label_map

    def get_lists(self):
        url = f"https://api.trello.com/1/boards/{self.board_id}/lists/"
        querystring = {
            "key": self.key,
            "token": self.token
        }
        r = requests.get(url, params=querystring)
        lists_ = r.json()
        lists = {list_["name"]: list_["id"] for list_ in lists_}
        print("Fetched lists")
        return lists

    def assign_list(self, due_date):
        today = dt.datetime.today()
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
        card_list = self.assign_list(due_date)
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
        with open("regular_tasks_test.json", "r") as f:
            tasks = json.load(f)
        return tasks

    def post_tasks(self):
        for task in self.tasks:
            card_names = [card["name"] for card in self.cards]
            if task["name"] not in card_names:
                self.create_card(task)
            else:
                print(f"Card skipped: {task['name']}")

    def update_task_file(self):
        with open("regular_tasks_test.json", "w") as f:
            json.dump(self.tasks, f)

    def log_date(self, list_cards):
        for card in list_cards:
            due_date = card["due"].strftime("%Y-%m-%d")
            for i, task in enumerate(self.tasks):
                if card == task["name"]:
                    self.tasks[i]["date_info"]["last_complete"] = due_date

    def archive_cards(self, list_name="Done"):
        list_id = self.lists[list_name]
        list_cards = []
        for i, card in list(enumerate(self.cards))[::-1]:
            if card["list"] == list_id:
                list_cards.append(card)
                del self.cards[i]
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

def main(board_name = "To Do Test"):
    board = TrelloBoard(board_name)
    board.archive_cards()
    board.post_tasks()
    
if __name__ == "__main__":
    main()