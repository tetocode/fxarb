import os

import pytest

from pyfxnode.window import Window


@pytest.mark.skipIf('os.name != \'posix\'')
def test_image_node():
    assert os.name == 'posix'
    for win in Window.iter_window():
        print(win.get_title())
        print(win.get_position())
        print(win.get_screen_shot())
