"""Manager di stato persistente: zone, POI, task."""

from .zone_manager import ZoneManager
from .poi_manager import PoiManager
from .task_manager import TaskManager

__all__ = ["ZoneManager", "PoiManager", "TaskManager"]
