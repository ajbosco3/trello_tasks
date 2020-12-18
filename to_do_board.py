from config import TASK_FILE
import trello
import json

class Board(trello.Board):
    def __init__(self, board_name):
        super().__init__(board_name)
        self._import_tasks()
    
    def _import_tasks(self):
        pass


class Card(trello.Card):
    pass

class List(trello.List):
    pass

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
            "time_estimate": self.time_estimate,
            "later": self.later
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
        self.later = task["later"]