"""
Loader del template Python usato per generare i file in `tasks_exec/`.

Il template è memorizzato come file di testo separato (`task_template.txt`)
in modo da poterlo modificare senza dover toccare codice Python e per evitare
che editor/IDE provino ad analizzarlo come codice del progetto.

Il template è una stringa raw: contiene riferimenti tipo `{TASK_META['nome']}`
che NON vanno sostituiti — sono codice del file generato. Va concatenato
così com'è dopo l'header e il meta-block costruiti dal `TaskManager`.
"""

import os

_TEMPLATE_FILE = os.path.join(os.path.dirname(__file__), "task_template.txt")

_cache = None


def get_motore_template():
    """
    Ritorna il template raw del motore di esecuzione inline da inserire
    nei file `.py` generati per ogni task. Letto da disco una volta sola.
    """
    global _cache
    if _cache is None:
        with open(_TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            _cache = f.read()
    return _cache
