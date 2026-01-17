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

    from among_us_gps.core import stop_flag
    stop_flag.requested = True       # richiede stop
    if stop_flag.requested: ...      # consuma
"""


class _StopFlag:
    """Wrapper boolean: l'attributo `requested` e' l'unico stato."""

    __slots__ = ("requested",)

    def __init__(self):
        self.requested = False


# Singleton globale del package.
flag = _StopFlag()


# Helper di compatibilita' con i pattern del codice originale.
def request_stop():
    flag.requested = True


def clear_stop():
    flag.requested = False


def is_stop_requested():
    return flag.requested
