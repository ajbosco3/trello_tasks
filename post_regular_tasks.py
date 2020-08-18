import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import requests

import helpers as hlp
from config import EXEMPT, TASK_FILE
from helpers import RangeDict

class Board:
    def __init__(self, board_name):
        self._get_board_id(board_name)
        self._get_labels()
        self.sprints = {}
        self._get_lists()
        self._get_cards()
        self._import_tasks()

    def daily_update(self):
        self.archive_cards()
        self._sprint_check()
        self.post_tasks()
        self.update_today()
        self.rearrange_cards()
        self.sort_all_lists()

    def _get_board_id(self, board_name):
        url = "https://api.trello.com/1/members/me/boards"
        boards = hlp.request("GET", url)
        board_id = [board["id"] for board in boards if board["name"] == board_name][0]
        self.board_id = board_id
        
    def _get_cards(self):
        self.card_names = []
        for list_ in self.lists.values():
            for card in list_.cards:
                self.card_names.append(card.name)

    def _get_labels(self):
        url = f"https://api.trello.com/1/boards/{self.board_id}/labels/"
        labels = hlp.request("GET", url)
        label_map = {label["name"]: label["id"] for label in labels}
        self.labels = label_map
        self.label_names = {id: name for name, id in self.labels.items()}
        print("Fetched labels")

    def _get_lists(self):
        url = f"https://api.trello.com/1/boards/{self.board_id}/lists/"
        lists_ = hlp.request("GET", url)

        self.lists = {}
        for list_input in lists_:
            list_input["board"] = self
            list_input["exempt"] = True if list_input["name"] in EXEMPT else False
            board_list = List(list_input)
            self.lists[board_list.name] = board_list
        print("Fetched lists and cards.")

    def _import_tasks(self):
        with open(TASK_FILE, "r") as f:
            tasks = json.load(f)
        self.tasks = [Task(self, task) for task in tasks]
        self.task_names = [task.name for task in self.tasks]

    def _update_task_file(self):
        task_output = hlp.format_tasks(self.tasks)
        with open(TASK_FILE, "w") as f:
            json.dump(task_output, f, default=hlp.date_handler)

    def post_tasks(self):
        for task in self.tasks:
            if task.name not in self.card_names:
                task.create_card()
            else:
                print(f"Card skipped: {task.name}")
        inbox = self.lists["Inbox"]
        inbox.get_list_cards()
    
    def _add_sprint(self, sprint):
        self.sprints[sprint.id] = sprint
    
    def remove_sprints(self, sprint_id=None):
        if sprint_id is None:
            sprints_to_go = self.sprints.copy()
        else:
            sprints_to_go = {sprint_id: self.sprints[sprint_id]}

        for sprint_id, sprint in sprints_to_go.items():
            sprint.remove()
            del self.sprints[sprint_id]
            print(f"Removed sprint {sprint_id}")

    def _sprint_check(self):
        today = hlp.localize_ts(dt.datetime.now()).date()
        sprints = self.sprints.copy()
        for sprint_id, sprint in sprints.items():
            if sprint.due_date < today:
                self.remove_sprints(sprint_id)
    
    def add_task(self):
        name = input("Enter task name: ")
        labels = input("Enter label names, separated by comma: ").split(",")
        delta = int(input("Enter task frequency: "))
        advance = True if input("Date flexible? (Y/N): ").upper() == "Y" else False
        est = int(input("Enter time estimate (in minutes): "))
        later  = True if input("Later?: ").upper() = "Y" else False
        task_input = {
            "name": name,
            "labels": labels,
            "date_info": {
                "delta": delta,
                "advance": advance,
                "last_complete": None
            },
            "time_estimate": est,
            "later": later
        }
        task = Task(self, task_input)
        self.tasks.append(task)
        self._update_task_file()

    def archive_cards(self, list_name="Done"):
        card_list = self.lists[list_name]
        card_list.archive_cards()

    def rearrange_cards(self):
        self._get_cards()
        for list_ in self.lists.values():
            card_list = list_.cards.copy()
            for card in card_list:
                card.assign_list()

    def sort_all_lists(self):
        for list_ in self.lists.values():
            list_.sort_list()

    def update_today(self):
        self._get_cards()
        today_list = self.lists["Today"]
        today = dt.datetime.today().replace(hour=23,minute=59,second=0)
        for card in today_list.cards:
            card.change_due_date(today)


class List:
    def __init__(self, list_input):
        self.board = list_input["board"]
        self.id = list_input["id"]
        self.name = list_input["name"]
        self.exempt = list_input["exempt"]
        self.get_list_cards()

    def get_list_cards(self):
        self.cards = []
        url = f'https://api.trello.com/1/lists/{self.id}/cards'
        fields = ["id","name","desc","due","labels"]
        card_list = hlp.request("GET", url, fields=fields)
        for card_input in card_list:
            card_input["due"] = hlp.localize_ts(card_input["due"])
            card_input["list"] = self
            self.cards.append(Card(card_input))
        self.time_sum()


    def sort_list(self):
        prefer_order = lambda x: (
            x.stats.get("priority", 999),
            x.labels[0]["name"],
            x.due,
            x.name)
        self.cards = sorted(self.cards, key=prefer_order)

        for rank, card in enumerate(self.cards, start=1):
            url = f"https://api.trello.com/1/cards/{card.id}"
            hlp.request("PUT", url, pos=rank)

    def time_sum(self, breakout=False):
        self.sprint_time = 0
        for card in self.cards:
            time_est = card.stats.get("time_estimate",0)
            self.sprint_time += time_est
        if breakout:
            card_list = sorted(self.cards, key=lambda x: x.stats["time_estimate"], reverse=True)
            for sort_card in card_list:
                time_est = sort_card.stats.get("time_estimate",0)
                print(sort_card.name, time_est)

    def add_sprint(self, due_date):
        sprint = Sprint(due_date, self)
        self.board._add_sprint(sprint)
    
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
        self.board._update_task_file()
        self.cards = []
        self.board._get_cards()

class Card:
    def __init__(self, card_input):
        for key, val in card_input.items():
            self.__setattr__(key, val)
        self.labels = sorted(self.labels, key=lambda x: x["name"])
        self.board = self.list.board
        self._get_stats()
        self._assign_sprint()

    def _get_stats(self):
        self.stats = {}
        if self.desc != '':
            try:
                stat_split = self.desc.split("#Stats\n")[1].replace("**","").split("\n")
            except:
                print(self.name)
                raise
            for stat in stat_split:
                key, val = stat.split(": ")
                key = hlp.snake_case(key)
                val = int(val) if val.isnumeric() else val
                self.stats[key] = val

    def _assign_sprint(self):
        if "sprint" in self.stats:
            sprint_id = self.stats["sprint"]
            if sprint_id not in self.board.sprints:
                due_date = self.stats["sprint_due"]
                sprint = Sprint(due_date)
                self.board._add_sprint(sprint)
            else:
                sprint = self.board.sprints[sprint_id]
            sprint.cards.append(self)

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
        new_list = diff_map.get(diff, "Beyond")
        if self.list.name != new_list and not self.list.exempt:
            self.move_card(new_list)

    def change_due_date(self, date):
        date = hlp.localize_ts(date)
        url = f"https://api.trello.com/1/cards/{self.id}"
        r = hlp.request("PUT", url, due=date)
        if r.status_code == 200:
            self.due = date

    def move_card(self, new_list_):
        url = f"https://api.trello.com/1/cards/{self.id}"
        new_list = self.list.board.lists[new_list_]
        r = hlp.request("PUT", url, idList=new_list.id)
        if r.status_code == 200:
            self.list.cards.remove(self)
            self.list = new_list
            self.list.cards.append(self)
            print(f"Moved card {self.name} to {self.list.name} (due {self.due})")
    
    def add_stats(self, **kwargs):
        url = f"https://api.trello.com/1/cards/{self.id}"
        for key, val in kwargs.items():
            self.stats[key] = val
        self.desc = hlp.format_desc(self.stats)
        hlp.request("PUT", url, desc=self.desc)

    def remove_stats(self, *args):
        url = f"https://api.trello.com/1/cards/{self.id}"
        for stat in args:
            try:
                del self.stats[stat]
            except KeyError:
                continue
        self.desc = hlp.format_desc(self.stats)
        hlp.request("PUT", url, desc=self.desc)

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

    def create_card_body(self):
        self.card_body = {
            "last_complete": self.date_info["last_complete"],
            "time_estimate": self.time_estimate
        }
        
    def create_card(self):
        self.assign_due_date()
        self.create_card_body()
        inbox = self._board.lists["Inbox"]

        url = "https://api.trello.com/1/cards"
        params = {
            "idList": inbox.id,
            "name": self.name,
            "idLabels": self._label_ids,
            "due": self.due,
            "desc": hlp.format_desc(self.card_body)
        }
        hlp.request("POST", url, **params)        
        print(f"Posted card: {self.name} (due {self.due.date()})")

class Sprint:
    def __init__(self, due_date, card_list=None):
        self.id = int(due_date.replace("-",""))
        self._assign_due_date(due_date)
        if card_list is not None:
            self.cards = card_list.cards.copy()
            self._activate_sprint()
        else:
            self.cards = []

    def _assign_due_date(self, due_date):
        if type(due_date) == str:
            self.due_date = dt.datetime.strptime(due_date, "%Y-%m-%d").date()
        else:
            self.due_date = due_date
    
    def _activate_sprint(self):
        for rank, card in enumerate(self.cards, start=1):
            card.add_stats(sprint=self.id, sprint_due=self.due_date, priority=rank)

    def remove(self):
        sprint_keys = ["sprint", "sprint_due", "priority"]
        for card in self.cards:
            card.remove_stats(*sprint_keys)
    


def main(board_name = "To Do List"):
    board = Board(board_name)
    board.daily_update()
    
if __name__ == "__main__":
    main()