"""
Input simulato Windows tramite ctypes + SendInput a livello scancode.

Among Us legge la tastiera con DirectInput: messaggi inviati via
``PostMessage`` o ``SendKeys`` (livello applicazione) vengono ignorati.
``SendInput`` con flag ``KEYEVENTF_SCANCODE`` invece passa attraverso lo
stack DirectInput e funziona correttamente.

:class:`KeyController` mantiene il set dei tasti correntemente premuti per
evitare di ripremere uno stesso tasto (no-op) o lasciarlo "incollato" se
non rilasciato (release_all all'uscita).
"""

import ctypes


# Bridge alla API Win32 ``SendInput`` per inviare input sintetico.
_SendInput = ctypes.windll.user32.SendInput

# Tipo helper: puntatore a unsigned long (per ``dwExtraInfo`` delle struct).
_PUL = ctypes.POINTER(ctypes.c_ulong)


# ---------------------------------------------------------------------------
# Strutture ctypes equivalenti alle struct C usate da SendInput.
# Layout dei campi e ordine devono matchare esattamente la dichiarazione
# in WinUser.h. Vedere MSDN > SendInput > INPUT structure.
# ---------------------------------------------------------------------------

class _KeyBdInput(ctypes.Structure):
    """Mirror della ``KEYBDINPUT`` di WinUser.h (evento tastiera)."""
    _fields_ = [("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", _PUL)]


class _HardwareInput(ctypes.Structure):
    """Mirror della ``HARDWAREINPUT`` (non usata ma richiesta dalla union)."""
    _fields_ = [("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_short),
                ("wParamH", ctypes.c_ushort)]


class _MouseInput(ctypes.Structure):
    """Mirror della ``MOUSEINPUT`` (non usata ma richiesta dalla union)."""
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", _PUL)]


class _InputI(ctypes.Union):
    """Union che contiene UNA delle 3 strutture sopra (tipo discriminato da ``_Input.type``)."""
    _fields_ = [("ki", _KeyBdInput),
                ("mi", _MouseInput),
                ("hi", _HardwareInput)]


class _Input(ctypes.Structure):
    """Struttura ``INPUT`` di WinUser.h che SendInput accetta in array."""
    _fields_ = [("type", ctypes.c_ulong),
                ("ii", _InputI)]


# Flag per le KEYBDINPUT (da WinUser.h):
_KEYEVENTF_SCANCODE = 0x0008   # wScan e' uno scancode hardware (non un VK)
_KEYEVENTF_KEYUP    = 0x0002   # release del tasto (senza il flag = press)


# Scancode dei tasti realmente usati dal bot (movimento, conferma, annulla).
# Riferimento: PS/2 Set 1, sezione "Make codes" della tabella standard.
SCAN_CODES = {
    'W': 0x11,
    'A': 0x1E,
    'S': 0x1F,
    'D': 0x20,
    'SPACE': 0x39,
    'ESC': 0x01,
}


def _send_scan(code, keyup=False):
    """
    Invia un singolo evento tastiera a livello scancode (DirectInput-friendly).

    :param code:  scancode hardware del tasto (vedere ``SCAN_CODES``)
    :param keyup: se ``False`` -> press; se ``True`` -> release
    """
    extra = ctypes.c_ulong(0)
    flags = _KEYEVENTF_SCANCODE | (_KEYEVENTF_KEYUP if keyup else 0)
    ki = _KeyBdInput(0, code, flags, 0, ctypes.pointer(extra))
    ii = _InputI(); ii.ki = ki
    inp = _Input(ctypes.c_ulong(1), ii)  # type=1 -> INPUT_KEYBOARD
    _SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))


class KeyController:
    """
    Wrapper stateful sopra ``_send_scan``: tiene traccia di quali tasti
    sono attualmente premuti per garantire press/release idempotenti.

    Tipico utilizzo nel bot::

        kc = KeyController()
        kc.press('W')         # avanti
        ...
        kc.release_all()      # cleanup all'uscita
    """

    def __init__(self):
        # Set dei tasti correntemente premuti. Usato per:
        # - skip di press doppi (gia' premuto -> no-op)
        # - skip di release di tasti non premuti
        # - release_all() finale all'uscita
        self.pressed = set()

    def press(self, key):
        """Preme un tasto (no-op se gia' premuto)."""
        if key in self.pressed:
            return
        _send_scan(SCAN_CODES[key], keyup=False)
        self.pressed.add(key)

    def release(self, key):
        """Rilascia un tasto (no-op se non premuto)."""
        if key not in self.pressed:
            return
        _send_scan(SCAN_CODES[key], keyup=True)
        self.pressed.discard(key)

    def release_all(self):
        """Rilascia tutti i tasti correntemente premuti."""
        for k in list(self.pressed):
            self.release(k)
