import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import requests

import helpers as hlp

class Board:
    def __init__(self, board_name):
        self.name = board_name
        self._get_classes()
        self._get_components()

    def _get_classes(self):
        self._classes = {
            "list": List,
            "card": Card
        }

    def _get_components(self):
        self._get_board_id()
        self._get_labels()
        self._get_lists()
        self._get_cards()

    def _get_board_id(self):
        url = "https://api.trello.com/1/members/me/boards"
        boards = hlp.request("GET", url)
        board_id = [board["id"] for board in boards if board["name"] == self.name][0]
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
            board_list = self._classes["list"](list_input)
            self.lists[board_list.name] = board_list
        print("Fetched lists and cards.")

    def archive_cards(self, list_name="Done"):
        card_list = self.lists[list_name]
        card_list.archive_cards()

class List:
    def __init__(self, list_input):
        self.board = list_input["board"]
        self.id = list_input["id"]
        self.name = list_input["name"]
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
    
    def get_checklists(self, get_complete=True):
        self.checklists = defaultdict(list)
        url = f"https://api.trello.com/1/cards/{self.id}/checklists"
        raw = hlp.request("GET", url)

        for checklist in raw:
            name = checklist["name"]
            check_items = sorted(checklist["checkItems"], key=lambda x: x["pos"])
            for checkitem in check_items:
                if get_complete == False and checkitem["state"] == "complete":
                    continue
                item_name = checkitem["name"]
                self.checklists[name].append(item_name)