#!database/bin/python
from db import app

# reminder imports
from send_reminders import send_reminder
import schedule
from threading import Thread
import time

# webscrape imports
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta, date
import pymysql
from webscrape import update

def sched():
    schedule.every().day.at("10:00").do(send_reminder)
    schedule.every(60).minutes.do(update)
    while True:
        schedule.run_pending()
        time.sleep(60) # wait one minute

t1 = Thread(target=sched)
t1.start()

# debug=True will result in double emails being sent above
app.run(debug=False, host='0.0.0.0', port="6789")
