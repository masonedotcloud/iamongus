"""
Mixin di TaskActionEditor: metodi separati per organizzazione.

Stesso pattern dei mixin di GPSVisualizerPro: i metodi sono divisi per
gruppo coerente (UI, click sul canvas, disegno, lista azioni, salva/test)
ma condividono lo stato ``self.*`` inizializzato in
``TaskActionEditor.__init__`` dentro ``among_us_ai/ui/editor.py``.
"""

from .canvas_input  import EditorCanvasInputMixin
from .drawing       import EditorDrawingMixin
from .list_panel    import EditorListPanelMixin
from .save_test     import EditorSaveTestMixin
from .sequence      import EditorSequenceMixin
from .start_actions import EditorStartActionsMixin
from .ui_build      import EditorUIMixin

__all__ = [
    "EditorCanvasInputMixin",
    "EditorDrawingMixin",
    "EditorListPanelMixin",
    "EditorSaveTestMixin",
    "EditorSequenceMixin",
    "EditorStartActionsMixin",
    "EditorUIMixin",
]
