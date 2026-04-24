"""
Among Us AI Bot
===============

Bot di navigazione e automazione per Among Us (Skeld).

Struttura del package (in ordine di dipendenza):

- ``core``         : configurazione, palette colori, ``stop_flag`` globale,
                     dipendenze Win32 opzionali, utility geometriche.
- ``io_input``     : input simulato di basso livello (SendInput, scancode).
- ``pathfinding``  : A* su griglia di celle calpestabili registrate dal mapper.
- ``game_io``      : lettura della memoria RAM di Among Us
                     (posizione del giocatore, lista task, stato del gioco).
- ``intelligence`` : analisi dei player in tempo reale (sospettosita',
                     attivita' sospette, follow score, task inferite).
- ``managers``     : persistenza di zone, POI e task registrate; pianificatore
                     Auto-All; calcolo distanze A* fra task.
- ``execution``    : motore di esecuzione runtime + template per i file
                     autonomi in ``tasks_exec/`` (thin wrapper + _motore/).
- ``ui``           : dashboard principale (DearPyGui), editor azioni,
                     mixin che si compongono in ``GPSVisualizerPro``.

Entry point::

    python -m among_us_ai     # via __main__.py
    python main.py             # alternativa
"""

__version__ = "2.2.61"
