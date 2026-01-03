from os import getenv
from dotenv import load_dotenv

load_dotenv('ppfenv')

workers = int(getenv('GUNICORN_PROCESSES', '2'))
threads = int(getenv('GUNICORN_THREADS', '4'))

# timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))

g_bind = getenv('GUNICORN_BIND', '0.0.0.0:8080')
bind = getenv('PPF_BIND', g_bind)

forwarded_allow_ips = '*'

secure_scheme_headers = { 'X-Forwarded-Proto': 'https' }
