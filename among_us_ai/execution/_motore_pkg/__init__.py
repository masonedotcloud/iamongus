"""
Motore di esecuzione delle azioni delle task.

Architettura: package modulare diviso per responsabilita'.

Modulo                 Funzioni esposte
---------------------- -----------------------------------------
geometria.py           helper geometriche (poligono, rettangolo, ...)
input_mouse.py         helper di input (click, drag con Bezier)
handlers_*.py          handler per ogni tipo di azione (~10 file)
dispatcher.py          esegui_azioni + DISPATCH_MAP
lifecycle.py           setup, run_task, teardown, esegui_lifecycle

API pubblica del package:
- esegui_azioni(azioni, hwnd, current_step, is_test)
- run_task(task_meta, azioni, ctx)
- esegui_lifecycle(task_meta, azioni, ctx)
"""

from .lifecycle import setup, run_task, teardown, esegui_lifecycle
from .dispatcher import esegui_azioni

__all__ = [
    "setup", "run_task", "teardown",
    "esegui_lifecycle", "esegui_azioni",
]
