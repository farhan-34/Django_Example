import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pytests.settings')  # Replace 'your_project.settings' with your actual settings module

def pytest_configure():
    settings.DEBUG = False
    django.setup()
