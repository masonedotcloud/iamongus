"""
Input simulato Windows tramite ctypes + SendInput (scan-code).

Among Us non riconosce le pressioni inviate via PostMessage o SendKeys
perché legge la tastiera con DirectInput; SendInput a livello scan-code
invece funziona. `KeyController` tiene traccia dei tasti correnti per
evitare di ripremere o di lasciarli "incollati".
"""

import ctypes


_SendInput = ctypes.windll.user32.SendInput
_PUL = ctypes.POINTER(ctypes.c_ulong)


class _KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", _PUL)]


class _HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_short),
                ("wParamH", ctypes.c_ushort)]


class _MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", _PUL)]


class _InputI(ctypes.Union):
    _fields_ = [("ki", _KeyBdInput), ("mi", _MouseInput), ("hi", _HardwareInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", _InputI)]


_KEYEVENTF_SCANCODE = 0x0008
_KEYEVENTF_KEYUP    = 0x0002

# Scan code per i tasti effettivamente usati dal bot
SCAN_CODES = {
    'W': 0x11,
    'A': 0x1E,
    'S': 0x1F,
    'D': 0x20,
    'SPACE': 0x39,
}


def _send_scan(code, keyup=False):
    extra = ctypes.c_ulong(0)
    flags = _KEYEVENTF_SCANCODE | (_KEYEVENTF_KEYUP if keyup else 0)
    ki = _KeyBdInput(0, code, flags, 0, ctypes.pointer(extra))
    ii = _InputI(); ii.ki = ki
    inp = _Input(ctypes.c_ulong(1), ii)
    _SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))


class KeyController:
    """Stato dei tasti tenuti premuti, con press/release idempotenti."""

    def __init__(self):
        self.pressed = set()

    def press(self, key):
        if key in self.pressed:
            return
        _send_scan(SCAN_CODES[key], keyup=False)
        self.pressed.add(key)

    def release(self, key):
        if key not in self.pressed:
            return
        _send_scan(SCAN_CODES[key], keyup=True)
        self.pressed.discard(key)

    def release_all(self):
        for k in list(self.pressed):
            self.release(k)
