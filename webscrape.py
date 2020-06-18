import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta

from db import app
import pymysql

class Database:
    def __init__(self):
        host = app.config.get('DB_IP')
        user = app.config.get('DB_USER')
        password = app.config.get('DB_PASS')
        db = "booking"
        self.con = pymysql.connect(host=host, user=user, password=password, \
                                   db=db, cursorclass=pymysql.cursors.DictCursor)
        self.cur = self.con.cursor()

def update():
    from datetime import date
    print('starting update')
    db = Database()

    # authenticate login to website
    session_requests = requests.session()
    login_url = "https://rushcliff.com/r/login.php"
    result = session_requests.get(login_url)

    auth = {
        "uid": app.config.get('WEB_ID'),
        "password": app.config.get('WEB_PASS')
    }

    result = session_requests.post(login_url, data=auth)

    # choose date starting period, look 30 days in advance
    date_dt = date.today() #date(2020, 3, 9)
    date_range = [date_dt]
    for n in range(1, 30):
        date_range.append(date_dt + timedelta(days=n))

    for d in date_range:
        date = d.strftime("%Y-%m-%d")
        date_reversed = d.strftime("%d-%m-%Y")

        # go to diary url, extract divs with appointments
        diary_url = "https://www.rushcliff.com/r/diary.php?sdate=" + date_reversed
        result = session_requests.get(diary_url)
        soup = BeautifulSoup(result.text, "html.parser")
        divs = soup.find_all('div', {'class': 'diary_header_column_multi'})
        divs = [div.prettify() for div in divs]

        for div in divs:
            # check for certain prac name
            if div.find('WESLEY') != -1:
                # search for start of each diary appointment
                matches = re.finditer('diary_appt_time', div)
                starts = [m.start() for m in matches]
                # search for start of info
                starts2 = [div.find('title', start) for start in starts]
                starts3 = [div.find('"', start) for start in starts2]

                # substrings with appt titles
                substrings = [div[start+7:start+100] for start in starts3]

                # extract starting times
                times = [div[start+1:start+6] for start in starts3]
                times = [datetime.strptime(t, '%H:%M') for t in times]

                # continue if no appts
                if times == []:
                    continue

                # extract names
                num_ends = [re.search(r'\d', s) for s in substrings]
                names = []
                for i in range(0, len(substrings)):
                    names.append(substrings[i][:num_ends[i].start()])
                names = [n.replace('Mrs ', '') for n in names]
                names = [n.replace('Mr ', '') for n in names]
                names = [n.replace('Miss ', '') for n in names]
                names = [n.replace('Ms ', '') for n in names]
                names = [n.replace('Dr ', '') for n in names]
                first_names = [n.split(' ')[0] for n in names]
                surnames    = [n.split(' ')[1] for n in names]

                # extract durations and end times
                durations = []
                for i in range(0, len(substrings)):
                    durations.append(substrings[i][num_ends[i].start():num_ends[i].start()+3])
                durations = [d.replace('30m', '0.30') for d in durations]
                durations = [d.replace('hr30', '.30') for d in durations]
                durations = [d.replace('hr', '.00') for d in durations]
                ends = []
                for i in range(0, len(durations)):
                    delta = timedelta(hours=int(float(durations[i])),
                                      minutes=round((float(durations[i]) % 1)*100))
                    ends.append(times[i] + delta)

                # infer treatment id and price from db
                treat_ids = []
                prices = []
                for i in range(0, len(durations)):
                    if durations[i] != '0.30' and durations[i] != '1.00':
                        treat_ids.append('')
                        prices.append('')
                        continue
                    db.cur.execute("SELECT treat_id, price FROM treatments WHERE duration = %s \
                                   ORDER BY treat_id ASC", durations[i])
                    res = db.cur.fetchall()[0]
                    treat_ids.append(res['treat_id'])
                    prices.append(res['price'])

                # extract any notes
                notes_start = [s.find('Notes:') for s in substrings]
                notes_end = []
                for i in range(0, len(substrings)):
                    notes_end.append(substrings[i].find('"', notes_start[i]))
                notes = []
                for i in range(0, len(substrings)):
                    if notes_start[i] != -1:
                        notes.append(substrings[i][notes_start[i]+7:notes_end[i]])
                    else:
                        notes.append('')

                for i in range(0, len(times)):
                    start = times[i].strftime('%H:%M')
                    end = ends[i].strftime('%H:%M')
                    if first_names[i] == 'Blocked':
                        # check whether entry exists already
                        db.cur.execute("SELECT * FROM blocked_periods WHERE prac_id = 1 AND date \
                                        = %s AND start = %s AND end = %s", (date, start, end))
                        res = db.cur.fetchall()
                        if res != ():
                            continue
                        # database entry does not exist so create one
                        db.cur.execute("INSERT IGNORE INTO blocked_periods (date, start, end, \
                                        prac_id) VALUES(%s, %s, %s, %s)", (date, start, end, 1))
                        db.con.commit()
                    else:
                        # check whether entry exists already
                        db.cur.execute("SELECT * FROM bookings WHERE prac_id = 1 AND name = %s AND \
                                        start = %s AND end = %s", (date, start, end))
                        res = db.cur.fetchall()
                        if res != ():
                            continue
                        # database entry does not exist so create one
                        db.cur.execute("INSERT IGNORE INTO clients (name, surname, dob, phone_1, \
                                        phone_2, address_1, address_2, address_3, city, county, \
                                        postcode, temp) VALUES(%s, %s, NULL, NULL, NULL, NULL, \
                                        NULL, NULL, NULL, NULL, NULL, 'Temp')", (first_names[i], \
                                        surnames[i]))
                        db.con.commit()
                        db.cur.execute("SELECT client_id FROM clients ORDER BY client_id desc \
                                        limit 1;")
                        client_id = db.cur.fetchall()[0]['client_id']
                        db.cur.execute("INSERT IGNORE INTO users (email, password, access_lvl, \
                                        auth_key, client_id, prac_id) VALUES('dummy', '', -1, \
                                        'dummy', %s, NULL)", client_id)
                        db.con.commit()
                        db.cur.execute("INSERT IGNORE INTO bookings (prac_id, client_id, treat_id, \
                                        name, start, end, descr, price, pay_status) VALUES(%s, %s, \
                                        %s, %s, %s, %s, %s, %s, 'not paid')", (1, client_id, \
                                        treat_ids[i], date, start, end, notes[i], prices[i]))
                        db.con.commit()
    print('starting update')
