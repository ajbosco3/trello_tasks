import post_regular_tasks as trello
import datetime as dt

def next_sunday(from_date=dt.date.today()):
    day_of_week = from_date.weekday()
    days_to_sunday = 6 - day_of_week
    sunday = from_date + dt.timedelta(days_to_sunday)
    return sunday


board = trello.Board("To Do List")
this_week = board.lists["This Week"]
sprint_date = next_sunday().__str__()
this_week.add_sprint(sprint_date)