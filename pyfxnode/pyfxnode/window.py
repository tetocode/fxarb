import os
from abc import ABC, abstractmethod
from typing import Tuple, Iterator

import PIL
from PIL.Image import Image


class _Window(ABC):
    def __init__(self, window):
        self._window = window

    @abstractmethod
    def get_title(self) -> str:
        pass

    @abstractmethod
    def get_position(self) -> Tuple[int, int, int, int]:
        pass

    @abstractmethod
    def get_screen_shot(self, x: int = None, y: int = None, width: int = None, height: int = None) -> Image:
        pass

    @classmethod
    @abstractmethod
    def iter_window(cls) -> Iterator['_Window']:
        pass


if os.name == 'posix':
    import ewmh
    import pyautogui


    class Window(_Window):
        def get_title(self) -> str:
            return '{}:{}'.format(self._window.get_wm_class(), self._window.get_wm_name())

        def get_position(self) -> Tuple[int, int, int, int]:
            data = getattr(self._window.get_geometry(), '_data')
            return data['x'], data['y'], data['width'], data['height']

        def get_screen_shot(self, x: int = None, y: int = None, width: int = None, height: int = None) -> Image:
            position = self.get_position()
            x = x or 0
            y = y or 0
            width = width or position[2]
            if width > position[2]:
                width = position[2]
            height = height or position[3]
            if height > position[3]:
                height = position[3]
            return pyautogui.screenshot(region=(x, y, width, height))

        @classmethod
        def iter_window(cls) -> Iterator['_Window']:
            for win in ewmh.EWMH().getClientList():
                yield Window(win)
else:
    import win32gui
    import win32ui
    import win32con
    import ctypes


    class Window(_Window):
        def get_title(self) -> str:
            return win32gui.GetWindowText(self._window)

        def get_position(self) -> Tuple[int, int, int, int]:
            hwnd = self._window
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            return left, top, right - left, bottom - top

        def get_screen_shot(self, x: int = None, y: int = None, width: int = None, height: int = None) -> Image:
            x = x or 0
            y = y or 0
            hwnd = self._window
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            if not width:
                width = right - left
            if not height:
                height = bottom - top
            hwnd_dc = win32gui.GetWindowDC(hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            save_dc.SetWindowOrg((0, 0))  # 13, 151))
            save_bit_map = win32ui.CreateBitmap()

            save_bit_map.CreateCompatibleBitmap(mfc_dc, width, height)  # 287, 76)
            save_dc.SelectObject(save_bit_map)
            #    result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 0)
            win32gui.BitBlt(save_dc.GetSafeHdc(), 0, 0, width, height, hwnd_dc, x, y, win32con.SRCCOPY)

            bmp_info = save_bit_map.GetInfo()
            bmp_str = save_bit_map.GetBitmapBits(True)
            im = PIL.Image.frombuffer(
                'RGB',
                (bmp_info['bmWidth'], bmp_info['bmHeight']),
                bmp_str, 'raw', 'BGRX', 0, 1)

            win32gui.DeleteObject(save_bit_map.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)
            return im

        @classmethod
        def iter_window(cls) -> Iterator['_Window']:
            is_window_visible = ctypes.windll.user32.IsWindowVisible
            handles = []

            def callback(hwnd, *_):
                nonlocal handles
                handles.append(hwnd)

            win32gui.EnumWindows(callback, None)
            for handle in handles:
                if is_window_visible(handle):
                    yield Window(handle)
