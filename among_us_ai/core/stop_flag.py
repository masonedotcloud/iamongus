"""
Flag globale di "stop" condiviso fra UI, motore di esecuzione e subprocess.

Contesto: in piu' punti del bot serve poter dire "interrompi subito":
- Hotkey F4/FINE dalla dashboard (`ui/app.py`).
- Pulsante "Stop" dell'editor azioni (`ui/editor.py`).
- Messaggio "STOP\\n" su stdin del subprocess (vedi `_motore_pkg/lifecycle.py`).

Tutti scrivono lo stesso flag; il dispatcher delle azioni
(`execution/_motore_pkg/dispatcher.py`) lo legge fra un'azione e l'altra e
abortisce il loop appena lo trova settato.

In passato era una variabile globale (``global _STOP_TEST_THREAD``);
nel package splittato serve un punto di riferimento univoco, quindi
e' incapsulata in una classe wrapper con singleton di modulo.

Uso tipico::

    from among_us_ai.core import stop_flag

    # Richiede stop
    stop_flag.request_stop()

    # All'inizio di una nuova esecuzione, resetta
    stop_flag.clear_stop()

    # Loop di lavoro: check fra una iterazione e l'altra
    while ...:
        if stop_flag.is_stop_requested():
            break
"""


class _StopFlag:
    """Contenitore boolean: l'unico stato e' :attr:`requested`."""

    __slots__ = ("requested",)

    def __init__(self):
        self.requested = False


# Singleton di modulo: importato da chiunque abbia bisogno del flag.
flag = _StopFlag()


# --- Helper di comodita' (interfaccia funzionale equivalente) ---

def request_stop():
    """Setta il flag di stop globale (richiesta di interruzione)."""
    flag.requested = True


def clear_stop():
    """Resetta il flag (chiamare all'inizio di una nuova esecuzione)."""
    flag.requested = False


def is_stop_requested():
    """Ritorna ``True`` se e' stato richiesto stop, ``False`` altrimenti."""
    return flag.requested
