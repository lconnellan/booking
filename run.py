#!database/bin/python
from db import app

# imports for reminders
from send_reminders import send_reminder
import schedule
from threading import Thread
import time

def sched():
    schedule.every().day.at("10:00").do(send_reminder)
    while True:
        schedule.run_pending()
        time.sleep(3600) # wait one minute

t1 = Thread(target=sched)
t1.start()

# debug=True will result in double emails being sent above
app.run(debug=False, host='0.0.0.0', port="6789")
