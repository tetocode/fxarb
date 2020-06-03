import os
import tempfile


def is_posix():
    return os.name == 'posix'


def is_windows():
    return os.name == 'nt'


def get_home_dir():
    if is_posix():
        return os.environ['HOME']
    if is_windows():
        return os.environ['USERPROFILE']

def get_desktop_dir():
    return os.path.join(get_home_dir(), 'Desktop')

def get_temp_dir():
    return tempfile.gettempdir()
