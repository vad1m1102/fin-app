import sys
import os

# Шлях до каталогу з проєктом на PythonAnywhere
path = '/home/vadim1102/fin-app'
if path not in sys.path:
    sys.path.insert(0, path)

from flask_app import app as application
