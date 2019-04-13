import datetime as dt
import json
import requests

class TrelloBoard:
    def __init__(self, board_name):
        self.key = "***REMOVED***"
        self.token = "***REMOVED***"
        self.board_id = self.get_board_id(board_name)
        self.cards = self.get_cards()
        self.labels = self.get_labels()
        self.lists = self.get_lists()
        self.tasks = self.import_tasks()

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
        url = "https://api.trello.com/1/boards/5cb0f20ceab39310f1be32b1/cards/"
        querystring = {
            "key": self.key,
            "token": self.token,
            "visible": "true"
        }
        r = requests.get(url, params=querystring)
        cards = r.json()
        
        names = [card["name"] for card in cards]
        print("Fetched cards")
        return names

    def get_labels(self):
        url = "https://api.trello.com/1/boards/5cb0f20ceab39310f1be32b1/labels/"
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
        url = "https://api.trello.com/1/boards/5cb0f20ceab39310f1be32b1/lists/"
        querystring = {
            "key": self.key,
            "token": self.token
        }
        r = requests.get(url, params=querystring)
        lists_ = r.json()
        lists = {list_["name"]: list_["id"] for list_ in lists_}
        print("Fetched lists")
        return lists

    def create_card(self, task, card_list, freq):
        url = "https://api.trello.com/1/cards"
        list_id = self.lists[card_list]
        label_ids = [self.labels[label] for label in task["labels"]]
        card_name = task["name"]
        due_date = self.assign_due_date(freq)
        
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

    def assign_due_date(self, freq):
        today = (dt.datetime.today() + dt.timedelta(1)).replace(hour=0,minute=30,second=0)
        delta = {"daily": dt.timedelta(0),
                "weekly": dt.timedelta(4 - today.weekday() % 7),
                "monthly": dt.timedelta(30),
                "bi-weekly": dt.timedelta()}
        due_date = today + delta[freq]
        return due_date
    

    def import_tasks(self):
        with open("regular_tasks.json", "r") as f:
            tasks = json.load(f)
        return tasks

    def post_tasks(self):
        for freq, data in self.tasks.items():
            card_list = data["list"]
            for task in data["tasks"]:
                task_name = task["name"]
                if task["name"] not in self.cards:
                    self.create_card(task, card_list, freq)
                else:
                    print(f"Card skipped: {task_name}")


def main():
    board = TrelloBoard()
    board.post_tasks()
    
if __name__ == "__main__":
    main()
    
