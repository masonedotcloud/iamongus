"""
Flag globale per interrompere il "Test" dell'editor azioni.

Settato dall'hotkey di Stop globale (F4 / End) nella dashboard
(`ui.gps_app.GPSVisualizerPro.aggiorna_frame`) e dal pulsante Stop
dell'editor (`ui.task_action_editor.TaskActionEditor`).

Letto dal motore di esecuzione runtime (`execution.runtime.esegui_azioni`)
fra una azione e l'altra: se True, il test viene interrotto.

Si trova in un modulo a se' perche' nell'originale era una variabile
globale condivisa fra TaskActionEditor, esegui_azioni e GPSVisualizerPro:
nel modulo unico bastava ``global _STOP_TEST_THREAD``, ma con il package
splittato serve un punto di riferimento univoco.

Uso::

    from among_us_ai.core import stop_flag
    # Flag globale di stop (True quando F4 o FINE viene premuto)
    stop_flag.requested = True       # richiede stop
    # Check stop globale (F4 o FINE)
    if stop_flag.requested: ...      # consuma
"""


class _StopFlag:
    """Wrapper boolean: l'attributo `requested` e' l'unico stato."""

    __slots__ = ("requested",)

    def __init__(self):
        """Inizializza l'istanza con i valori di default."""
        self.requested = False


# Singleton globale del package.
flag = _StopFlag()


# Helper di compatibilita' con i pattern del codice originale.
def request_stop():
    """Richiede lo stop globale (chiamata da F4 e END)."""
    flag.requested = True


def clear_stop():
    """Resetta il flag di stop globale."""
    flag.requested = False


def is_stop_requested():
    """Ritorna se stop requested."""
    return flag.requested
