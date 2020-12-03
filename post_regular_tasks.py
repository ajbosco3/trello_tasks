import datetime as dt
import json
from collections import defaultdict
from distutils.util import strtobool
from pathlib import Path

import requests

import helpers as hlp
from config import EXEMPT
from helpers import RangeDict

class Board:
    def __init__(self, board_name):
        self._get_board_id(board_name)
        self._get_labels()
        self._get_lists()
        self._get_cards()

    def daily_update(self):
        self.archive_cards()
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

    def archive_cards(self):
        url = f"https://api.trello.com/1/lists/{self.id}/archiveAllCards"
        hlp.request("POST", url)
        
        card_names = [card.name for card in self.cards]
        print(f"All cards archived in list {self.name}: {card_names}")
        self.cards = []
        self.board._get_cards()

class Card:
    def __init__(self, card_input):
        for key, val in card_input.items():
            self.__setattr__(key, val)
        self.labels = sorted(self.labels, key=lambda x: x["name"])
        self.board = self.list.board
        self._get_stats()

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
                if val.isnumeric():
                    val = int(val)
                elif val in ("True", "False"):
                    val = bool(strtobool(val))
                self.stats[key] = val

    def assign_list(self):
        now = hlp.localize_ts(dt.datetime.now())
        sunday = (now + dt.timedelta(6 - now.weekday() % 7)).replace(hour=23, minute=59, second=0)
        diff = int((self.due - now).total_seconds()//3600)
        later = self.stats.get("later", False)

        hours_to_sunday = int((sunday - now).total_seconds()//3600)
        if hours_to_sunday < 28:
            hours_to_sunday += 168

        diff_map = RangeDict({
            range(0,29): "Later" if later is True else "Today",
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
    
    def get_checklists(self):
        self.checklists = defaultdict(list)
        url = f"https://api.trello.com/1/cards/{self.id}/checklists"
        raw = hlp.request("GET", url)

        for checklist in raw:
            name = checklist["name"]
            check_items = sorted(checklist["checkItems"], key=lambda x: x["pos"])
            for checkitem in check_items:
                item_name = checkitem["name"]
                self.checklists[name].append(item_name)


def main(board_name = "To Do List"):
    board = Board(board_name)
    board.daily_update()
    
if __name__ == "__main__":
    main()