import os

SECRET_KEY = b'5d6d846f35538d4554a51a1d27bd11bb'

# email server
MAIL_SERVER = 'smtp.googlemail.com'
MAIL_PORT = 465
MAIL_USE_TLS = False
MAIL_USE_SSL = True
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

# testing
#TESTING = True

# administrator list
# ADMINS = ['your-gmail-username@gmail.com']
