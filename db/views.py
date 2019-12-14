from flask import render_template, redirect, url_for, request, session, flash
from flask_mail import Message
import pymysql
import hashlib
from functools import wraps
from datetime import datetime, timedelta, date, time
import ast
import random
import string

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
        password = self.cur.fetchall()[0]['password']
        if password_in == password:
            session['msg'] = 'Signed in.'
            session['email'] = email
            self.cur.execute("SELECT access_lvl FROM users WHERE email = %s", (email, ))
            session['access_lvl'] = self.cur.fetchall()[0]['access_lvl']
            self.cur.execute("SELECT client_id FROM users WHERE email = %s", (email, ))
            client_id = self.cur.fetchall()[0]['client_id']
            if client_id != None:
                session['client_id'] = client_id
        else:
            flash('Email or password incorrect. Please try again.')

def auth_required(level=2):
    def callable(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not 'access_lvl' in session:
                session['error'] = 'Login is required to continue.'
                return redirect(url_for('login', next=request.endpoint))
            elif session['access_lvl'] == -1:
                session['error'] = 'Account registration still needs to be \
                                    completed. Please check your emails.'
                return redirect(url_for('index', next=request.endpoint))
            elif session['access_lvl'] < level:
                session['error'] = 'User access level insufficient.'
                return redirect(url_for('login', next=request.endpoint))
            return func(*args, **kwargs)
        return wrapper
    return callable

@app.route('/')
def index():
    if 'msg' in session:
        msg = session['msg']
        session.pop('msg', None)
    else:
        msg = None
    return render_template('index.html', msg=msg, session=session)

@app.route('/logout')
def logout():
    session.pop('email', None)
    session.pop('access_lvl', None)
    session.pop('client_id', None)
    session['msg'] = "You have logged out."
    return redirect(request.args.get('next') or url_for('index'))

@app.route('/database')
@auth_required(level=2)
def database():
    db = Database()
    db.cur.execute("SHOW TABLES")
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

@app.route('/error/<error>', methods=['GET', 'POST'])
def error(error):
    if request.method == 'POST':
        return redirect(url_for('index'))
    return render_template('error.html', error=error)

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
            db.cur.execute("INSERT IGNORE INTO %s (%s) VALUES (%s);" % (table, fieldnames, values))
            db.con.commit()
            return redirect(url_for('tables', table=table))
    return render_template('tables_add.html', result=res[0], col_type=res[1], named_keys=res[2])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'error' in session:
        msg = session['error']
        session.pop('error', None)
    else:
        msg = None
    db = Database()
    if request.method == 'POST':
        if request.form['next'] == 'login':
            db.authenticate(request.form['email'], request.form['password'])
            return redirect(request.args.get('next') or url_for('index'))
        if request.form['next'] == 'create':
            return redirect(url_for('create_account'))
    return render_template('login.html', msg=msg)

@app.route('/create_account', methods=['GET', 'POST'])
def create_account():
    if 'error' in session:
        msg = session['error']
        session.pop('error', None)
    else:
        msg = None
    db = Database()
    if request.method == 'POST':
        if not request.form['password'] == request.form['password_confirm']:
            error = 'Passwords do not match'
            session['error'] = error
            return redirect(url_for('create_account'))
        else:
            password = request.form['password']
            email = request.form['email']
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
                    forms[f] = None
            # insert new details into db
            db.cur.execute("INSERT IGNORE INTO clients (name, surname, phone_1, phone_2, \
                           address_1, address_2, address_3, city, county, postcode) \
                           VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", \
                           (forms['name'], forms['surname'], forms['phone_1'], \
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
            session['msg'] = "An email has been sent to %s." % email
            return redirect(request.args.get('next') or url_for('index'))
    return render_template('create_account.html', msg=msg)

@app.route('/email_confirmation/<key>')
def email_confirmation(key):
    db = Database()
    db.cur.execute("UPDATE users SET access_lvl = 0, auth_key = NULL WHERE auth_key = %s", (key, ))
    db.con.commit()
    return render_template('email_confirmation.html')

@app.route('/treatments', methods=['GET', 'POST'])
def treatments():
    db = Database()
    # fetch list of treatments
    db.cur.execute("SELECT name FROM treatments")
    treatments = [entry['name'] for entry in db.cur.fetchall()]
    # create treatment links
    if request.method == 'POST':
        session['treatment'] = request.form['type']
        db.cur.execute("SELECT duration, price FROM treatments where \
                       name = %s", (session['treatment'], ))
        res = [[entry['duration'], entry['price']] for entry in db.cur.fetchall()][0]
        session['duration'] = str(res[0])
        session['price'] = str(res[1])
        return redirect(url_for('dates'))
    return render_template('treatments.html', treatments=treatments)

@app.route('/dates', methods=['GET', 'POST'])
def dates():
    # collect list of dates for next month
    today = date.today()
    date_range = [today]
    for n in range(1, 28):
        date_range.append(today + timedelta(days=n))
    # format it nicely
    date_range_f = [d.strftime("%A %d %B") for d in date_range]

    # reobtain original date from user input and store it
    if request.method == 'POST':
        for n in range(0, 28):
            if date_range_f[n] == request.form['date']:
                day = n
        session['date'] = date_range[day].strftime('%Y-%m-%d')
        session['datef'] = date_range[day].strftime('%A %d %B')
        return redirect(url_for('booking'))
    return render_template('dates.html', date_range=date_range_f)

def datetime_range(start, end, delta):
    """Generator function for time range"""
    current = start
    while current < end:
        yield current
        current += delta

def interval_conversion(list, avail=False):
    """Converts time data into interval format"""
    import intervals as intervals
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

@app.route('/booking', methods=['GET', 'POST'])
def booking():
    error = None
    db = Database()
    # fetch list of availabilities
    db.cur.execute("SELECT date, start, end, prac_id FROM avails")
    avails = [[entry['date'], (datetime.min + entry['start']).time(),
                              (datetime.min + entry['end']).time(),
               entry['prac_id']] for entry in db.cur.fetchall()]
    # fetch list of existing bookings
    db.cur.execute("SELECT name, start, end, prac_id FROM bookings")
    bookings = [[entry['name'], (datetime.min + entry['start']).time(),
                                (datetime.min + entry['end']).time(),
                 entry['prac_id']] for entry in db.cur.fetchall()]

    # filter out avails for other dates
    valid_avails = []
    for a in avails:
        if session['date'] == a[0].strftime('%Y-%m-%d'):
            valid_avails.append(a)
    if valid_avails == []:
        error = "Sorry no slots available. Please select another date."
        return render_template('booking.html', error=error)
    # make the time periods into intervals instead
    avails_i = interval_conversion(valid_avails, avail=True)
    bookings_i = interval_conversion(bookings)
    # subtract booked periods from available ones
    for a in avails_i:
        for b in bookings_i:
            a[0] = a[0] - b[0]

    # generate list of all possible times in a day
    time_slots = [dt for dt in
        datetime_range(datetime.combine(valid_avails[0][0], time(hour=9)),
                       datetime.combine(valid_avails[0][0], time(hour=17, minute=55)),
                       timedelta(minutes=30))]
    # find available slots
    for i, t in enumerate(time_slots):
        pracs = []
        for avail in avails_i:
            if t in avail[0]:
                pracs.append(avail[1])
        time_slots[i] = [t.strftime('%-H:%M'), pracs]

    if request.method == 'POST':
        res = ast.literal_eval(request.form['time_slot'])
        session['time_slot'] = res[0]
        session['end'] = (datetime(1990,1,1, int(res[0].split(':')[0]), \
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

    return render_template('booking.html', time_slots=time_slots)

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
            room_id = session['prac_id'] # assumed each prac has own room for now
            notes = 'NULL' # needs to be set up
            db.cur.execute("INSERT IGNORE INTO bookings (prac_id, client_id, room_id, name, \
                           start, end, notes, price) VALUES(" + str(session['prac_id']) \
                           + ", " + str(client_id) + ", " + str(room_id) + ", '" \
                           + session['date'] + "', '" + session['time_slot'] + "', '" \
                           + session['end'] + "', " + notes + ", " + session['price'] + ");")
            db.con.commit()
            return redirect(url_for('completed'))
        elif request.form['answer'] == "cancel":
            return redirect(url_for('index'))
    return render_template('confirmation.html', session=session)

@app.route('/client_choice', methods=['GET', 'POST'])
@auth_required(level=2)
def client_choice():
    db = Database()
    db.cur.execute("SELECT name, surname, client_id FROM clients")
    res = db.cur.fetchall()
    clients = [[entry['name'] + ' '  + entry['surname'], entry['client_id']] for entry in res]
    if request.method == 'POST':
        res = ast.literal_eval(request.form['type'])
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
    db.cur.execute("SELECT client_id, prac_id from users WHERE email = %s", (session['email']))
    res = db.cur.fetchall()
    client_id = res[0]['client_id']
    prac_id = res[0]['prac_id']
    if client_id == None:
        db.cur.execute("SELECT * FROM bookings WHERE prac_id = %s" % str(prac_id))
    else:
        db.cur.execute("SELECT * FROM bookings WHERE client_id = %s" % str(client_id))
    bookings = db.cur.fetchall()
    res = db.list_table('bookings')
    if request.method == 'POST':
        if 'delete' in request.form:
            # delete using the primary key (which is identified by 'auto')
            col_type = res[1]
            auto_field = [field for field in col_type if col_type[field] == 'auto'][0]
            try:
                db.cur.execute("DELETE FROM %s WHERE %s = %s" % \
                               ('bookings', auto_field, request.form['delete']))
                db.con.commit()
            except:
                error = 'Error: this row cannot be deleted as another row \
                         in the table depends upon it.'
                return redirect(url_for('error', error=error))
            return redirect(url_for('my_appointments'))
    return render_template('my_appointments.html', bookings=bookings, col_type=res[1], \
                           named_keys=res[2], access_lvl=session['access_lvl'])
