"""
Import centralizzati delle dipendenze Windows e di computer vision.

Alcuni moduli (input simulato, scanner YOLO, OCR, lettura RAM via pymem)
girano solo su Windows con l'eseguibile di Among Us in foreground.
Per non duplicare i ``try/except`` in tutto il codice, il package li tenta
una volta sola QUI ed espone:

- ``WIN_OK``: ``True`` se TUTTI gli import sono andati a buon fine
- ``mss``, ``win32gui``, ``win32api``, ``win32con``, ``np``, ``cv2``,
  ``pyautogui``: i moduli stessi (oppure ``None`` se import fallito)

Il resto del codice importa da qui::

    from among_us_ai.core import win_deps
    if not win_deps.WIN_OK:
        ...
    win_deps.pyautogui.click(...)
"""

# Stato globale: True solo se l'intero blocco try ha avuto successo.
WIN_OK = False

# Riferimenti ai moduli (rimangono None se l'import fallisce).
# Tenerli a livello modulo permette gli accessi del tipo
# `win_deps.win32gui.GetForegroundWindow()` senza dover ri-importare.
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

    # Configurazione PyAutoGUI per il bot:
    # - FAILSAFE=True: muovere il mouse nell'angolo alto-sx interrompe lo
    #   script (utile come "killswitch" durante i test).
    # - PAUSE=0: niente pausa automatica fra una chiamata PyAutoGUI e
    #   l'altra (gestiamo noi i timing nel motore).
    _pyautogui.FAILSAFE = True
    _pyautogui.PAUSE = 0

    # Espone i moduli all'esterno solo se tutto l'import e' andato.
    mss = _mss
    win32gui = _win32gui
    win32api = _win32api
    win32con = _win32con
    np = _np
    cv2 = _cv2
    pyautogui = _pyautogui
    WIN_OK = True
except Exception:
    # Anche un solo import fallito invalida tutto il blocco: i moduli
    # restano None e WIN_OK=False. Il chiamante puo' decidere se proseguire
    # in modalita' degradata o terminare con un messaggio chiaro.
    WIN_OK = False
