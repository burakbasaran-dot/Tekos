#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# WeasyPrint için macOS library path
if sys.platform == 'darwin':
    homebrew_lib_path = '/opt/homebrew/lib'
    if os.path.exists(homebrew_lib_path):
        current_dyld = os.environ.get('DYLD_LIBRARY_PATH', '')
        if homebrew_lib_path not in current_dyld:
            os.environ['DYLD_LIBRARY_PATH'] = f"{homebrew_lib_path}:{current_dyld}" if current_dyld else homebrew_lib_path


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stok_sistemi.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
