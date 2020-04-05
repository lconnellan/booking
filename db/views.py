from flask import render_template, redirect, url_for, request, session, flash, make_response, send_file
from flask_mail import Message
import pymysql
import hashlib
from functools import wraps
from datetime import datetime, timedelta, date, time
import ast
import random
import string
from io import BytesIO
from base64 import b64decode
import intervals as intervals

from db import app, mail

class Database:
    def __init__(self):
        host = '192.168.251.141'
        user = "lloyd"
        password = "cr1cket"
        db = "booking"
        self.con = pymysql.connect(host=host, user=user, password=password, \
                                   db=db, cursorclass=pymysql.cursors.DictCursor)
        self.cur = self.con.cursor()
    def list_table(self, table):
        """Fetch entries from a table, ignoring auto_inc and checking if str"""
        self.cur.execute("SELECT * FROM %s LIMIT 50" % table)
        result = self.cur.fetchall()
        self.cur.execute("SHOW COLUMNS FROM %s" % table)
        columns = self.cur.fetchall()
        column_type = {}
        for col in columns:
            if col['Extra'] == 'auto_increment':
                column_type[col['Field']] = 'auto'
            elif col['Type'] in ['date', 'time']:
                column_type[col['Field']] = 'str'
            elif 'varchar' in col['Type']:
                column_type[col['Field']] = 'str'
            elif col['Key'] == 'MUL':
                column_type[col['Field']] = 'foreign'
            else:
                column_type[col['Field']] = 'num'
        self.cur.execute("USE information_schema")
        self.cur.execute("SELECT REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME \
                          FROM KEY_COLUMN_USAGE WHERE TABLE_NAME = %s", (table, ))
        foreign_keys = self.cur.fetchall()
        self.cur.execute("USE booking")
        named_keys = {}
        for key in foreign_keys:
            if key['REFERENCED_TABLE_NAME'] != None:
                rtable = key['REFERENCED_TABLE_NAME']
                rcol = key['REFERENCED_COLUMN_NAME']
                self.cur.execute("SELECT %s.name, %s.%s FROM %s" % (rtable, rtable, rcol, rtable))
                tmp = self.cur.fetchall()
                named_keys[rcol] = {}
                for entry in tmp:
                    named_keys[rcol][entry[rcol]] = entry['name']
        return result, column_type, named_keys
    def authenticate(self, email, password_in):
        """Hash password and check versus stored email/pass in db"""
        m = hashlib.md5()
        m.update(bytes(password_in, encoding='utf-8'))
        password_in = m.hexdigest()
        # fetch password from db
        self.cur.execute("SELECT password FROM users WHERE email = %s", (email, ))
        res = self.cur.fetchall()
        if not res:
            flash('Email not registered. Please create an account.')
            return False
        else:
            password = res[0]['password']
        if password_in == password:
            flash('Signed in.')
            session['email'] = email
            self.cur.execute("SELECT access_lvl FROM users WHERE email = %s", (email, ))
            session['access_lvl'] = self.cur.fetchall()[0]['access_lvl']
            self.cur.execute("SELECT client_id FROM users WHERE email = %s", (email, ))
            client_id = self.cur.fetchall()[0]['client_id']
            if client_id != None:
                session['client_id'] = client_id
            return True
        else:
            flash('Email or password incorrect. Please try again.')
            return False

def auth_required(level=2):
    def callable(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not 'access_lvl' in session:
                session['error'] = 'Login is required to continue.'
                return redirect(url_for('login', next=request.path[1:]))
            elif session['access_lvl'] == -1:
                session['error'] = 'Account registration still needs to be \
                                    completed. Please check your emails.'
                return redirect(url_for('index'))
            elif session['access_lvl'] < level:
                session['error'] = 'User access level insufficient.'
                return redirect(url_for('login', next=request.path[1:]))
            return func(*args, **kwargs)
        return wrapper
    return callable

@app.route('/')
def index():
    return render_template('index.html', session=session)

@app.route('/error/<error>', methods=['GET', 'POST'])
def error(error):
    if request.method == 'POST':
        return redirect(url_for('index'))
    return render_template('error.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    db = Database()
    if request.method == 'POST':
        if request.form['next'] == 'login':
            success = db.authenticate(request.form['email'], request.form['password'])
            if success:
                return redirect(request.args.get('next') or url_for('index'))
            else:
                return redirect(url_for('login', next=request.args.get('next')))
        if request.form['next'] == 'create':
            return redirect(url_for('create_account'))
        if request.form['next'] == 'reset':
            return redirect(url_for('reset_password'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('email', None)
    session.pop('access_lvl', None)
    session.pop('client_id', None)
    flash("You have logged out.")
    return redirect(request.args.get('next') or url_for('index'))

@app.route('/create_account', methods=['GET', 'POST'])
def create_account():
    db = Database()
    if request.method == 'POST':
        if not request.form['password'] == request.form['password_confirm']:
            error = 'Error: passwords do not match'
            session['error'] = error
            return redirect(url_for('create_account'))
        else:
            password = request.form['password']
            email = request.form['email']
            if not '@' in email or not '.' in email:
                error = 'Error: email not valid.'
                session['error'] = error
                return redirect(url_for('create_account'))
            db.cur.execute("SELECT email FROM users")
            emails = [emails['email'] for emails in db.cur.fetchall()]
            if email in emails:
                error = 'Sorry but that email is already registered. Please \
                         login or reset your password if necessary.'
                session['error'] = error
                return redirect(url_for('create_account'))
            #generate hashed password
            m = hashlib.md5()
            m.update(bytes(password, encoding='utf-8'))
            password = m.hexdigest()
            # generate random auth key
            key = ''.join([random.choice(string.ascii_letters + string.digits) for n in range(32)])
            forms = request.form.copy()
            for f in forms:
                if forms[f] == '':
                    if any(f == field for field in ['phone_2', 'address_2', 'address_3', 'county']):
                        forms[f] = None
                    else:
                        error = 'Please submit details for all fields marked with a *'
                        session['error'] = error
                        return redirect(url_for('create_account'))
            # insert new details into db
            db.cur.execute("INSERT IGNORE INTO clients (name, surname, dob, phone_1, phone_2, \
                           address_1, address_2, address_3, city, county, postcode) \
                           VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", \
                           (forms['name'], forms['surname'], forms['dob'], forms['phone_1'], \
                           forms['phone_2'], forms['address_1'], forms['address_2'], \
                           forms['address_3'], forms['city'], forms['county'], forms['postcode']))
            db.con.commit()
            db.cur.execute("SELECT client_id FROM clients order by client_id desc limit 1;")
            client_id = db.cur.fetchall()[0]['client_id']
            db.cur.execute("INSERT IGNORE INTO users (email, password, access_lvl, \
                           auth_key, client_id, prac_id) VALUES(%s, %s, -1, %s, %s, NULL)", \
                           (email, password, key, client_id))
            db.con.commit()
            # send email with confirmation link
            link = 'http://192.168.251.131:6789/email_confirmation/' + key
            msg = Message("Please verify your email address", \
                          sender=app.config.get('MAIL_USERNAME'), recipients=[email])
            msg.html = render_template('pass_confirm.html', link=link)
            mail.send(msg)
            flash("An email has been sent to %s to confirm your registration." % email)
            return redirect(request.args.get('next') or url_for('index'))
    return render_template('create_account.html')

@app.route('/email_confirmation/<key>')
def email_confirmation(key):
    db = Database()
    db.cur.execute("UPDATE users SET access_lvl = 0, auth_key = NULL WHERE auth_key = %s", (key, ))
    db.con.commit()
    return render_template('email_confirmation.html')

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    db = Database()
    if request.method == 'POST':
        email = request.form['email']
        # generate random auth key
        key = ''.join([random.choice(string.ascii_letters + string.digits) for n in range(32)])
        db.cur.execute("UPDATE users SET auth_key = %s WHERE email = %s", (key, email))
        db.con.commit()
        # send email with confirmation link
        link = 'http://192.168.251.131:6789/reset_confirmation/' + key
        msg = Message("Password reset confirmation", sender=app.config.get('MAIL_USERNAME'), recipients=[email])
        msg.html = render_template('pass_reset.html', link=link)
        mail.send(msg)
        flash("An email has been sent to %s reset your password." % email)
        return redirect(request.args.get('next') or url_for('index'))
    return render_template('reset_password.html')

@app.route('/reset_confirmation/<key>', methods=['GET', 'POST'])
def reset_confirmation(key):
    db = Database()
    if request.method == 'POST':
        if not request.form['password'] == request.form['password_confirm']:
            error = 'Passwords do not match'
            session['error'] = error
            return redirect(url_for('reset_confirmation', key=key))
        else:
            password = request.form['password']
            #generate hashed password
            m = hashlib.md5()
            m.update(bytes(password, encoding='utf-8'))
            password = m.hexdigest()
            db.cur.execute("UPDATE users SET password = %s, auth_key = NULL WHERE auth_key = %s", \
                           (password, key))
            db.con.commit()
            flash("You have successfully changed your password.")
            return redirect(url_for('index'))
    return render_template('reset_confirmation.html')

@app.route('/database')
@auth_required(level=2)
def database():
    db = Database()
    db.cur.execute("SHOW TABLES WHERE tables_in_booking NOT LIKE 'notes'")
    res = db.cur.fetchall()
    return render_template('database.html', result=res)

@app.route('/database/<table>', methods=['GET', 'POST'])
@auth_required(level=2)
def tables(table):
    db = Database()
    res = db.list_table(table)
    if request.method == 'POST':
        if 'add' in request.form:
            return redirect(url_for('tables_add', table=table))
        elif 'delete' in request.form:
            # delete using the primary key (which is identified by 'auto')
            col_type = res[1]
            auto_field = [field for field in col_type if col_type[field] == 'auto'][0]
            try:
                db.cur.execute("DELETE FROM %s WHERE %s = %s" % \
                               (table, auto_field, request.form['delete']))
                db.con.commit()
            except:
                error = 'Error: this row cannot be deleted as another row \
                         in the table depends upon it.'
                return redirect(url_for('error', error=error))
            return redirect(url_for('tables', table=table))
    return render_template('tables.html', result=res[0], col_type=res[1], named_keys=res[2])

@app.route('/database/<table>_add', methods=['GET', 'POST'])
@auth_required(level=2)
def tables_add(table):
    db = Database()
    res = db.list_table(table)
    if request.method == 'POST':
        if request.form['submit'] == 'yes':
            first = True
            # compose a string of inputs to put into database
            for fieldname, value in request.form.items():
                if fieldname != 'submit':
                    col_type = res[1]
                    if col_type[fieldname] == 'str':
                        value = "'" + value + "'"
                    # first entry doesn't need preceeding comma
                    if first:
                        fieldnames = fieldname
                        values = value
                        first = False
                    else:
                        fieldnames += ', ' + fieldname
                        values += ', ' + value
            query = "INSERT IGNORE INTO %s (%s) VALUES (%s);" % (table, fieldnames, values)
            db.cur.execute("INSERT IGNORE INTO %s (%s) VALUES (%s);" % (table, fieldnames, values))
            db.con.commit()
            return redirect(url_for('tables', table=table))
    return render_template('tables_add.html', result=res[0], col_type=res[1], named_keys=res[2])

@app.route('/treatments', methods=['GET', 'POST'])
def treatments():
    db = Database()
    # fetch list of treatments
    db.cur.execute("SELECT * FROM treatments")
    treatments = db.cur.fetchall()
    time = []
    for t in treatments:
        hours = int(t['duration'])
        mins = int((t['duration'] - int(t['duration']))*100)
        t = ''
        if hours >= 2:
            t += str(hours) + ' hours'
        elif hours >= 1:
            t += str(hours) + ' hour'
        if mins > 0 and hours != 0:
            t += ', ' + str(mins) + ' minutes'
        elif hours == 0:
            t += str(mins) + ' minutes'
        time.append(t)
    # create treatment links
    if request.method == 'POST':
        session['treatment'] = request.form['type']
        db.cur.execute("SELECT treat_id, duration, price FROM treatments where \
                       name = %s", (session['treatment'], ))
        res = db.cur.fetchall()[0]
        session['duration'] = str(res['duration'])
        session['price'] = str(res['price'])
        session['treat_id'] = str(res['treat_id'])
        return redirect(url_for('dates'))
    return render_template('treatments.html', treatments=treatments, time=time)

def datetime_range(start, end, delta):
    """Generator function for time range"""
    current = start
    while current < end:
        yield current
        current += delta

def interval_conversion(list, avail=False):
    """Converts time data into interval format"""
    intervals_list = []
    dur_h = int(session['duration'].split('.')[0])
    dur_m = int(session['duration'].split('.')[1])
    duration = timedelta(hours=dur_h, minutes=dur_m)
    for l in list:
        if avail:
            intervals_list.append([intervals.closed(
                                  datetime.combine(l[0], l[1]),
                                  datetime.combine(l[0], l[2])
                                  - duration), l[3]])
        else:
            intervals_list.append([intervals.closedopen(
                                  datetime.combine(l[0], l[1]),
                                  datetime.combine(l[0], l[2])), l[3]])
    return intervals_list

def time_slots(date, day):
    db = Database()
    # fetch list of availabilities
    db.cur.execute("SELECT day, start, end, prac_id FROM avails")
    avails = [[entry['day'], (datetime.min + entry['start']).time(),
                             (datetime.min + entry['end']).time(),
               entry['prac_id']] for entry in db.cur.fetchall()]
    # fetch list of existing bookings
    db.cur.execute("SELECT name, start, end, prac_id FROM bookings")
    bookings = [[entry['name'], (datetime.min + entry['start']).time(),
                                (datetime.min + entry['end']).time(),
                 entry['prac_id']] for entry in db.cur.fetchall()]
    # fetch list of blocked periods
    db.cur.execute("SELECT date, start, end, prac_id FROM blocked_periods")
    blocked = [[entry['date'], (datetime.min + entry['start']).time(),
                               (datetime.min + entry['end']).time(),
                entry['prac_id']] for entry in db.cur.fetchall()]

    # fetch availabilities for current day
    valid_avails = []
    for a in avails:
        if day == a[0]:
            a[0] = datetime(int(date.split('-')[0]),
                            int(date.split('-')[1]),
                            int(date.split('-')[2]))
            valid_avails.append(a)
    if not valid_avails:
        return [], 0
    avails_i = interval_conversion(valid_avails, avail=True)
    bookings_i = interval_conversion(bookings)
    blocked_i = interval_conversion(blocked)
    # subtract booked periods from available ones
    for a in avails_i:
        now = datetime.now()
        # remove times that have already happened
        a[0] = a[0] - intervals.closedopen(now - timedelta(hours=24), now)
        # restrict to 12 hours in advance for non admin
        if 'access_lvl' in session:
            if session['access_lvl'] < 2:
                a[0] = a[0] - intervals.closedopen(now, now + timedelta(hours=12))
        else:
            a[0] = a[0] - intervals.closedopen(now, now + timedelta(hours=12))
        for b in bookings_i:
            if a[1] == b[1]:
                a[0] = a[0] - b[0]
        for b in blocked_i:
            if a[1] == b[1]:
                a[0] = a[0] - b[0]

    # generate list of all possible times in a day
    time_slots = [dt for dt in
        datetime_range(datetime.combine(valid_avails[0][0], time(hour=9)),
                       datetime.combine(valid_avails[0][0], time(hour=19, minute=55)),
                       timedelta(minutes=30))]
    # find available slots
    sessions = 0
    for i, t in enumerate(time_slots):
        pracs = []
        for avail in avails_i:
            if t in avail[0]:
                pracs.append(avail[1])
                sessions += 1
        time_slots[i] = [t.strftime('%-H:%M'), pracs]
    return time_slots, sessions

@app.route('/dates', methods=['GET', 'POST'])
def dates():
    # collect list of dates for next month
    today = date.today()
    date_range = [today]
    for n in range(1, 28):
        date_range.append(today + timedelta(days=n))
    # format it nicely
    date_range_f = [d.strftime("%A %d %B") for d in date_range]
    avails = []
    for d in date_range:
        dat = d.strftime('%Y-%m-%d')
        day = d.strftime('%A')
        slots, sessions = time_slots(dat, day)
        if sessions == 0:
            avails.append('False')
        else:
            avails.append('True')

    # reobtain original date from user input and store it
    if request.method == 'POST':
        for n in range(0, 28):
            if date_range_f[n] == request.form['date']:
                day = n
        session['date'] = date_range[day].strftime('%Y-%m-%d')
        session['day'] = date_range[day].strftime('%A')
        return redirect(url_for('booking'))
    return render_template('dates.html', date_range=date_range_f, avails=avails)

@app.route('/booking', methods=['GET', 'POST'])
def booking():
    db = Database()
    slots = time_slots(session['date'], session['day'])[0]
    if request.method == 'POST':
        res = ast.literal_eval(request.form['time_slot'])
        session['time_slot'] = res[0]
        session['end'] = (datetime(1990, 1, 1, int(res[0].split(':')[0]), \
                          int(res[0].split(':')[1])) + timedelta( \
                          hours=int(session['duration'].split('.')[0]), \
                          minutes=int(session['duration'].split('.')[1]))).strftime('%-H:%M')
        # fetch list of practitioners
        pracs = []
        for prac_id in res[1]:
            db.cur.execute("SELECT name, surname FROM practitioners \
                           WHERE prac_id = %s" % str(prac_id))
            pracs.append([[entry['name'] + ' ' + entry['surname'] \
                         for entry in db.cur.fetchall()][0], prac_id])
        session['pracs'] = pracs
        return redirect(url_for('practitioner_choice'))

    return render_template('booking.html', time_slots=slots)

@app.route('/practitioner_choice', methods=['GET', 'POST'])
@auth_required(level=0)
def practitioner_choice():
    if request.method == 'POST':
        res = ast.literal_eval(request.form['type'])
        session['prac'] = res[0]
        session['prac_id'] = res[1]
        if 'client_id' in session or 'client_id_tmp' in session:
            return redirect(url_for('confirmation'))
        else:
            return redirect(url_for('client_choice'))
    return render_template('practitioner_choice.html', pracs=session['pracs'])

@app.route('/confirmation', methods=['GET', 'POST'])
@auth_required(level=0)
def confirmation():
    if request.method == 'POST':
        if request.form['answer'] == "proceed":
            db = Database()
            if 'client_id' in session:
                client_id = session['client_id']
            else:
                client_id = session['client_id_tmp']
                session.pop('client_id_tmp')
            db.cur.execute("INSERT IGNORE INTO bookings (prac_id, client_id, treat_id, name,\
                           start, end, descr, price, pay_status) VALUES(%s, %s, %s, %s, %s, %s, \
                           %s, %s, 'not paid')", (str(session['prac_id']), str(client_id), \
                           str(session['treat_id']), session['date'], session['time_slot'], \
                           session['end'], request.form['descr'], session['price']))
            db.con.commit()

            return redirect(url_for('completed'))
        elif request.form['answer'] == "cancel":
            return redirect(url_for('index'))
    return render_template('confirmation.html', session=session)

@app.route('/client_choice', methods=['GET', 'POST'])
@auth_required(level=2)
def client_choice():
    db = Database()
    db.cur.execute("SELECT name, surname, client_id FROM clients ORDER BY surname")
    res = db.cur.fetchall()
    clients = [[entry['name'] + ' '  + entry['surname'], entry['client_id']] for entry in res]
    if request.method == 'POST':
        res = ast.literal_eval(request.form['client'])
        session['client_id_tmp'] = res
        return redirect(url_for('confirmation'))
    return render_template('client_choice.html', clients=clients)

@app.route('/completed', methods=['GET', 'POST'])
@auth_required(level=0)
def completed():
    if request.method == 'POST':
        if request.form['type'] == "return":
            return redirect(url_for('index'))
    return render_template('completed.html')

@app.route('/prices')
def prices():
    return render_template('prices.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/what-to-expect')
def what_to_expect():
    return render_template('what_to_expect.html')

@app.route('/our-team')
def our_team():
    return render_template('our_team.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/osteopathy')
def osteopathy():
    return render_template('osteopathy.html')

@app.route('/my_appointments', methods=['GET', 'POST'])
@auth_required(level=0)
def my_appointments():
    db = Database()
    db.cur.execute("SELECT client_id, prac_id FROM users WHERE email = %s", (session['email']))
    res = db.cur.fetchall()
    client_id = res[0]['client_id']
    prac_id = res[0]['prac_id']
    if client_id == None:
        db.cur.execute("SELECT * FROM bookings WHERE prac_id = %s order by name desc" \
                       % str(prac_id))
    else:
        db.cur.execute("SELECT * FROM bookings WHERE client_id = %s order by name desc" \
                       % str(client_id))
    bookings = db.cur.fetchall()
    res = db.list_table('bookings')
    if request.method == 'POST':
        if 'delete' in request.form:
            try:
                db.cur.execute("DELETE FROM bookings WHERE booking_id = %s" % \
                               request.form['delete'])
                db.con.commit()
            except:
                error = 'Error: this row cannot be deleted as another row \
                         in the table depends upon it.'
                return redirect(url_for('error', error=error))
            return redirect(url_for('my_appointments'))
        elif 'submit' in request.form:
            pay_status = 'pay_status' + request.form['submit']
            db.cur.execute("UPDATE bookings SET pay_status = %s WHERE booking_id = %s", \
                           (request.form[pay_status], request.form['submit']) )
            price = 'price' + request.form['submit']
            db.cur.execute("UPDATE bookings SET price = %s WHERE booking_id = %s", \
                           (request.form[price], request.form['submit']) )
            db.con.commit()
            return redirect(url_for('my_appointments'))
        elif 'view' in request.form:
            return redirect(url_for('appointment_notes', booking_id=request.form['view']))
        elif 'invoice-submit' in request.form:
            id_list = request.form.getlist('invoice')
            return redirect(url_for('invoice', id_list=id_list))
    return render_template('my_appointments.html', bookings=bookings, col_type=res[1], \
                           named_keys=res[2], access_lvl=session['access_lvl'])

@app.route('/my_appointments/visual/<week>')
@auth_required(level=0)
def my_appointments_gui(week):
    db = Database()
    db.cur.execute("SELECT * FROM users WHERE email = %s", (session['email']))
    res = db.cur.fetchall()[0]
    prac_id = res['prac_id']
    client_id = res['client_id']
    if client_id == None:
        db.cur.execute("SELECT * FROM bookings WHERE prac_id = %s" % prac_id)
    else:
        db.cur.execute("SELECT * FROM bookings WHERE client_id = %s" % client_id)
    bookings = db.cur.fetchall()
    today = date.today()
    target_day = today + timedelta(days=int(week)*7)
    monday = target_day - timedelta(days=target_day.weekday())
    start_time = time(hour=9)

    b_table = [0]*24
    for i in range(0, 24):
        b_table[i] = [0]*7
    for b in bookings:
        if client_id == None:
            db.cur.execute("SELECT * FROM clients WHERE client_id = %s", (b['client_id']))
        else:
            db.cur.execute("SELECT * FROM practitioners WHERE prac_id = %s", (b['prac_id']))
        personnel = db.cur.fetchall()[0]
        db.cur.execute("SELECT * FROM treatments WHERE treat_id = %s", (b['treat_id']))
        duration = db.cur.fetchall()[0]['duration']
        interval = intervals.closed(monday, monday + timedelta(days=7))
        if b['name'] in interval:
            j = (b['name'] - monday).days
            btime = (datetime.min + b['start']).time()
            if btime == start_time:
                i = 0
            else:
                bdtime = datetime.combine(today, btime)
                start_datetime = datetime.combine(today, start_time)
                i = int((bdtime - start_datetime).seconds/(30*60))
            if duration == 1.0:
                b_table[i][j] = [personnel['name'] + ' ' + personnel['surname'], b['booking_id'], 1]
                b_table[i+1][j] = ['filler', b['booking_id'], 0]
            else:
                b_table[i][j] = [personnel['name'] + ' ' + personnel['surname'], b['booking_id'], 0]
    times = [dt for dt in datetime_range(datetime.combine(today, time(hour=9)), \
             datetime.combine(today, time(hour=20, minute=55)), \
             timedelta(seconds=30*60))]
    times = [t.strftime('%-H:%M') for t in times]
    days = [monday.strftime('%a %d %b')]
    for d in range(1, 7):
        days.append((monday + timedelta(days=d)).strftime('%a %d %b'))
    return render_template('my_appointments_gui.html', booking=b_table, times=times, days=days, \
                           week=week)

@app.route('/my_appointments/notes/<booking_id>', methods=['GET', 'POST'])
@auth_required(level=2)
def appointment_notes(booking_id):
    db = Database()
    db.cur.execute("SELECT * FROM notes WHERE notes.booking_id = %s AND draft = 0" % booking_id)
    notes = db.cur.fetchall()
    res = db.list_table('notes')
    if 'add' in request.form:
        return redirect(url_for('appointment_notes_add', booking_id=booking_id))
    elif 'return' in request.form:
        return redirect(url_for('my_appointments_gui', week=0))
    return render_template('appointment_notes.html', notes=notes, col_type=res[1], \
                           named_keys=res[2])

@app.route('/my_appointments/notes/<booking_id>_add', methods=['GET', 'POST'])
@auth_required(level=2)
def appointment_notes_add(booking_id):
    db = Database()
    db.cur.execute("SELECT * FROM bookings WHERE booking_id = %s" % booking_id)
    bookings = db.cur.fetchall()[0]
    db.cur.execute("SELECT name, surname FROM clients WHERE client_id = %s" % bookings['client_id'])
    res = db.cur.fetchall()[0]
    client = res['name'] + ' ' + res['surname']
    db.cur.execute("SELECT * FROM notes WHERE booking_id = %s AND draft = 1" % booking_id)
    try:
        draft = db.cur.fetchall()[0]['note']
    except:
        draft = ''
    db.cur.execute("SELECT * FROM notes WHERE notes.client_id = %s AND draft = 0" \
                   % bookings['client_id'])
    notes = db.cur.fetchall()
    res = db.list_table('notes')
    if request.method == 'POST':
        if 'note_draft' in request.form:
            db.cur.execute("INSERT IGNORE INTO notes (note, image, timestamp, client_id, prac_id, \
                           booking_id, draft) VALUES(%s, NULL, NOW(), %s, %s, %s, 1)", \
                           (request.form['note_draft'], bookings['client_id'], \
                           bookings['prac_id'], booking_id))
            db.con.commit()
            flash('Draft saved')
            return redirect(url_for('appointment_notes', booking_id=booking_id))
        if 'note_final' in request.form:
            db.cur.execute("INSERT IGNORE INTO notes (note, image, timestamp, client_id, prac_id, \
                           booking_id, draft) VALUES(%s, %s, NOW(), %s, %s, %s, 0)", \
                           (request.form['note_final'], request.form['img'], \
                           bookings['client_id'], bookings['prac_id'], booking_id))
            db.con.commit()
            db.cur.execute("DELETE FROM notes WHERE draft = 1 AND booking_id = %s", booking_id)
            db.con.commit()
            return redirect(url_for('appointment_notes', booking_id=booking_id))
    return render_template('appointment_notes_add.html', bookings=bookings, client=client, \
                           draft=draft, notes=notes, col_type=res[1], named_keys=res[2])

@app.route('/invoice/<id_list>', methods=['GET', 'POST'])
@auth_required(level=2)
def invoice(id_list):
    id_list = ast.literal_eval(id_list)
    db = Database()
    total = 0
    bookings = []
    client = None
    for booking_id in id_list:
        db.cur.execute("SELECT * FROM bookings WHERE booking_id = %s", booking_id)
        booking = db.cur.fetchall()[0]
        db.cur.execute("SELECT name FROM treatments WHERE treat_id = %s", booking['treat_id'])
        treatment = db.cur.fetchall()[0]['name']
        if client is None:
            db.cur.execute("SELECT * FROM clients WHERE client_id = %s", booking['client_id'])
            res = db.cur.fetchall()[0]
            client = res['name'] + ' ' + res['surname']
            db.cur.execute("SELECT * FROM practitioners WHERE prac_id = %s", booking['prac_id'])
            res = db.cur.fetchall()[0]
            prac = res['name'] + ' ' + res['surname']
        bookings.append([treatment, booking['name'], booking['price']])
        total += booking['price']
    today = date.today()
    return render_template('invoice.html', bookings=bookings, client=client, prac=prac, \
                           today=today, total=total)

@app.route('/client_note', methods=['GET', 'POST'])
@auth_required(level=2)
def client_note():
    db = Database()
    db.cur.execute("SELECT * FROM clients")
    clients = db.cur.fetchall()
    if request.method == 'POST':
        return redirect(url_for('client_notes_view', client_id=request.form['client_id']))
    return render_template('client_note.html', clients=clients)

@app.route('/client_notes/<client_id>')
@auth_required(level=2)
def client_notes_view(client_id):
    db = Database()
    db.cur.execute("SELECT * FROM notes where notes.client_id = %s" % client_id)
    notes = db.cur.fetchall()
    res = db.list_table('notes')
    return render_template('client_notes_view.html', notes=notes, col_type=res[1], \
                           named_keys=res[2])

@app.route('/block_periods', methods=['GET', 'POST'])
@auth_required(level=2)
def block_periods():
    db = Database()
    db.cur.execute("SELECT prac_id from users WHERE email = %s", (session['email']))
    res = db.cur.fetchall()
    prac_id = res[0]['prac_id']
    db.cur.execute("SELECT * FROM blocked_periods where blocked_periods.prac_id = %s" \
                   % str(prac_id))
    blocked = db.cur.fetchall()
    res = db.list_table('blocked_periods')
    if request.method == 'POST':
        if 'submit' in request.form:
            db.cur.execute("INSERT IGNORE INTO blocked_periods (date, start, end, prac_id) \
                           VALUES(%s, %s, %s, %s)", (request.form['date'], request.form['start'], \
                           request.form['end'], str(prac_id)))
            db.con.commit()
            return redirect(url_for('block_periods'))
        elif 'delete' in request.form:
            try:
                db.cur.execute("DELETE FROM blocked_periods WHERE bp_id = %s" \
                               % request.form['delete'])
                db.con.commit()
            except:
                error = 'Error: this row cannot be deleted as another row \
                         in the table depends upon it.'
                return redirect(url_for('error', error=error))
            return redirect(url_for('block_periods'))
    return render_template('block_periods.html', blocked=blocked)

@app.route('/image')
def view_image():
    db = Database()
    db.cur.execute("SELECT image FROM notes WHERE note_id = 3")
    image = db.cur.fetchall()[0]['image']
    image = image[22:]
    img_io = BytesIO(b64decode(image))
    return send_file(img_io, mimetype='image/png');

@app.route('/pdf')
def pdf():
    return render_template('pdf.html')
