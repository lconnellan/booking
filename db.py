from flask import Flask, render_template, redirect, url_for, request, session
import pymysql
import hashlib
from functools import wraps
from datetime import datetime, timedelta, date, time
import ast

app = Flask(__name__)

app.secret_key = b'5d6d846f35538d4554a51a1d27bd11bb'

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
        self.cur.execute("SELECT * FROM " + table + " LIMIT 50")
        result = self.cur.fetchall()
        self.cur.execute("SHOW COLUMNS FROM " + table)
        columns = self.cur.fetchall()
        column_type = {}
        for col in columns:
            if col['Extra'] == 'auto_increment':
                column_type[col['Field']] = 'auto'
            elif col['Type'] in ['date', 'time']:
                column_type[col['Field']] = 'str'
            elif 'varchar' in col['Type']:
                column_type[col['Field']] = 'str'
            else:
                column_type[col['Field']] = 'num'
        return result, column_type
    def list_tables(self):
        self.cur.execute("SHOW TABLES")
        result = self.cur.fetchall()
        return result
    def authenticate(self, username_in, password_in):
        """Hash password and check versus stored user/pass in db"""
        m = hashlib.md5()
        m.update(bytes(password_in, encoding='utf-8'))
        password_in = m.hexdigest()
        # fetch password from db
        self.cur.execute("SELECT password FROM users WHERE username = '" + username_in + "'")
        password = self.cur.fetchall()[0]['password']
        if password_in == password:
            print('Signed in.')
            session['username'] = username_in
            self.cur.execute("SELECT access_lvl FROM users WHERE username = '" + username_in + "'")
            session['access_lvl'] = self.cur.fetchall()[0]['access_lvl']
        else:
            print('Username or password incorrect. Please try again.')

def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not 'access_lvl' in session:
            print('Login is required to continue')
            return redirect(url_for('login', next=request.endpoint))
        if session['access_lvl'] != 2:
            print('User access level insufficient')
            return redirect(url_for('login', next=request.endpoint))
        return func(*args, **kwargs)
    return wrapper

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if request.form['category'] == "logout":
            session.pop('username', None)
            session.pop('access_lvl', None)
            msg = "You have logged out."
            return render_template('index.html', message=msg, session=session)
    return render_template('index.html', session=session)

@app.route('/database')
@admin_required
def database():
    db = Database()
    res = db.list_tables()
    return render_template('database.html', result=res)

@app.route('/database/<table>', methods=['GET', 'POST'])
@admin_required
def tables(table):
    db = Database()
    res, col_type = db.list_table(table)
    if request.method == 'POST':
        if 'add' in request.form:
            return redirect(url_for('tables_add', table=table))
        elif 'delete' in request.form:
            auto_field = [field for field in col_type if col_type[field] == 'auto'][0]
            try:
                db.cur.execute("DELETE FROM " + table + " WHERE " + auto_field + \
                               " = " + request.form['delete'])
                db.con.commit()
            except:
                error = 'Error: this row cannot be deleted as another row \
                         in the table depends upon it.'
                return redirect(url_for('error', error=error))
            return redirect(url_for('tables', table=table))
    return render_template('tables.html', result=res, col_type=col_type)

@app.route('/error/<error>', methods=['GET', 'POST'])
def error(error):
    if request.method == 'POST':
        return redirect(url_for('index'))
    return render_template('error.html', error=error)

@app.route('/database/<table>_add', methods=['GET', 'POST'])
@admin_required
def tables_add(table):
    db = Database()
    res, col_type = db.list_table(table)
    if request.method == 'POST':
        if request.form['submit'] == 'yes':
            first = True
            for fieldname, value in request.form.items():
                if fieldname != 'submit':
                    if col_type[fieldname[:-1]]:
                        value = "'" + value + "'"
                    if first:
                        fieldnames = fieldname[:-1]
                        values = value
                        first = False
                    else:
                        fieldnames += ', ' + fieldname[:-1]
                        values += ', ' + value
            db.cur.execute("INSERT IGNORE INTO " + table + "(" + fieldnames \
                           + ") VALUES(" + values + ");")
            db.con.commit()
            res = db.list_table(table)[0]
            return redirect(url_for('tables', table=table, col_type=col_type))
    return render_template('tables_add.html', result=res, col_type=col_type)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Route for handling the login page logic"""
    error = None
    db = Database()
    if request.method == 'POST':
        db.authenticate(request.form['username'], request.form['password'])
        return redirect(request.args.get('next') or url_for('index'))
    return render_template('login.html', error=error)

@app.route('/treatments', methods=['GET', 'POST'])
def treatments():
    db = Database()
    # fetch list of treatments
    db.cur.execute("SELECT descr FROM treatments")
    treatments = [entry['descr'] for entry in db.cur.fetchall()]
    # create treatment links
    if request.method == 'POST':
        session['treatment'] = request.form['type']
        db.cur.execute('SELECT duration, price FROM treatments where \
                       descr = "' + session['treatment'] + '"')
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
    db.cur.execute("SELECT date, start, end, prac_id FROM bookings")
    bookings = [[entry['date'], (datetime.min + entry['start']).time(),
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
                           int(res[0].split(':')[1])) \
                         + timedelta(hours=int(session['duration'].split('.')[0]), \
                           minutes=int(session['duration'].split('.')[1]))).strftime('%-H:%M')
        # fetch list of practitioners
        pracs = []
        for prac_id in res[1]:
            db.cur.execute("SELECT first_name, surname FROM practitioners \
                           WHERE prac_id = " + str(prac_id))
            pracs.append([[entry['first_name'] + ' ' + entry['surname'] \
                         for entry in db.cur.fetchall()][0], prac_id])
        session['pracs'] = pracs
        return redirect(url_for('practitioner_choice'))

    return render_template('booking.html', time_slots=time_slots)


@app.route('/practitioner_choice', methods=['GET', 'POST'])
def practitioner_choice():
    if request.method == 'POST':
        res = ast.literal_eval(request.form['type'])
        session['prac'] = res[0]
        session['prac_id'] = res[1]
        return redirect(url_for('confirmation'))
    return render_template('practitioner_choice.html', pracs=session['pracs'])

@app.route('/confirmation', methods=['GET', 'POST'])
def confirmation():
    if request.method == 'POST':
        if request.form['answer'] == "proceed":
            return redirect(url_for('completed'))
        elif request.form['answer'] == "cancel":
            return redirect(url_for('index'))
    return render_template('confirmation.html', session=session)

@app.route('/completed', methods=['GET', 'POST'])
def completed():
    if request.method == 'POST':
        db = Database()
        client_id = '1' # needs to be set up
        room_id = session['prac_id'] # assumed each prac has own room for now
        notes = 'NULL' # needs to be set up
        db.cur.execute("INSERT IGNORE INTO bookings (prac_id, client_id, room_id, date, \
                       start, end, notes, price) VALUES(" + str(session['prac_id']) \
                       + ", " + str(client_id) + ", " + str(room_id) + ", '" \
                       + session['date'] + "', '" + session['time_slot'] + "', '" \
                       + session['end'] + "', " + notes + ", " + session['price'] + ");")
        db.con.commit()
        if request.form['type'] == "return":
            return redirect(url_for('index'))
    return render_template('completed.html')

@app.route('/styles')
def styles():
    return render_template('styles.css', content_type='application/json')