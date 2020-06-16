import os

SECRET_KEY = b'5d6d846f35538d4554a51a1d27bd11bb'

# email server
MAIL_SERVER = 'smtp.googlemail.com'
MAIL_PORT = 465
MAIL_USE_TLS = False
MAIL_USE_SSL = True
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

# mysql database
DB_PASS = os.environ.get('DBPASS')
DB_IP = os.environ.get('DB_IP')
DB_USER = os.environ.get('DB_USER')

# web database
WEB_ID = os.environ.get('WEB_ID')
WEB_PASS = os.environ.get('WEB_PASS')

# testing
#TESTING = True

# administrator list
# ADMINS = ['your-gmail-username@gmail.com']
