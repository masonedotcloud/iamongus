"""
Input simulato Windows tramite ctypes + SendInput (scan-code).

Among Us non riconosce le pressioni inviate via PostMessage o SendKeys
perche' legge la tastiera con DirectInput; SendInput a livello scan-code
invece funziona. `KeyController` tiene traccia dei tasti correnti per
evitare di ripremere o di lasciarli "incollati".
"""

import ctypes


_SendInput = ctypes.windll.user32.SendInput
_PUL = ctypes.POINTER(ctypes.c_ulong)


class _KeyBdInput(ctypes.Structure):
    """Classe '_KeyBdInput'."""
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", _PUL)]


class _HardwareInput(ctypes.Structure):
    """Classe '_HardwareInput'."""
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_short),
                ("wParamH", ctypes.c_ushort)]


class _MouseInput(ctypes.Structure):
    """Classe '_MouseInput'."""
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", _PUL)]


class _InputI(ctypes.Union):
    """Classe '_InputI'."""
    _fields_ = [("ki", _KeyBdInput), ("mi", _MouseInput), ("hi", _HardwareInput)]


class _Input(ctypes.Structure):
    """Classe '_Input'."""
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


# Invia un evento tastiera a livello scan-code (DirectInput)
def _send_scan(code, keyup=False):
    """Invia scan."""
    extra = ctypes.c_ulong(0)
    flags = _KEYEVENTF_SCANCODE | (_KEYEVENTF_KEYUP if keyup else 0)
    ki = _KeyBdInput(0, code, flags, 0, ctypes.pointer(extra))
    ii = _InputI(); ii.ki = ki
    inp = _Input(ctypes.c_ulong(1), ii)
    _SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))


class KeyController:
    """Stato dei tasti tenuti premuti, con press/release idempotenti."""

    def __init__(self):
        """Inizializza l'istanza con i valori di default."""
        self.pressed = set()

    def press(self, key):
        """Preme un tasto via SendInput (scan-code)."""
        if key in self.pressed:
            return
        # Invia un evento tastiera a livello scan-code (DirectInput)
        _send_scan(SCAN_CODES[key], keyup=False)
        self.pressed.add(key)

    def release(self, key):
        """Rilascia un tasto via SendInput (scan-code)."""
        if key not in self.pressed:
            return
        # Invia un evento tastiera a livello scan-code (DirectInput)
        _send_scan(SCAN_CODES[key], keyup=True)
        self.pressed.discard(key)

    def release_all(self):
        """Rilascia tutti i tasti tenuti premuti."""
        for k in list(self.pressed):
            self.release(k)
