"""
WSGI config for stok_sistemi project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import sys

# WeasyPrint için macOS library path
if sys.platform == 'darwin':
    homebrew_lib_path = '/opt/homebrew/lib'
    if os.path.exists(homebrew_lib_path):
        current_dyld = os.environ.get('DYLD_LIBRARY_PATH', '')
        if homebrew_lib_path not in current_dyld:
            os.environ['DYLD_LIBRARY_PATH'] = f"{homebrew_lib_path}:{current_dyld}" if current_dyld else homebrew_lib_path

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stok_sistemi.settings')

application = get_wsgi_application()
