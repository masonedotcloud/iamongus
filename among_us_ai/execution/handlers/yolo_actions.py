"""
Azioni basate su rilevamento YOLO (drag/click su oggetti rilevati).

Handler per le azioni di tipo: yolo_drag, yolo_drag_all, yolo_click, yolo_click_all.

Ogni funzione ha la firma standard:
    handle_<tipo>(az, ctx) -> None

dove ``az`` e' il dict dell'azione e ``ctx`` e' un namespace con i
parametri condivisi (cx, cy, cw, ch del rect del gioco; hwnd; flag
is_test). Le funzioni delegano i movimenti del mouse ai helper di
``_drag_utils.py``.
"""

import math
import os
import random
import time

import pyautogui

from .._drag_utils import (
    trascinamento_umano,
    trascinamento_multi,
    esegui_click_hold,
    trascinamento_e_tieni,
    trascinamento_seq_tappe,
)
from ...core.geometry import (
    random_point_in_rect,
    random_point_in_poly,
    point_in_polygon,
)


def handle_yolo_drag(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Drag basato su YOLO: cerca un oggetto in una ROI poligonale e lo trascina a destinazione.

    Parametri
    ---------
    az : dict
        Dizionario dell'azione (chiavi specifiche del tipo).
    cx, cy : int
        Origine (top-left) del rect del client del gioco.
    cw, ch : int
        Larghezza e altezza del rect del client.
    hwnd : int
        Handle della finestra del gioco (per check foreground).
    is_test : bool
        True se chiamato dal pulsante "Test" dell'editor (modalita' verbosa).
    """
    durata = az.get("durata", 0.0)
    attesa = az.get("attesa", 0.0)
    import os
    try:
        from ultralytics import YOLO
        import numpy as np
        import mss
        _YOLO_OK = True
    except ImportError:
        _YOLO_OK = False

    model_name = az.get('yolo_model', '')
    model_path = os.path.join(os.getcwd(), model_name) if not os.path.isabs(model_name) else model_name
        
    ex = cx + int(az.get('end_rx', 0) * cw)
    ey = cy + int(az.get('end_ry', 0) * ch)
    roi_poly = az.get('roi_poly', [])
    start_t = time.time()
    found = False
    print(f"[yolo_drag] Cerco oggetto con YOLO: {model_path}")
    
    if _YOLO_OK and os.path.exists(model_path):
        model = YOLO(model_path)
        # Cattura uno screenshot della regione del gioco
        with mss.mss() as sct:
            if len(roi_poly) >= 3:
                xs = [p[0] for p in roi_poly]
                ys = [p[1] for p in roi_poly]
                m_left = cx + int(min(xs) * cw)
                m_top = cy + int(min(ys) * ch)
                m_width = int((max(xs) - min(xs)) * cw)
                m_height = int((max(ys) - min(ys)) * ch)
            else:
                m_left, m_top, m_width, m_height = cx, cy, cw, ch
                
            monitor = {"top": m_top, "left": m_left, "width": m_width, "height": m_height}
            
            while time.time() - start_t < 3.0:
                try:
                    sct_img = np.array(sct.grab(monitor))
                    img_bgr = sct_img[:, :, :3]
                    # Inferenza YOLO sull'immagine catturata
                    results = model(img_bgr, conf=0.7, verbose=False)
                    boxes = results[0].boxes
                    if len(boxes) > 0:
                        best_box = max(boxes, key=lambda b: float(b.conf[0]))
                        x1, y1, x2, y2 = best_box.xyxy[0].tolist()
                        sx = m_left + int((x1 + x2) / 2)
                        sy = m_top + int((y1 + y2) / 2)
                        
                        inside = True
                        if len(roi_poly) >= 3:
                            rx_rel = (sx - cx) / cw
                            ry_rel = (sy - cy) / ch
                            inside = False
                            n_v = len(roi_poly)
                            j_v = n_v - 1
                            for i_v in range(n_v):
                                xi, yi = roi_poly[i_v]
                                xj, yj = roi_poly[j_v]
                                if ((yi > ry_rel) != (yj > ry_rel)) and \
                                   (rx_rel < (xj - xi) * (ry_rel - yi) / (yj - yi + 1e-12) + xi):
                                    inside = not inside
                                j_v = i_v
                        
                        if inside:
                            trascinamento_umano(sx, sy, ex, ey, durata)
                            found = True
                            break
                except Exception:
                    pass
                # Pausa il thread per il tempo specificato (secondi)
                time.sleep(0.1)
    
    if not found:
        print(f"[yolo_drag] Oggetto non trovato (cercato in: {model_path})")
    # Pausa il thread per il tempo specificato (secondi)
    time.sleep(attesa)



def handle_yolo_drag_all(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Come yolo_drag ma per tutti gli oggetti rilevati (es. raccogliere tutte le foglie).

    Parametri
    ---------
    az : dict
        Dizionario dell'azione (chiavi specifiche del tipo).
    cx, cy : int
        Origine (top-left) del rect del client del gioco.
    cw, ch : int
        Larghezza e altezza del rect del client.
    hwnd : int
        Handle della finestra del gioco (per check foreground).
    is_test : bool
        True se chiamato dal pulsante "Test" dell'editor (modalita' verbosa).
    """
    durata = az.get("durata", 0.0)
    attesa = az.get("attesa", 0.0)
    import os
    try:
        from ultralytics import YOLO
        import numpy as np
        import mss
        _YOLO_OK = True
    except ImportError:
        _YOLO_OK = False

    model_name = az.get('yolo_model', '')
    model_path = os.path.join(os.getcwd(), model_name) if not os.path.isabs(model_name) else model_name

    ex = cx + int(az.get('end_rx', 0) * cw)
    ey = cy + int(az.get('end_ry', 0) * ch)
    roi_poly = az.get('roi_poly', [])
    
    if _YOLO_OK and os.path.exists(model_path):
        model = YOLO(model_path)
        # Cattura uno screenshot della regione del gioco
        with mss.mss() as sct:
            if len(roi_poly) >= 3:
                xs = [p[0] for p in roi_poly]
                ys = [p[1] for p in roi_poly]
                m_left = cx + int(min(xs) * cw)
                m_top = cy + int(min(ys) * ch)
                m_width = int((max(xs) - min(xs)) * cw)
                m_height = int((max(ys) - min(ys)) * ch)
            else:
                m_left, m_top, m_width, m_height = cx, cy, cw, ch

            monitor = {"top": m_top, "left": m_left, "width": m_width, "height": m_height}
            max_time = 20.0
            start_t = time.time()
            empty_frames = 0
            
            while time.time() - start_t < max_time:
                try:
                    sct_img = np.array(sct.grab(monitor))
                    img_bgr = sct_img[:, :, :3]
                    # Inferenza YOLO sull'immagine catturata
                    results = model(img_bgr, conf=0.7, verbose=False)
                    boxes = results[0].boxes
                    
                    valid_boxes = []
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        sx = m_left + int((x1 + x2) / 2)
                        sy = m_top + int((y1 + y2) / 2)
                        
                        inside = True
                        if len(roi_poly) >= 3:
                            rx_rel = (sx - cx) / cw
                            ry_rel = (sy - cy) / ch
                            inside = False
                            n_v = len(roi_poly)
                            j_v = n_v - 1
                            for i_v in range(n_v):
                                xi, yi = roi_poly[i_v]
                                xj, yj = roi_poly[j_v]
                                if ((yi > ry_rel) != (yj > ry_rel)) and \
                                   (rx_rel < (xj - xi) * (ry_rel - yi) / (yj - yi + 1e-12) + xi):
                                    inside = not inside
                                j_v = i_v
                        if inside and math.hypot(sx - ex, sy - ey) > 60:
                            valid_boxes.append((sx, sy, float(box.conf[0])))
                            
                    if not valid_boxes:
                        empty_frames += 1
                        if empty_frames >= 3:
                            break 
                        # Pausa il thread per il tempo specificato (secondi)
                        time.sleep(0.1)
                        continue

                    empty_frames = 0
                    best_box = max(valid_boxes, key=lambda b: b[2])
                    sx, sy = best_box[0], best_box[1]
                    
                    trascinamento_umano(sx, sy, ex, ey, durata)
                    # Pausa il thread per il tempo specificato (secondi)
                    time.sleep(0.15) 
                    
                except Exception as e:
                    print(f"[yolo_drag_all] Errore iterazione: {e}")
                    break
    else:
        print(f"[yolo_drag_all] YOLO o modello non trovato: {model_path}")
    
    _time.sleep(attesa)



def handle_yolo_click(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Click su un oggetto rilevato da YOLO.

    Parametri
    ---------
    az : dict
        Dizionario dell'azione (chiavi specifiche del tipo).
    cx, cy : int
        Origine (top-left) del rect del client del gioco.
    cw, ch : int
        Larghezza e altezza del rect del client.
    hwnd : int
        Handle della finestra del gioco (per check foreground).
    is_test : bool
        True se chiamato dal pulsante "Test" dell'editor (modalita' verbosa).
    """
    durata = az.get("durata", 0.0)
    attesa = az.get("attesa", 0.0)
    import os as _os
    try:
        from ultralytics import YOLO as _YOLO
        import mss as _mss
        import numpy as _np
        _YOLO_OK = True
    except ImportError:
        _YOLO_OK = False

    model_name = az.get('yolo_model', '')
    _base_dir = _os.getcwd()  # cwd del processo Python = radice progetto
    _model_path = _os.path.join(_base_dir, model_name) if not _os.path.isabs(model_name) else model_name
    if not _os.path.exists(_model_path):
        _model_path = model_name
        
    roi_poly = az.get('roi_poly', [])
    start_t = _time.time()
    found = False
    
    if _YOLO_OK and _os.path.exists(_model_path):
        model = _YOLO(_model_path)
        with _mss.mss() as sct:
            if len(roi_poly) >= 3:
                xs = [p[0] for p in roi_poly]
                ys = [p[1] for p in roi_poly]
                m_left = cx + int(min(xs) * cw)
                m_top = cy + int(min(ys) * ch)
                m_width = int((max(xs) - min(xs)) * cw)
                m_height = int((max(ys) - min(ys)) * ch)
            else:
                m_left, m_top, m_width, m_height = cx, cy, cw, ch
                
            monitor = {"top": m_top, "left": m_left, "width": m_width, "height": m_height}
            
            while _time.time() - start_t < 3.0:
                try:
                    sct_img = _np.array(sct.grab(monitor))
                    img_bgr = sct_img[:, :, :3]
                    # Inferenza YOLO sull'immagine catturata
                    results = model(img_bgr, conf=0.5, verbose=False)
                    boxes = results[0].boxes
                    if len(boxes) > 0:
                        best_box = max(boxes, key=lambda b: float(b.conf[0]))
                        x1, y1, x2, y2 = best_box.xyxy[0].tolist()
                        sx = m_left + int((x1 + x2) / 2)
                        sy = m_top + int((y1 + y2) / 2)
                        
                        inside = True
                        if len(roi_poly) >= 3:
                            rx_rel = (sx - cx) / cw
                            ry_rel = (sy - cy) / ch
                            inside = False
                            n_v = len(roi_poly)
                            j_v = n_v - 1
                            for i_v in range(n_v):
                                xi, yi = roi_poly[i_v]
                                xj, yj = roi_poly[j_v]
                                if ((yi > ry_rel) != (yj > ry_rel)) and \
                                   (rx_rel < (xj - xi) * (ry_rel - yi) / (yj - yi + 1e-12) + xi):
                                    inside = not inside
                                j_v = i_v
                                
                        if inside:
                            _click_hold(sx, sy, durata)
                            found = True
                            break
                except Exception:
                    pass
                _time.sleep(0.1)
    
    if not found:
        print(f"[yolo_click] Oggetto non trovato (modello: {_model_path})")
    _time.sleep(attesa)



def handle_yolo_click_all(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Click su tutti gli oggetti rilevati da YOLO in una ROI.

    Parametri
    ---------
    az : dict
        Dizionario dell'azione (chiavi specifiche del tipo).
    cx, cy : int
        Origine (top-left) del rect del client del gioco.
    cw, ch : int
        Larghezza e altezza del rect del client.
    hwnd : int
        Handle della finestra del gioco (per check foreground).
    is_test : bool
        True se chiamato dal pulsante "Test" dell'editor (modalita' verbosa).
    """
    durata = az.get("durata", 0.0)
    attesa = az.get("attesa", 0.0)
    import os as _os
    try:
        from ultralytics import YOLO as _YOLO
        import mss as _mss
        import numpy as _np
        _YOLO_OK = True
    except ImportError:
        _YOLO_OK = False

    model_name = az.get('yolo_model', '')
    _base_dir = _os.getcwd()  # cwd del processo Python = radice progetto
    _model_path = _os.path.join(_base_dir, model_name) if not _os.path.isabs(model_name) else model_name
    if not _os.path.exists(_model_path):
        _model_path = model_name

    roi_poly = az.get('roi_poly', [])

    if _YOLO_OK and _os.path.exists(_model_path):
        model = _YOLO(_model_path)
        with _mss.mss() as sct:
            if len(roi_poly) >= 3:
                xs = [p[0] for p in roi_poly]
                ys = [p[1] for p in roi_poly]
                m_left = cx + int(min(xs) * cw)
                m_top = cy + int(min(ys) * ch)
                m_width = int((max(xs) - min(xs)) * cw)
                m_height = int((max(ys) - min(ys)) * ch)
            else:
                m_left, m_top, m_width, m_height = cx, cy, cw, ch

            monitor = {"top": m_top, "left": m_left, "width": m_width, "height": m_height}
            max_time = 20.0
            start_t = _time.time()
            empty_frames = 0
            
            while _time.time() - start_t < max_time:
                try:
                    sct_img = _np.array(sct.grab(monitor))
                    img_bgr = sct_img[:, :, :3]
                    # Inferenza YOLO sull'immagine catturata
                    results = model(img_bgr, conf=0.5, verbose=False)
                    boxes = results[0].boxes
                    
                    valid_boxes = []
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        sx = m_left + int((x1 + x2) / 2)
                        sy = m_top + int((y1 + y2) / 2)
                        
                        inside = True
                        if len(roi_poly) >= 3:
                            rx_rel = (sx - cx) / cw
                            ry_rel = (sy - cy) / ch
                            inside = False
                            n_v = len(roi_poly)
                            j_v = n_v - 1
                            for i_v in range(n_v):
                                xi, yi = roi_poly[i_v]
                                xj, yj = roi_poly[j_v]
                                if ((yi > ry_rel) != (yj > ry_rel)) and \
                                   (rx_rel < (xj - xi) * (ry_rel - yi) / (yj - yi + 1e-12) + xi):
                                    inside = not inside
                                j_v = i_v
                        if inside:
                            valid_boxes.append((sx, sy, float(box.conf[0])))
                            
                    if not valid_boxes:
                        empty_frames += 1
                        if empty_frames >= 3:
                            break 
                        _time.sleep(0.1)
                        continue

                    empty_frames = 0
                    
                    for box_info in valid_boxes:
                        sx, sy = box_info[0], box_info[1]
                        _click_hold(sx, sy, durata)
                        _time.sleep(0.05) 
                    
                    _time.sleep(0.15) 
                    
                except Exception as e:
                    print(f"[yolo_click_all] Errore iterazione: {e}")
                    break
    else:
        print(f"[yolo_click_all] YOLO o modello non trovato: {_model_path}")
    
    # Pausa il thread per il tempo specificato (secondi)
    time.sleep(attesa)
    


