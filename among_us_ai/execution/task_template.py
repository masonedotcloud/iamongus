"""
Riferimento al template del motore di esecuzione per i file in ``tasks_exec/``.

Storia (per contesto):

- v1: ogni task era un file ``.py`` COMPLETAMENTE AUTONOMO da ~1300 righe
  (motore inline). Template: ``task_template.txt``.
- v2: motore comune in un SINGOLO file ``tasks_exec/_motore.py``; le task
  erano thin wrapper. Template: ``_motore_template.txt``.
- v3 (ATTUALE): motore comune diviso in PACKAGE MODULARE. La cartella
  ``_motore_pkg/`` viene copiata in ``tasks_exec/_motore/`` (13 file Python,
  uno per famiglia di handler) e le task restano thin wrapper di ~74 righe.

Le varianti v1/v2 (i due file ``.txt``) sono state rimosse: erano codice
morto (i loro loader ``get_motore_template`` / ``get_motore_modulo`` non
venivano piu' chiamati da nessuna parte). Il task_writer usa esclusivamente
il package modulare, il cui path e' esposto da :func:`get_motore_pkg_path`.
"""

import os

# Path del package modulare del motore (variante v3, l'unica usata).
# Il task_writer lo copia in `tasks_exec/_motore/`.
_MOTORE_PKG = os.path.join(os.path.dirname(__file__), "_motore_pkg")


def get_motore_pkg_path():
    """
    Ritorna il path della cartella ``_motore_pkg/`` (template del package
    modulare del motore). Usato dal ``task_writer`` per copiarla in
    ``tasks_exec/_motore/``.
    """
    return _MOTORE_PKG
