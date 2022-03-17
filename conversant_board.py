import trello
import helpers as hlp

class Board(trello.Board):
    def __init__(self, board_name):
        self.name = board_name
        super()._get_components()
        self._get_invisible_cards()
        self._get_projects()
    
    def _get_invisible_cards(self):
        self.invisible_cards = {}
        url = f"https://api.trello.com/1/boards/{self.board_id}/cards/closed"
        cards = hlp.request("GET", url)[:300]
        for card in cards:
            self._register_invisible_card(card)

    def _register_invisible_card(self, card):
        if isinstance(card, trello.Card) is False:
            card["board"] = self
            card = trello.Card(card)
        url = card.shortlink
        self.invisible_cards[url] = card
    
    def _create_invisible_card(self, card_name):
        inbox = self.lists["Inbox"]
        card = inbox.add_card(card_name, return_card=True)
        card.archive()
        self._register_invisible_card(card)
        return card
    
    def _get_projects(self):
        self.projects = {}
        for card in self.cards.values():
            if hlp.is_project(card):
                self.projects[card.name] = Project(card)

class Project:
    def __init__(self, card):
        self.board = card.board
        self.card = card
        self.card_name = card.name
        self._get_project_titles()
        self._get_tasks()

    def _get_project_titles(self):
        split = self.card_name.split("||")
        self.title = split[0]
        if "||" in self.card_name:
            self.subtitle = split[1]
    
    def _get_tasks(self):
        self.card.get_checklists()
        self._parse_tasks()

    def _parse_tasks(self):
        self.tasks = {}
        for checklist_name, checklist in self.card.checklists.items():
            subtasks = {}
            for check_item in checklist.check_items:
                task = self._register_task(check_item, checklist)
                subtasks[task.name] = task
            self.tasks[checklist_name] = subtasks
    
    def _register_task(self, check_item, checklist):
        task_input = {"name": check_item}
        task_input["board"] = self.board
        task_input["project"] = self
        task_input["checklist"] = checklist
        task = Task(task_input)
        return task
    
    def update_subtitle(self, subtitle):
        self.subtitle = subtitle
        self.card_name = f"{self.title}||{self.subtitle}"
        self.card.update_name(self.card_name)
    
    def next_task_subtitle(self):
        for _, tasks in self.tasks.items():
            for task in tasks.keys():
                self.update_subtitle(task)
                break
    
    def link_all_tasks(self):
        for _, tasks in self.tasks.items():
            for task in tasks.values():
                task.link_task()

class Task:
    def __init__(self, task_input):
        self.raw_name = task_input["name"]
        self.board = task_input["board"]
        self.project = task_input["project"]
        self.checklist = task_input["checklist"]
        self._is_url()
        self._get_task_name()
    
    def _is_url(self):
        if "trello.com/c/" in self.raw_name:
            self.is_url = True
            self.url = self.raw_name
        else:
            self.is_url = False
            self.url = None

    def _get_task_name(self):
        if self.is_url:
            shortlink = hlp.get_shortlink(self.url)
            self.card = self.board.invisible_cards[shortlink]
            self.name = self.card.name
        else:
            self.card = None
            self.name = self.raw_name
    
    def link_task(self):
        if self.is_url is False:
            self.card = self.board._create_invisible_card(self.name)
            self.raw_name = self.card.url
            self._is_url()
            self.checklist.update_item(self.name, self.url)
        