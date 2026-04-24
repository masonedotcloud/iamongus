"""
ui: componenti UI DearPyGui.

- :class:`GPSVisualizerPro` : dashboard principale (mappa, navigation, task,
                              POI, sidebar Intelligence). Composta da ~25 mixin
                              (vedi sotto-package ``mixins/``).
- :class:`TaskActionEditor` : finestra di editing della sequenza di azioni
                              di una task (live preview del client del gioco,
                              click registrabili, multi-drag, wiring, ecc.).
                              Composta da 7 mixin (sotto-package ``editor_mixins/``).
"""

from .app import GPSVisualizerPro
from .editor import TaskActionEditor

__all__ = ["GPSVisualizerPro", "TaskActionEditor"]
