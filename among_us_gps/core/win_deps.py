"""
Centralizza l'import delle librerie Windows-specifiche e di OpenCV/PyAutoGUI.

Alcuni moduli (input simulato, scanner YOLO, OCR) funzionano solo su Windows
con l'eseguibile di Among Us in foreground. Gli import vengono tentati una
volta sola e il flag `WIN_OK` indica se l'ambiente è completo.

Il resto del codice importa da qui invece di ripetere try/except sparsi.
"""

WIN_OK = False

mss = None
win32gui = None
win32api = None
win32con = None
np = None
cv2 = None
pyautogui = None

try:
    import mss as _mss
    import win32gui as _win32gui
    import win32api as _win32api
    import win32con as _win32con
    import numpy as _np
    import cv2 as _cv2
    import pyautogui as _pyautogui
    _pyautogui.FAILSAFE = True
    _pyautogui.PAUSE = 0

    mss = _mss
    win32gui = _win32gui
    win32api = _win32api
    win32con = _win32con
    np = _np
    cv2 = _cv2
    pyautogui = _pyautogui
    WIN_OK = True
except Exception:
    WIN_OK = False
