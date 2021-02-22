from config import TASK_FILE, LABEL_PRIORITY, EXEMPT, SORT_ORDER
import trello
import datetime as dt
import json
import helpers as hlp

class Board(trello.Board):
    def __init__(self, board_name):
        self.name = board_name
        self._get_classes()
        self._get_diff_map()
        self.label_priority = LABEL_PRIORITY
        super()._get_components()
        self._import_tasks()
        self._get_projects()

    def _get_classes(self):
        self._classes = {
            "list": List,
            "card": Card
        }
    
    def _get_diff_map(self):
        hours_to_sunday = hlp.hours_to_sunday()
        self.diff_map = hlp.RangeDict({
            range(0,29): "Today",
            range(29,hours_to_sunday+1): "To Do"
        })

    def _import_tasks(self):
        with open(TASK_FILE, "r") as f:
            tasks = json.load(f)
        self.tasks = {task["name"]: Task(self, task) for task in tasks}
    
    def _update_task_file(self):
        task_output = hlp.format_tasks(self.tasks)
        with open(TASK_FILE, "w") as f:
            json.dump(task_output, f, default=hlp.date_handler)
    
    def _get_projects(self):
        self.projects = {}
        project_list = self.lists["Projects"]
        for card in project_list.cards:
            self.projects[card.name] = Project(card)

    def post_tasks(self):
        for task in self.tasks.values():
            if task.name not in self.cards:
                task.create_card()
            else:
                print(f"Card skipped: {task.name}")
        inbox = self.lists["Inbox"]
        inbox.get_list_cards()
    
    def rearrange_cards(self):
        for list_ in self.lists.values():
            if not list_.exempt:
                card_list = list_.cards.copy()
                for card in card_list:
                    if card.due is not None:
                        card.assign_list()
    
    def sort_all_lists(self):
        for list_ in self.lists.values():
            if not list_.exempt:
                list_.sort_list()


class Card(trello.Card):
    def __init__(self, card_input):
        super().__init__(card_input)
        self.priority = self._assign_priority()
    
    def _parse_labels(self):
        priority = self.board.label_priority
        label_names = [label["name"] for label in self.labels]
        priorities = sorted([priority[name] for name in label_names])
        if len(priorities) == 1:
            priorities.append(0)
        return priorities

    def _assign_priority(self):
        if len(self.labels) == 0:
            priorities = [99,99]
        else:
            priorities = self._parse_labels()
        return priorities

    def assign_list(self):
        now = hlp.localize_ts(dt.datetime.now())
        diff = int((self.due - now).total_seconds()//3600)
        new_list = self.board.diff_map.get(diff, "Someday")
        if self.list.name != new_list:
            self.move_card(new_list)

class List(trello.List):
    def __init__(self, list_input):
        super().__init__(list_input)
        self.exempt = self.name in EXEMPT
        self.sort_order = SORT_ORDER[self.name]
        
    def _log_date(self):
        for card in self.cards:
            if card.name in self.board.tasks:
                if card.due is not None:
                    due_date = card.due.strftime("%Y-%m-%d")
                    last_complete = due_date
                else:
                    last_complete = dt.date.today()
                self.board.tasks[card.name].date_info["last_complete"] = last_complete
    
    def archive_log(self):
        self._log_date()
        self.board._update_task_file()
        super().archive_cards()
    
    def sort_list(self):
        sorted_cards = sorted(self.cards, key=self.sort_order)
        pos = 0
        for card in sorted_cards:
            card.change_pos(pos)
            pos += 94

class Task:
    def __init__(self, board, task):
        self._board = board
        self.name = task["name"]
        self.labels = task["labels"]
        self._label_ids = [self._board.labels[label] for label in self.labels]
        self.date_info = task["date_info"]
        self.time_estimate = task["time_estimate"]
        self.later = task["later"]

    def _get_base_date(self):
        if self.date_info["last_complete"]:
            base = dt.datetime.strptime(self.date_info["last_complete"], "%Y-%m-%d")
        else:
            base = dt.datetime.today()
        base = base.replace(hour=23,minute=59,second=0)
        return base
    
    def _advance_date(self, date):
        next_sunday = lambda x: x + dt.timedelta(6 - x.weekday() % 7)
        if self.date_info["advance"]:
            date = next_sunday(date)
        return date

    def assign_due_date(self):
        if self.date_info["post_date"]:
            base = self._get_base_date()
            raw_due = base + dt.timedelta(self.date_info["delta"])
            utc_due = self._advance_date(raw_due)
            self.due = hlp.localize_ts(utc_due)

    def create_card_body(self):
        self.card_body = {
            "last_complete": self.date_info["last_complete"],
            "time_estimate": self.time_estimate,
            "later": self.later
        }
        
    def create_card(self):
        inbox = self._board.lists["Inbox"]
        self.assign_due_date()
        self.create_card_body()
        params = {
            "idLabels": self._label_ids,
            "due": getattr(self, "due", None),   
            "desc": hlp.format_desc(self.card_body)
        }
        inbox.add_card(self.name, **params)

class Project:
    def __init__(self, card):
        self.board = card.board
        self.card = card
        self.name = card.name
        self._get_subtasks()
    
    def _get_subtasks(self):
        self.card.get_checklists()
        self.checklist = self.card.checklists.get("Checklist", dict())
        self._parse_subtasks()
        
    def _parse_subtasks(self):
        self.subtasks = {}
        self.subtask_card_cnt = 0
        check_items = self.checklist.check_items
        for subtask, check_id in check_items.items():
            card = ''
            name, link = hlp.hyperlink_split(subtask)
            if link != '':
                card = self.board.cards[name]
                self.subtask_card_cnt += 1
            self.subtasks[name] = {"card": card, "check_id": check_id}
    
    def _make_subtask_card(self, name):
        inbox = self.board.lists["Inbox"]
        card = inbox.add_card(name, return_card=True)
        return card
    
    def _update_checkitem(self, card):
        new_name = hlp.make_hyperlink(card.name, card.url)
        self.checklist.update_item(card.name, new_name)

    
    def post_subtask_cards(self, tot_cards=1):
        for name, subtask in self.subtasks.items():
            if self.subtask_card_cnt >= tot_cards:
                break
            elif subtask["card"] == '':
                card = self._make_subtask_card(name)
                self.subtasks[name]["card"] = card
                self._update_checkitem(card)
                card.create_attachment(self.card.url)
                self.subtask_card_cnt += 1