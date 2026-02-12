"""
Facade degli import condivisi dai mixin di TaskActionEditor.

Stesso pattern di ``ui/mixins/_imports.py``: ogni mixin fa::

    from ._imports import *

per ottenere tutti i simboli "di contesto" usati dall'editor.
"""

import math
import threading
import time

import dearpygui.dearpygui as dpg

from ...core.config import MAX_PREVIEW_W, MAX_PREVIEW_H
from ...core.geometry import get_client_rect, point_in_polygon
from ...core import stop_flag
from ...core.win_deps import (
    WIN_OK as _WIN_OK,
    cv2,
    mss,
    np,
    pyautogui,
    win32api,
    win32con,
    win32gui,
)
from ...execution.runtime import esegui_azioni, _extract_pure_shape


__all__ = [
    # stdlib
    "math", "threading", "time",
    # GUI
    "dpg",
    # config / geometry
    "MAX_PREVIEW_W", "MAX_PREVIEW_H",
    "get_client_rect", "point_in_polygon",
    # stato globale
    "stop_flag",
    # win deps
    "_WIN_OK", "cv2", "mss", "np", "pyautogui",
    "win32api", "win32con", "win32gui",
    # runtime
    "esegui_azioni", "_extract_pure_shape",
]
