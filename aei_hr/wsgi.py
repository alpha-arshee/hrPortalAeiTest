"""
WSGI config for aei_hr project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aei_hr.settings')

application = get_wsgi_application()