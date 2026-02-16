"""
Handler per i minigiochi che richiedono visione artificiale (YOLO).

5 varianti:
- yolo_drag        drag verso un singolo oggetto rilevato
- yolo_drag_all    drag su ogni oggetto rilevato (loop)
- yolo_click       click su singolo oggetto
- yolo_click_all   click su tutti (loop)
- yolo_drag_seq    drag in sequenza guidata su tappe predefinite

Tutti usano un modello YOLO (.pt) caricato dinamicamente. La ROI
(region of interest) e' un poligono dell'azione.
"""
import time as _time
import math as _math
try:
    import pyautogui as _pag
    import mss as _mss
    import numpy as _np
    import cv2 as _cv2
    from ultralytics import YOLO as _YOLO
except Exception:
    _pag = _mss = _np = _cv2 = _YOLO = None
from .geometria import _point_in_polygon
from .input_mouse import _drag_umano, _click_hold, _drag_seq_tappe

def _h_yolo_drag(az, cx, cy, cw, ch, hwnd, durata, attesa):
    import os as _os
    try:
        from ultralytics import YOLO as _YOLO
        import mss as _mss
        import numpy as _np
        _YOLO_OK = True
    except ImportError:
        _YOLO_OK = False
    model_name = az.get('yolo_model', '')
    _base_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    _model_path = _os.path.join(_base_dir, model_name) if not _os.path.isabs(model_name) else model_name
    if not _os.path.exists(_model_path):
        _model_path = model_name
    ex = cx + int(az.get('end_rx', 0) * cw)
    ey = cy + int(az.get('end_ry', 0) * ch)
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
                m_left, m_top, m_width, m_height = (cx, cy, cw, ch)
            monitor = {'top': m_top, 'left': m_left, 'width': m_width, 'height': m_height}
            while _time.time() - start_t < 3.0:
                try:
                    sct_img = _np.array(sct.grab(monitor))
                    img_bgr = sct_img[:, :, :3]
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
                                if (yi > ry_rel) != (yj > ry_rel) and rx_rel < (xj - xi) * (ry_rel - yi) / (yj - yi + 1e-12) + xi:
                                    inside = not inside
                                j_v = i_v
                        if inside:
                            _drag_umano(sx, sy, ex, ey, durata)
                            found = True
                            break
                except Exception:
                    pass
                _time.sleep(0.1)
    if not found:
        print(f'[yolo_drag] Oggetto non trovato (modello: {_model_path})')
    _time.sleep(attesa)


def _h_yolo_drag_all(az, cx, cy, cw, ch, hwnd, durata, attesa):
    import os as _os
    try:
        from ultralytics import YOLO as _YOLO
        import mss as _mss
        import numpy as _np
        _YOLO_OK = True
    except ImportError:
        _YOLO_OK = False
    model_name = az.get('yolo_model', '')
    _base_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    _model_path = _os.path.join(_base_dir, model_name) if not _os.path.isabs(model_name) else model_name
    if not _os.path.exists(_model_path):
        _model_path = model_name
    ex = cx + int(az.get('end_rx', 0) * cw)
    ey = cy + int(az.get('end_ry', 0) * ch)
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
                m_left, m_top, m_width, m_height = (cx, cy, cw, ch)
            monitor = {'top': m_top, 'left': m_left, 'width': m_width, 'height': m_height}
            empty_frames = 0
            while True:
                try:
                    sct_img = _np.array(sct.grab(monitor))
                    img_bgr = sct_img[:, :, :3]
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
                                if (yi > ry_rel) != (yj > ry_rel) and rx_rel < (xj - xi) * (ry_rel - yi) / (yj - yi + 1e-12) + xi:
                                    inside = not inside
                                j_v = i_v
                        if inside and _math.hypot(sx - ex, sy - ey) > 60:
                            valid_boxes.append((sx, sy, float(box.conf[0])))
                    if not valid_boxes:
                        empty_frames += 1
                        if empty_frames >= 3:
                            break
                        _time.sleep(0.1)
                        continue
                    empty_frames = 0
                    best_box = max(valid_boxes, key=lambda b: b[2])
                    sx, sy = (best_box[0], best_box[1])
                    _drag_umano(sx, sy, ex, ey, durata)
                    _time.sleep(0.15)
                except Exception as e:
                    print(f'[yolo_drag_all] Errore iterazione: {e}')
                    break
    else:
        print(f'[yolo_drag_all] YOLO o modello non trovato: {_model_path}')
    _time.sleep(attesa)


def _h_yolo_click(az, cx, cy, cw, ch, hwnd, durata, attesa):
    import os as _os
    try:
        from ultralytics import YOLO as _YOLO
        import mss as _mss
        import numpy as _np
        _YOLO_OK = True
    except ImportError:
        _YOLO_OK = False
    model_name = az.get('yolo_model', '')
    _base_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
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
                m_left, m_top, m_width, m_height = (cx, cy, cw, ch)
            monitor = {'top': m_top, 'left': m_left, 'width': m_width, 'height': m_height}
            while _time.time() - start_t < 3.0:
                try:
                    sct_img = _np.array(sct.grab(monitor))
                    img_bgr = sct_img[:, :, :3]
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
                                if (yi > ry_rel) != (yj > ry_rel) and rx_rel < (xj - xi) * (ry_rel - yi) / (yj - yi + 1e-12) + xi:
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
        print(f'[yolo_click] Oggetto non trovato (modello: {_model_path})')
    _time.sleep(attesa)


def _h_yolo_click_all(az, cx, cy, cw, ch, hwnd, durata, attesa):
    import os as _os
    try:
        from ultralytics import YOLO as _YOLO
        import mss as _mss
        import numpy as _np
        _YOLO_OK = True
    except ImportError:
        _YOLO_OK = False
    model_name = az.get('yolo_model', '')
    _base_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
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
                m_left, m_top, m_width, m_height = (cx, cy, cw, ch)
            monitor = {'top': m_top, 'left': m_left, 'width': m_width, 'height': m_height}
            empty_frames = 0
            while True:
                try:
                    sct_img = _np.array(sct.grab(monitor))
                    img_bgr = sct_img[:, :, :3]
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
                                if (yi > ry_rel) != (yj > ry_rel) and rx_rel < (xj - xi) * (ry_rel - yi) / (yj - yi + 1e-12) + xi:
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
                        sx, sy = (box_info[0], box_info[1])
                        _click_hold(sx, sy, durata)
                        _time.sleep(0.05)
                    _time.sleep(0.15)
                except Exception as e:
                    print(f'[yolo_click_all] Errore iterazione: {e}')
                    break
    else:
        print(f'[yolo_click_all] YOLO o modello non trovato: {_model_path}')
    _time.sleep(attesa)


def _h_yolo_drag_seq(az, cx, cy, cw, ch, hwnd, durata, attesa):
    import os as _os
    try:
        from ultralytics import YOLO as _YOLO
        import mss as _mss
        import numpy as _np
        _YOLO_OK = True
    except ImportError:
        _YOLO_OK = False
    model_name = az.get('yolo_model', '')
    _base_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
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
                m_left, m_top, m_width, m_height = (cx, cy, cw, ch)
            monitor = {'top': m_top, 'left': m_left, 'width': m_width, 'height': m_height}
            start_t = _time.time()
            empty_frames = 0
            while _time.time() - start_t < 15.0:
                try:
                    sct_img = _np.array(sct.grab(monitor))
                    img_bgr = sct_img[:, :, :3]
                    results = model(img_bgr, conf=0.5, verbose=False)
                    boxes = results[0].boxes
                    valid_boxes = []
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        sx = m_left + int((x1 + x2) / 2)
                        sy = m_top + int((y1 + y2) / 2)
                        cls_id = int(box.cls[0])
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
                                if (yi > ry_rel) != (yj > ry_rel) and rx_rel < (xj - xi) * (ry_rel - yi) / (yj - yi + 1e-12) + xi:
                                    inside = not inside
                                j_v = i_v
                        if inside:
                            valid_boxes.append({'x': sx, 'y': sy, 'cls': cls_id})
                    if not valid_boxes:
                        empty_frames += 1
                        if empty_frames >= 3:
                            break
                        _time.sleep(0.2)
                        continue
                    empty_frames = 0
                    classi_count = {}
                    for b in valid_boxes:
                        classi_count[b['cls']] = classi_count.get(b['cls'], 0) + 1
                    if len(classi_count) >= 2:
                        cls_sorgente = min(classi_count, key=classi_count.get)
                        sorgenti = [b for b in valid_boxes if b['cls'] == cls_sorgente]
                        target = [b for b in valid_boxes if b['cls'] != cls_sorgente]
                    else:
                        valid_boxes.sort(key=lambda b: b['x'])
                        sorgenti = [valid_boxes[0]]
                        target = valid_boxes[1:]
                    if sorgenti and target:
                        sorgente = min(sorgenti, key=lambda b: b['x'])
                        target = [t for t in target if t['x'] > sorgente['x']]
                        target.sort(key=lambda b: b['x'])
                        if target:
                            punti_drag = [(sorgente['x'], sorgente['y'])] + [(t['x'], t['y']) for t in target]
                            if len(punti_drag) >= 2:
                                p_penultimo = punti_drag[-2]
                                p_ultimo = punti_drag[-1]
                                dx = p_ultimo[0] - p_penultimo[0]
                                dy = p_ultimo[1] - p_penultimo[1]
                                dist = _math.hypot(dx, dy)
                                if dist > 0:
                                    extend_ratio = 150.0 / dist
                                    ex = int(p_ultimo[0] + dx * extend_ratio)
                                    ey = int(p_ultimo[1] + dy * extend_ratio)
                                    punti_drag[-1] = (ex, ey)
                            _drag_seq_tappe(punti_drag, durata)
                            _time.sleep(0.5)
                        else:
                            _time.sleep(0.2)
                    else:
                        _time.sleep(0.2)
                except Exception as e:
                    print(f'[yolo_drag_seq] Errore iterazione: {e}')
                    break
                _time.sleep(0.1)
    else:
        print(f'[yolo_drag_seq] YOLO o modello non trovato: {_model_path}')
    _time.sleep(attesa)


