import datetime as dt
import json
import requests
from dateutil import tz
from collections import defaultdict

from config import EXEMPT

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

def title_case(string):
    first = string[0]
    rest = string[1:]
    title_str = f"{first.upper()}{rest}"
    return title_str

def format_desc(desc_dict):
    print(desc_dict)
    desc_struct = []
    for title, val in desc_dict.items():
        title = title_case(title.replace("_"," "))
        desc_struct.append(f"**{title}:** {val}")
    desc = "#Stats\n{}".format('\n'.join(desc_struct))
    return desc

class List:
    def __init__(self, list_input):
        self.board = list_input["board"]
        self.id = list_input["id"]
        self.name = list_input["name"]
        self.exempt = list_input["exempt"]
        self.get_list_cards()
        self.time_sum()

    def get_list_cards(self):
        self.cards = []
        url = f'https://api.trello.com/1/lists/{self.id}/cards'
        querystring = {"key": self.board.key, "token": self.board.token, "fields": ["id","name","desc","due"]}
        card_list = requests.get(url, params=querystring).json()
        for card_input in card_list:
            card_input["due"] = localize_ts(card_input["due"])
            card_input["list"] = self
            self.cards.append(Card(card_input))


    def sort_list(self):
        prefer_order = lambda x: (
            self.label_names[x["labels"][0]],
            x["due"],
            x["name"])
        self.cards = sorted(self.cards, key=prefer_order)

        for rank, card in enumerate(self.cards, start=1):
            url = f"https://api.trello.com/1/cards/{card['id']}"
            querystring = {"key": self.board.key, "token": self.board.token, "pos": rank}
            requests.put(url, querystring)

    def time_sum(self, breakout=False):
        self.sprint_time = 0
        for card in self.cards:
            self.sprint_time += card.stats["Time estimate"]
        if breakout:
            card_list = sorted(self.cards, key=lambda x: x.stats["Time estimate"], reverse=True)
            for sort_card in card_list:
                print(sort_card.name, sort_card.stats["Time estimate"])
    
    def _log_date(self):
        for card in self.cards:
            due_date = card.due.strftime("%Y-%m-%d")
            for i, task in enumerate(self.board.tasks):
                if card.name == task["name"]:
                    self.board.tasks[i]["date_info"]["last_complete"] = due_date

    def archive_cards(self):
        url = f"https://api.trello.com/1/lists/{self.list_id}/archiveAllCards"
        querystring = {
            "key": self.board.key,
            "token": self.board.token
        }
        requests.post(url, params=querystring)
        
        card_names = [card.name for card in self.cards]
        print(f"All cards archived in list {self.name}: {card_names}")
        self._log_date()
        #self.board.update_task_file()
        self.board.get_cards()

class Card:
    def __init__(self, card_input):
        for key, val in card_input.items():
            self.__setattr__(key, val)
        self._get_stats()

    def _get_stats(self):
        self.stats = {}
        stat_split = self.desc.split("#Stats\n")[1].replace("**","").split("\n")
        for stat in stat_split:
            key, val = stat.split(": ")
            val = int(val) if val.isnumeric() else val
            self.stats[key] = val

    def assign_list(self):
        now = localize_ts(dt.datetime.now())
        sunday = (now + dt.timedelta(6 - now.weekday() % 7)).replace(hour=23, minute=59, second=0)
        diff = int((self.due - now).total_seconds()//3600)

        hours_to_sunday = int((sunday - now).total_seconds()//3600)
        if hours_to_sunday < 28:
            hours_to_sunday += 168

        diff_map = RangeDict({
            range(0,29): "Today",
            range(29,hours_to_sunday+1): "This Week",
            range(hours_to_sunday,720): "This Month"
        })
        name = diff_map.get(diff, "Beyond")
        self.card_list = {"name": name, "id": self.list.board.lists[name]}
    
    def assign_due_date(self):
        if self.date_info["last_complete"]:
            base = dt.datetime.strptime(self.date_info["last_complete"], "%Y-%m-%d")
        else:
            base = dt.datetime.today()
        base = base.replace(hour=23,minute=59,second=0)
        raw_due_date = base + dt.timedelta(self.date_info["delta"])

        next_sunday = lambda x: x + dt.timedelta(6 - x.weekday() % 7)
        if date_info["advance"]:
            raw_due_date = next_sunday(raw_due_date)
        
        self.due = localize_ts(raw_due_date)

    def move_card(self):
        url = f"https://api.trello.com/1/cards/{card}"
        querystring = {
            "key": self.key,
            "token": self.token,
            "idList": new_list
        }
        requests.put(url, params=querystring)



    

class Board:
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

        self.lists = {}
        for list_input in lists_:
            list_input["board"] = self
            list_input["exempt"] = True if list_input["name"] in EXEMPT else False
            board_list = List(list_input)
            self.lists[board_list.name] = board_list
        print("Fetched lists")

    def assign_list(self, due_date):
        now = localize_ts(dt.datetime.now())
        sunday = (now + dt.timedelta(6 - now.weekday() % 7)).replace(hour=23, minute=59, second=0)
        diff = int((due_date - now).total_seconds()//3600)

        hours_to_sunday = int((sunday - now).total_seconds()//3600)
        if hours_to_sunday < 28:
            hours_to_sunday += 168

        diff_map = RangeDict({
            range(0,29): "Today",
            range(29,hours_to_sunday+1): "This Week",
            range(hours_to_sunday,720): "This Month"
        })
        card_list = diff_map.get(diff, "Beyond")
        return card_list
    
    def create_card(self, task):
        due_date = self.assign_due_date(task["date_info"])
        card_list = self.assign_list(due_date)
        list_id = self.lists[card_list]
        label_ids = [self.labels[label] for label in task["labels"]]
        card_name = task["name"]
        body = {
            "last_complete": task['date_info']['last_complete'],
            "time_estimate": task['time_estimate']
        }
        
        url = "https://api.trello.com/1/cards"
        querystring = {
            "idList": list_id,
            "name": card_name,
            "idLabels": label_ids,
            "due": due_date,
            "desc": format_desc(body),
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

        return localize_ts(due_date)

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
            self.label_names[x["labels"][0]],
            x["due"],
            x["name"])
        card_list = sorted(card_list, key=prefer_order)

        for rank, card in enumerate(card_list, start=1):
            url = f"https://api.trello.com/1/cards/{card['id']}"
            querystring = {"key": self.key, "token": self.token, "pos": rank}
            requests.put(url, querystring)

    def get_list_cards(self, list_id):
        url = f'https://api.trello.com/1/lists/{list_id}/cards'
        querystring = {"key": self.key, "token": self.token, "fields": ["id","name","desc"]}
        list_cards = requests.get(url, params=querystring).json()
        return list_cards

    def get_stats(self, card):
        stat_split = card["desc"].split("#Stats\n")[1].replace("**","").split("\n")
        for stat in stat_split:
            key, val = stat.split(": ")
            val = int(val) if val.isnumeric() else val
            card[key] = val
        return card

    def list_time_sum(self, list_id, breakout=False):
        card_list = self.get_list_cards(list_id)
        sprint_time = 0
        for card in card_list:
            card = self.get_stats(card)
            sprint_time += card["time estimate"]
        if breakout:
            card_list = sorted(card_list, key=lambda x: x["time estimate"], reverse=True)
            for card in card_list:
                print(card["name"], card["time estimate"])
        return sprint_time

    def rearrange_cards(self):
        self.get_cards()
        for card in self.cards:
            card_list = card["list"]
            new_list = self.lists[self.assign_list(card["due"])]
            if card_list != new_list and not card_list.exempt:
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
        est = int(input("Enter time estimate (in minutes): "))
        task = {
            "name": name,
            "labels": labels,
            "date_info": {
                "delta": delta,
                "advance": advance,
                "last_complete": None
            },
        "time_estimate": est
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


def main(board_name = "To Do List"):
    board = TrelloBoard(board_name)
    board.daily_update()
    
if __name__ == "__main__":
    main()