from flask import render_template
from flask_mail import Message
from datetime import date, datetime, timedelta
from db.views import Database
from db import app, mail

def send_reminder():
    db = Database()
    db.cur.execute("SELECT * FROM bookings")
    bookings = db.cur.fetchall()
    clients = []
    today = date.today()
    for booking in bookings:
        if booking['name'] - today == timedelta(2):
            if booking['client_id'] not in clients:
                clients.append(booking['client_id'])
    for client_id in clients:
        d2 = (today + timedelta(2)).strftime('%Y-%m-%d')
        db.cur.execute("SELECT email FROM users WHERE client_id = %s", client_id)
        email = db.cur.fetchall()[0]['email']
        db.cur.execute("SELECT name FROM clients WHERE client_id = %s", client_id)
        name = db.cur.fetchall()[0]['name']
        db.cur.execute("SELECT * FROM bookings WHERE client_id = %s AND name = %s", \
                       (str(client_id), d2))
        res = db.cur.fetchall()[0]
        time = (datetime(1990, 1, 1) + res['start']).strftime('%-H:%M')
        dat = (today + timedelta(2)).strftime("%A %d %B")
        treat_id = res['treat_id']
        db.cur.execute("SELECT name FROM treatments WHERE treat_id = %s", treat_id)
        treatment = db.cur.fetchall()[0]['name']
        prac_id = res['prac_id']
        db.cur.execute("SELECT name FROM practitioners WHERE prac_id = %s", prac_id)
        prac = db.cur.fetchall()[0]['name']
        msg = Message("Booking reminder - Framework Livingston", \
                      sender=app.config.get('MAIL_USERNAME'), recipients=[email])
        with app.app_context():
            msg.html = render_template('reminder.html', name=name, treatment=treatment, \
                                    prac=prac, time=time, date=dat)
            mail.send(msg)
