"""
managers: stato persistente del bot (zone, POI, task).

- :class:`ZoneManager`               : poligoni delle "stanze" disegnati dall'utente
- :class:`PoiManager`                 : punti di interesse (vent, body, ecc.)
- :class:`TaskManager`                : task registrate (facade su Dettagli + Esecuzione)
- :class:`TaskDettagliManager`        : struttura/posizione/parametri (statici)
- :class:`TaskEsecuzioneManager`      : azioni concrete (mouse, drag, OCR)

I 4 manager hanno lo stesso schema d'uso: ``load()``, ``salva()``, e una
lista in memoria sincronizzata con il file su disco.
"""

from .zone_manager           import ZoneManager
from .poi_manager            import PoiManager
from .task_manager           import TaskManager
from .task_dettagli_manager  import TaskDettagliManager
from .task_esecuzione_manager import TaskEsecuzioneManager

__all__ = [
    "ZoneManager", "PoiManager",
    "TaskManager", "TaskDettagliManager", "TaskEsecuzioneManager",
]
