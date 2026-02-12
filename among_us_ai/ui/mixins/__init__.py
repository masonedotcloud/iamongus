"""
Mixin di GPSVisualizerPro: metodi separati per organizzazione.

Ogni mixin contiene un blocco coerente di metodi della classe principale.
Sono disgiunti (nessun metodo si sovrappone) e tutti condividono lo stato
``self.*`` inizializzato in ``GPSVisualizerPro.__init__`` dentro
``among_us_ai/ui/app.py``.

Per aggiungere un nuovo gruppo di metodi: crea un nuovo file ``foo.py``
in questa cartella con una classe ``FooMixin``, e aggiungilo alla lista
delle basi in ``app.py``.
"""

from .auto_move import AutoMoveMixin
from .auto_quest import AutoQuestMixin
from .dialogs import DialogsMixin
from .input_callbacks import InputCallbacksMixin
from .map_loader import MapLoaderMixin
from .memory_sync import MemorySyncMixin
from .misc import MiscMixin
from .poi import PoiMixin
from .rendering_entities import RenderingEntitiesMixin
from .rendering_world import RenderingWorldMixin
from .tasks_launch import TasksLaunchMixin
from .tasks_list import TasksListMixin
from .tasks_popups_edit import TasksPopupsEditMixin
from .tasks_popups_register import TasksPopupsRegisterMixin
from .tasks_popups_subitem import TasksPopupsSubitemMixin
from .tasks_process import TasksProcessMixin
from .ui_setup import UISetupMixin
from .yolo_scanner import YoloScannerMixin
from .zones import ZonesMixin

__all__ = [
    "AutoMoveMixin", "AutoQuestMixin", "DialogsMixin",
    "InputCallbacksMixin", "MapLoaderMixin", "MemorySyncMixin",
    "MiscMixin", "PoiMixin",
    "RenderingEntitiesMixin", "RenderingWorldMixin",
    "TasksLaunchMixin", "TasksListMixin",
    "TasksPopupsEditMixin", "TasksPopupsRegisterMixin",
    "TasksPopupsSubitemMixin", "TasksProcessMixin",
    "UISetupMixin", "YoloScannerMixin", "ZonesMixin",
]
