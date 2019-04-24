import datetime as dt
import json
import requests

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
        
        names = [{"name": card["name"], "id": card["id"], "list": card["idList"]} for card in cards]
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

    def create_card(self, task, card_list, freq):
        url = "https://api.trello.com/1/cards"
        list_id = self.lists[card_list]
        label_ids = [self.labels[label] for label in task["labels"]]
        card_name = task["name"]
        last_complete = task.get("last_complete", None)
        due_date = self.assign_due_date(freq, last_complete)
        
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
            tasks = json.load(f)
        return tasks

    def post_tasks(self):
        for freq, data in self.tasks.items():
            card_list = data["list"]
            card_names = [card["name"] for card in self.cards]
            for task in data["tasks"]:
                task_name = task["name"]
                if task["name"] not in card_names:
                    self.create_card(task, card_list, freq)
                else:
                    print(f"Card skipped: {task_name}")

    def update_task_file(self):
        with open("regular_tasks.json", "w") as f:
            json.dump(self.tasks, f)

    def log_date(self, list_cards):
        today = dt.date.today().strftime("%Y-%m-%d")
        for card in list_cards:
            for freq, data in self.tasks.items():
                for i, task in enumerate(data["tasks"]):
                    if card == task["name"]:
                        self.tasks[freq]["tasks"][i]["last_complete"] = today

    def archive_cards(self, list_name="Done"):
        list_id = self.lists[list_name]
        list_cards = []
        for i, card in list(enumerate(self.cards))[::-1]:
            if card["list"] == list_id:
                list_cards.append(card["name"])
                del self.cards[i]
        url = f"https://api.trello.com/1/lists/{list_id}/archiveAllCards"
        querystring = {
            "key": self.key,
            "token": self.token
        }
        requests.post(url, params=querystring)
        print(f"All cards archived in list {list_name}: {list_cards}")
        self.log_date(list_cards)
        self.update_task_file()

def main(board_name = "To Do Test"):
    board = TrelloBoard(board_name)
    board.post_tasks()
    
if __name__ == "__main__":
    main()