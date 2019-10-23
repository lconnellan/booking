from flask import Flask, render_template, redirect, url_for, request, session
import pymysql
import hashlib
from functools import wraps

app = Flask(__name__)

app.secret_key = b'5d6d846f35538d4554a51a1d27bd11bb'

class Database:
    def __init__(self):
        host = '192.168.251.141'
        user = "lloyd"
        password = "cr1cket"
        db = "booking"
        self.con = pymysql.connect(host=host, user=user, password=password, db=db, cursorclass=pymysql.cursors.DictCursor)
        self.cur = self.con.cursor()
    def list_category(self, category):
        self.cur.execute("SELECT * FROM " + category + " LIMIT 50")
        result = self.cur.fetchall()
        return result

class User(Database):
    def __init__(self):
        Database.__init__(self)
        self.username = 'user'
        self.access_lvl = 0
    def authenticate(self, username_in, password_in):
        self.cur.execute("SELECT password FROM users WHERE username = '" + username_in + "'")
        password = self.cur.fetchall()[0]['password']
        if password_in == password:
            print('Signed in.')
            session['username'] = username_in
            self.cur.execute("SELECT access_lvl FROM users WHERE username = '" + username_in + "'")
            self.access_lvl = self.cur.fetchall()[0]['access_lvl']
            session['access_lvl'] = self.access_lvl
        else:
            print('Username or password incorrect. Please try again.')

def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        print(session['access_lvl'])
        if session['access_lvl'] == None:
            print('Login is required to continue')
            return redirect(url_for('login'))
        if session['access_lvl'] != 2:
            print('User access level insufficient')
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    return wrapper

@app.route('/clients')
@admin_required
def clients():
    db = Database()
    res = db.list_category('clients')
    return render_template('clients.html', result=res, content_type='application/json')

@app.route('/practitioners')
@admin_required
def practitioners():
    db = Database()
    res = db.list_category('practitioners')
    return render_template('practitioners.html', result=res, content_type='application/json')

# Route for handling the login page logic
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    user = User()
    if request.method == 'POST':
        username = request.form['username']
        m = hashlib.md5()
        m.update(bytes(request.form['password'], encoding='utf-8'))
        password = m.hexdigest()
        user.authenticate(username, password)
        print(user.access_lvl)
        if user.access_lvl == 2:
            return redirect(url_for('index'))
        else:
            error = 'Access level not sufficient.'
    return render_template('login.html', error=error)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if request.form['category'] == "clients":
            return redirect(url_for('clients'))
        elif request.form['category'] == "practitioners":
            return redirect(url_for('practitioners'))
    return render_template('index.html')
