"""
Facade degli import condivisi dai mixin di GPSVisualizerPro.

I mixin contengono metodi che originariamente erano nel monolite ``main.py``
e usano molti simboli "di contesto" (dpg, GPSConfig, Colors, np, ecc.).
Per evitare di ripetere gli stessi import in 15 file, ognuno fa::

    from ._imports import *

Cosi' i singoli mixin restano focalizzati sui metodi veri e propri.

Il vantaggio in piu': se domani aggiungiamo una dipendenza globale (es. un
nuovo manager o una nuova costante), basta aggiungerla qui e tutti i mixin
la vedono. Se la nuova dipendenza serve a uno solo, conviene importarla nel
mixin che la usa (per limitare l'accoppiamento).
"""

import atexit
import json
import math
import os
import random
import subprocess
import sys
import threading
import time

import dearpygui.dearpygui as dpg

from ...core.config import GPSConfig, Colors
from ...core.geometry import (
    hex_to_rgba as _hex_to_rgba,
    get_client_rect,
    point_in_polygon,
)
from ...core import stop_flag
from ...core.win_deps import (
    WIN_OK as _WIN_OK,
    mss,
    np,
    pyautogui,
    win32api,
    win32gui,
)
from ...io_input import KeyController, SCAN_CODES
from ...io_input.key_controller import _send_scan
from ...managers import PoiManager, TaskManager, ZoneManager
from ...game_io import AmongUsMemoryReader, AmongUsTaskReader
from ...pathfinding import Pathfinder


__all__ = [
    # stdlib
    "atexit", "json", "math", "os", "random", "subprocess",
    "sys", "threading", "time",
    # third-party / GUI
    "dpg",
    # config + geometry
    "GPSConfig", "Colors",
    "_hex_to_rgba", "get_client_rect", "point_in_polygon",
    # stato globale
    "stop_flag",
    # win deps
    "_WIN_OK", "mss", "np", "pyautogui",
    "win32api", "win32gui",
    # input
    "KeyController", "SCAN_CODES", "_send_scan",
    # manager / readers / pathfinder
    "PoiManager", "TaskManager", "ZoneManager",
    "AmongUsMemoryReader", "AmongUsTaskReader",
    "Pathfinder",
]
