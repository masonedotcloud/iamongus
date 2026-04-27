"""
Esecuzione delle azioni delle task: motore runtime + template per i file
generati nella cartella ``tasks_exec/``.

NB: questo ``__init__.py`` non importa il runtime in modo top-level perche'
il runtime richiede ``pyautogui``, ``win32gui`` ecc., che sono dipendenze
opzionali Windows-only. Il TaskManager ha bisogno solo del path del package
template, che e' importabile da solo (nessuna dipendenza Win)::

    from among_us_ai.execution.task_template import get_motore_pkg_path

Per usare il runtime sui sistemi dove e' disponibile::

    from among_us_ai.execution.runtime import esegui_azioni
"""
