"""
io_input: input tastiera simulato a basso livello.

Espone :class:`KeyController` (gestione press/release dei tasti WASD verso
la finestra di Among Us) e ``SCAN_CODES`` (mappatura nome -> scancode hardware
per SendInput). Il motore di esecuzione delle task usa lo stesso modulo per
inviare SPAZIO, ESC, frecce, ecc.
"""

from .key_controller import KeyController, SCAN_CODES

__all__ = ["KeyController", "SCAN_CODES"]
