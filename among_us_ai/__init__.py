"""
Among Us AI Bot
===============

Bot di navigazione/automazione per Among Us.

Struttura del package:
- ``core``        : configurazione, palette colori, dipendenze opzionali Win,
                    utility geometriche.
- ``io_input``    : input simulato di basso livello (SendInput/scan-code).
- ``pathfinding`` : A* su griglia di celle calpestabili.
- ``game_io``     : lettura della memoria di Among Us (posizione, task).
- ``managers``    : persistenza di zone, POI e task registrate.
- ``execution``   : motore di esecuzione runtime e template per i file
                    autonomi nei ``tasks_exec/``.
- ``ui``          : dashboard principale (DearPyGui) ed editor azioni.

Entry point: ``python -m among_us_ai``  oppure  ``python main.py``.
"""

__version__ = "2.2.61"
