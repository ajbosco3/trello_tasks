import random
from collections import defaultdict
from itertools import groupby

import trello

class Board(trello.Board):
    def __init__(self, board_name):
        super().__init__(board_name)
        self.by_label = lambda x: x.labels[0]["name"]
        self.get_lists_to_check()
        self._get_done_labels()

    def _sorted_card_list(self, list_name):
        card_list = self.lists[list_name]
        sorted_list = sorted(card_list.cards, key=self.by_label)
        return sorted_list
    
    def _get_done_labels(self):
        self.done_labels = []
        this_week = self.lists["This Week"]
        for card in this_week.cards:
            label = card.labels[0]["name"]
            self.done_labels.append(label)

    def get_lists_to_check(self):
        self.lists_to_check = []
        list_names = ("This Month", "Reading")
        for list_ in list_names:
            sorted_list = self._sorted_card_list(list_)
            self.lists_to_check.append(sorted_list)

    def choose_cards(self):
        for article_list in self.lists_to_check:
            for label, _cards in groupby(article_list, self.by_label):
                if label not in self.done_labels:
                    article = random.choice(list(_cards))
                    article.move_card("This Week")
                    self.done_labels.append(label)

if __name__ == "__main__":
    board = Board("Professional Development")
    board.choose_cards()