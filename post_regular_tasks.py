import datetime as dt
import json
from collections import defaultdict

import requests

import helpers as hlp
from config import EXEMPT, TASK_FILE
from helpers import RangeDict

class Board:
    def __init__(self, board_name):
        self.get_board_id(board_name)
        self.get_labels()
        self.get_lists()
        self.get_cards()
        self.import_tasks()

    def daily_update(self):
        self.archive_cards()
        self.post_tasks()
        self.update_today()
        self.rearrange_cards()
        self.sort_all_lists()

    def get_board_id(self, board_name):
        url = "https://api.trello.com/1/members/me/boards"
        boards = hlp.request("GET", url)
        board_id = [board["id"] for board in boards if board["name"] == board_name][0]
        self.board_id = board_id
        
    def get_cards(self):
        self.card_names = []
        for list_ in self.lists.values():
            for card in list_.cards:
                self.card_names.append(card.name)

    def get_labels(self):
        url = f"https://api.trello.com/1/boards/{self.board_id}/labels/"
        labels = hlp.request("GET", url)
        label_map = {label["name"]: label["id"] for label in labels}
        self.labels = label_map
        self.label_names = {id: name for name, id in self.labels.items()}
        print("Fetched labels")

    def get_lists(self):
        url = f"https://api.trello.com/1/boards/{self.board_id}/lists/"
        lists_ = hlp.request("GET", url)

        self.lists = {}
        for list_input in lists_:
            list_input["board"] = self
            list_input["exempt"] = True if list_input["name"] in EXEMPT else False
            board_list = List(list_input)
            self.lists[board_list.name] = board_list
        print("Fetched lists and cards.")

    def import_tasks(self):
        with open(TASK_FILE, "r") as f:
            tasks = json.load(f)
        self.tasks = [Task(self, task) for task in tasks]
        self.task_names = [task.name for task in self.tasks]

    def post_tasks(self):
        for task in self.tasks:
            if task.name not in self.card_names:
                task.create_card()
            else:
                print(f"Card skipped: {task.name}")

    def update_task_file(self):
        task_output = hlp.format_tasks(self.tasks)
        print(task_output)
        with open(TASK_FILE, "w") as f:
            json.dump(task_output, f, default=hlp.date_handler)

    def archive_cards(self, list_name="Done"):
        card_list = self.lists[list_name]
        card_list.archive_cards()

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
        task_input = {
            "name": name,
            "labels": labels,
            "date_info": {
                "delta": delta,
                "advance": advance,
                "last_complete": None
            },
        "time_estimate": est
        }
        task = Task(self, task_input)
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
                "due": hlp.localize_ts(today)
            }
            requests.put(url, params=querystring)


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
        fields = ["id","name","desc","due","labels"]
        card_list = hlp.request("GET", url, fields=fields)
        for card_input in card_list:
            card_input["due"] = hlp.localize_ts(card_input["due"])
            card_input["list"] = self
            self.cards.append(Card(card_input))


    def sort_list(self):
        prefer_order = lambda x: (
            self.board.label_names[x["labels"][0]],
            x["due"],
            x["name"])
        self.cards = sorted(self.cards, key=prefer_order)

        for rank, card in enumerate(self.cards, start=1):
            url = f"https://api.trello.com/1/cards/{card['id']}"
            hlp.request("PUT", url, pos=rank)

    def time_sum(self, breakout=False):
        self.sprint_time = 0
        for card in self.cards:
            time_est = card.stats.get("Time estimate",0)
            self.sprint_time += time_est
        if breakout:
            card_list = sorted(self.cards, key=lambda x: x.stats["Time estimate"], reverse=True)
            for sort_card in card_list:
                time_est = sort_card.stats.get("Time estimate",0)
                print(sort_card.name, time_est)
    
    def _log_date(self):
        for card in self.cards:
            due_date = card.due.strftime("%Y-%m-%d")
            for i, task in enumerate(self.board.tasks):
                if card.name == task.name:
                    self.board.tasks[i].date_info["last_complete"] = due_date

    def archive_cards(self):
        url = f"https://api.trello.com/1/lists/{self.id}/archiveAllCards"
        hlp.request("POST", url)
        
        card_names = [card.name for card in self.cards]
        print(f"All cards archived in list {self.name}: {card_names}")
        self._log_date()
        self.board.update_task_file()
        self.cards = []
        self.board.get_cards()

class Card:
    def __init__(self, card_input):
        for key, val in card_input.items():
            self.__setattr__(key, val)
        self._get_stats()

    def _get_stats(self):
        self.stats = {}
        if self.desc != '':
            stat_split = self.desc.split("#Stats\n")[1].replace("**","").split("\n")
            for stat in stat_split:
                key, val = stat.split(": ")
                val = int(val) if val.isnumeric() else val
                self.stats[key] = val

    def move_card(self, new_list_):
        url = f"https://api.trello.com/1/cards/{self.id}"
        new_list = self.list.board.lists[new_list_]
        r = hlp.request("PUT", url, idList=new_list.id)
        if r.status_code == 200:
            self.list = new_list


class Task:
    def __init__(self, board, task):
        self._board = board
        self.name = task["name"]
        self.labels = task["labels"]
        self._label_ids = [self._board.labels[label] for label in self.labels]
        self.date_info = task["date_info"]
        self.time_estimate = task["time_estimate"]

    def assign_due_date(self):
        if self.date_info["last_complete"]:
            base = dt.datetime.strptime(self.date_info["last_complete"], "%Y-%m-%d")
        else:
            base = dt.datetime.today()
        base = base.replace(hour=23,minute=59,second=0)
        raw_due_date = base + dt.timedelta(self.date_info["delta"])

        next_sunday = lambda x: x + dt.timedelta(6 - x.weekday() % 7)
        if self.date_info["advance"]:
            raw_due_date = next_sunday(raw_due_date)
        
        self.due = hlp.localize_ts(raw_due_date)

    def assign_list(self):
        now = hlp.localize_ts(dt.datetime.now())
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
        self.card_list = self._board.lists[name]

    def create_card_body(self):
        self.card_body = {
            "last_complete": self.date_info["last_complete"],
            "time_estimate": self.time_estimate
        }
        
    
    def create_card(self):
        self.assign_due_date()
        self.assign_list()
        self.create_card_body()

        url = "https://api.trello.com/1/cards"
        params = {
            "idList": self.card_list.id,
            "name": self.name,
            "idLabels": self._label_ids,
            "due": self.due,
            "desc": hlp.format_desc(self.card_body)
        }
        r = hlp.request("POST", url, **params)        
        print(f"Posted card: {self.name} to list {self.card_list.name} (due {self.due.date()})")
        

def main(board_name = "To Do List"):
    board = Board(board_name)
    board.daily_update()
    
if __name__ == "__main__":
    main()