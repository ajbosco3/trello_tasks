from collections import defaultdict
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
        self.cards = {}
        for list_ in self.lists.values():
            for card in list_.cards:
                self.cards[card.name] = card

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
    
    def _register_card(self, card_input):
        card_input["list"] = self
        card_input["due"] = hlp.localize_ts(card_input.get("due", None))
        card = Card(card_input)
        self.cards.append(card)
        return card

    def get_list_cards(self):
        self.cards = []
        url = f'https://api.trello.com/1/lists/{self.id}/cards'
        fields = ["id","name","desc","due","labels","url"]
        card_list = hlp.request("GET", url, fields=fields)
        for card_input in card_list:
            self._register_card(card_input)

    def add_card(self, name, return_card=False, **kwargs):
        url = "https://api.trello.com/1/cards"
        params = {
            "idList": self.id,
            "name": name,
            **kwargs
        }
        r = hlp.request("POST", url, **params)
        card = self._register_card(r.json())
        print(f"Posted card: {name}")
        if return_card:
            return card

    def archive_cards(self):
        url = f"https://api.trello.com/1/lists/{self.id}/archiveAllCards"
        hlp.request("POST", url)
        
        card_names = [card.name for card in self.cards]
        print(f"All cards archived in list {self.name}: {card_names}")
        self.cards = []
        self.board._get_cards()

class Card:
    def __init__(self, card_input):
        self.id = card_input["id"]
        self.name = card_input["name"]
        self.desc = card_input["desc"]
        self.due = card_input["due"]
        self.labels = sorted(card_input["labels"], key=lambda x: x["name"])
        self.url = card_input["url"]
        self.list = card_input["list"]
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
    
    def get_checklists(self):
        self.checklists = {}
        url = f"https://api.trello.com/1/cards/{self.id}/checklists"
        raw = hlp.request("GET", url)
        for checklist in raw:
            checklist["card"] = self
            name = checklist["name"]
            self.checklists[name] = Checklist(checklist)
    
    def create_attachment(self, attach_url):
        url = f"https://api.trello.com/1/cards/{self.id}/attachments"
        params = {
            "url": attach_url
        }
        hlp.request("POST", url, **params)

class Checklist:
    def __init__(self, check_input):
        self.card = check_input["card"]
        self.name = check_input["name"]
        self._parse_input(check_input)
    
    def _parse_input(self, check_input, get_complete=False):
        self.check_items = {}
        check_items = sorted(check_input["checkItems"], key=lambda x: x["pos"])
        for checkitem in check_items:
            if get_complete == False and checkitem["state"] == "complete":
                continue
            item_name = checkitem["name"]
            item_id = checkitem["id"]
            self.check_items[item_name] = item_id
    
    def update_item(self, name, new_name, state="incomplete"):
        item_id = self.check_items[name]
        url = f"https://api.trello.com/1/cards/{self.card.id}/checkItem/{item_id}"
        params = {
            "name": new_name,
            "state": state
        }
        hlp.request("PUT", url, **params)
        self.card.get_checklists()
