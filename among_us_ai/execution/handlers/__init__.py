"""
Handlers delle azioni del motore di esecuzione.

Ogni file gestisce una "famiglia" di azioni:

- ``simple_clicks.py``  : click, click_rect, click_poly
- ``simple_drags.py``   : drag, drag_multi, drag_zone, drag_hold
- ``wiring.py``         : wiring (cablaggio)
- ``sync_click.py``     : sync_click (click sincronizzato a evento visivo)
- ``anomaly.py``        : click_anomaly
- ``number_match.py``   : number_match
- ``ocr_keypad.py``     : ocr_keypad
- ``yolo_actions.py``   : yolo_drag, yolo_drag_all, yolo_click, yolo_click_all
- ``click_until.py``    : click_until

Ogni handler ha la firma standard::

    handle_<tipo>(az, cx, cy, cw, ch, hwnd, is_test) -> None

Il dispatcher principale e' in ``runtime.py::esegui_azioni``.
"""

from .simple_clicks import handle_click, handle_click_rect, handle_click_poly
from .simple_drags  import (handle_drag, handle_drag_multi,
                            handle_drag_zone, handle_drag_hold)
from .wiring        import handle_wiring
from .sync_click    import handle_sync_click
from .anomaly       import handle_click_anomaly
from .number_match  import handle_number_match
from .ocr_keypad    import handle_ocr_keypad
from .yolo_actions  import (handle_yolo_drag, handle_yolo_drag_all,
                            handle_yolo_click, handle_yolo_click_all)
from .click_until   import handle_click_until


# Mappa: nome del tipo di azione -> funzione handler.
# Usato dal dispatcher in ``runtime.py`` per evitare un lungo if/elif.
DISPATCH_MAP = {
    "click":           handle_click,
    "click_rect":      handle_click_rect,
    "click_poly":      handle_click_poly,
    "drag":            handle_drag,
    "drag_multi":      handle_drag_multi,
    "drag_zone":       handle_drag_zone,
    "drag_hold":       handle_drag_hold,
    "wiring":          handle_wiring,
    "sync_click":      handle_sync_click,
    "click_anomaly":   handle_click_anomaly,
    "number_match":    handle_number_match,
    "ocr_keypad":      handle_ocr_keypad,
    "yolo_drag":       handle_yolo_drag,
    "yolo_drag_all":   handle_yolo_drag_all,
    "yolo_click":      handle_yolo_click,
    "yolo_click_all":  handle_yolo_click_all,
    "click_until":     handle_click_until,
}


__all__ = ["DISPATCH_MAP"]
