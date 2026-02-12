"""
Loader dei template Python usati per generare i file in `tasks_exec/`.

Esistono DUE template:

1. ``_motore_template.txt``: il MOTORE COMUNE che viene scritto come
   ``tasks_exec/_motore.py``. Contiene helper geometriche, handler per
   ogni tipo di azione, dispatcher, lifecycle. Riceve TASK_META e AZIONI
   come parametri (non come globali) per gestire qualunque task.

2. ``task_template.txt``: il vecchio template per file COMPLETAMENTE
   AUTONOMI (~1300 righe). Tenuto per compatibilita' / fallback se
   l'utente vuole un file standalone (modalita' "codice personalizzato"
   o esportazione).

Il `task_writer` di default usa il modello "thin wrapper":
- Crea/aggiorna `tasks_exec/_motore.py` (motore comune)
- Genera ogni file task come thin wrapper (~100 righe) che importa
  il motore relativo.

I template sono memorizzati come file di testo separati per essere
modificabili senza toccare codice Python e per evitare che editor/IDE
provino ad analizzarli come codice del progetto.
"""

import os

_TEMPLATE_FILE = os.path.join(os.path.dirname(__file__), "task_template.txt")
_MOTORE_FILE   = os.path.join(os.path.dirname(__file__), "_motore_template.txt")

_cache_template = None
_cache_motore = None


def get_motore_template():
    """
    Ritorna il template raw del motore di esecuzione inline da inserire
    nei file `.py` AUTONOMI generati per ogni task.

    NB: e' il vecchio template, usato solo in modalita' "file autonomo"
    (che produce file da ~1300 righe). Per il modello "thin wrapper"
    (default) usa ``get_motore_modulo()``.
    """
    global _cache_template
    if _cache_template is None:
        with open(_TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            _cache_template = f.read()
    return _cache_template


def get_motore_modulo():
    """
    Ritorna il template raw del motore COMUNE (`_motore.py` in
    ``tasks_exec/``) usato dal modello thin wrapper.

    Contiene tutte le helper, handler, dispatcher, e funzioni
    ``run_task(task_meta, azioni, ctx)`` ed ``esegui_lifecycle(...)``
    che ricevono i dati come parametri.
    """
    global _cache_motore
    if _cache_motore is None:
        with open(_MOTORE_FILE, 'r', encoding='utf-8') as f:
            _cache_motore = f.read()
    return _cache_motore
