"""
Loader dei template Python usati per generare i file in `tasks_exec/`.

Esistono TRE varianti di motore (in ordine cronologico):

1. ``task_template.txt``: il primo template, file COMPLETAMENTE AUTONOMI
   (~1300 righe ognuno). Ogni file task contiene il motore inline.
   Tenuto per compatibilita' / fallback se l'utente vuole un file
   standalone (esportazione, ispezione, ecc.).

2. ``_motore_template.txt``: motore comune in un SINGOLO file
   ``tasks_exec/_motore.py`` (~1266 righe). I file task sono thin
   wrapper di ~74 righe. Tenuto per riferimento.

3. ``_motore_pkg/``: motore comune diviso in PACKAGE MODULARE.
   Cartella ``tasks_exec/_motore/`` con ~13 file Python (uno per
   famiglia di handler). I file task sono thin wrapper di ~74 righe.
   E' il modello DEFAULT del task_writer (v2.1.9+).

Il `task_writer` di default usa il modello (3): copia il package
``_motore_pkg/`` in ``tasks_exec/_motore/`` e genera i thin wrapper.
"""

import os

_TEMPLATE_FILE = os.path.join(os.path.dirname(__file__), "task_template.txt")
_MOTORE_FILE   = os.path.join(os.path.dirname(__file__), "_motore_template.txt")
_MOTORE_PKG    = os.path.join(os.path.dirname(__file__), "_motore_pkg")

_cache_template = None
_cache_motore = None


def get_motore_template():
    """
    Ritorna il template raw del motore di esecuzione inline da inserire
    nei file `.py` AUTONOMI generati per ogni task.

    NB: e' il vecchio template (variante 1), produce file da ~1300 righe.
    """
    global _cache_template
    if _cache_template is None:
        with open(_TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            _cache_template = f.read()
    return _cache_template


def get_motore_modulo():
    """
    Ritorna il template raw del motore COMUNE in un singolo file (variante 2).

    NB: tenuto per riferimento. Il default e' il package modulare
    (vedi ``get_motore_pkg_path()``).
    """
    global _cache_motore
    if _cache_motore is None:
        with open(_MOTORE_FILE, 'r', encoding='utf-8') as f:
            _cache_motore = f.read()
    return _cache_motore


def get_motore_pkg_path():
    """
    Ritorna il path della cartella ``_motore_pkg/`` (template del package
    modulare del motore, variante 3). Usato dal task_writer per copiarla
    in ``tasks_exec/_motore/``.
    """
    return _MOTORE_PKG
