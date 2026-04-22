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
from .input_mouse import _drag_umano, _click_hold, _drag_seq_tappe, _drag_snap

def _h_yolo_drag(az, cx, cy, cw, ch, hwnd, durata, attesa):
    """
    Handler ``yolo_drag``: drag verso il SINGOLO oggetto rilevato con
    confidence piu' alta dentro la ROI.

    Cerca per 3s; se trova l'oggetto, fa drag dalla sua posizione al
    target (end_rx, end_ry) usando :func:`_drag_umano`. Se l'oggetto cade
    fuori dal poligono ROI, viene scartato (no falsi positivi al bordo).
    """
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
        print(f'[YoloDrag] Oggetto non trovato (modello: {_model_path})')
    _time.sleep(attesa)


def _h_yolo_drag_all(az, cx, cy, cw, ch, hwnd, durata, attesa):
    """
    Handler per Clean O2 Filter (e simili) con DRAG A FASI.

    Il problema precedente: il drag "umano" classico (pyautogui.moveTo
    seguito da mouseDown immediato) NON viene registrato da Among Us
    come "afferro la foglia". Visivamente il bot "tocca" la foglia ma
    non la sposta.

    Nuova implementazione del drag in 5 fasi:
      1. SNAP istantaneo sulla posizione (no tween)
      2. Pausa 50ms (il sistema operativo aggiorna la posizione del cursore)
      3. mouseDown + pausa LUNGA 250ms (Among Us registra "ho afferrato")
      4. Micro-movimento iniziale di "engaging" (8 px verso target in 80ms)
      5. Movimento principale in linea retta verso il target
      6. Pausa 200ms sopra il target (Among Us registra "rilascio qui")
      7. mouseUp
    """
    import os as _os
    import random as _rnd
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

    if not _YOLO_OK or not _os.path.exists(_model_path):
        print(f'[YoloDragAll] YOLO o modello non trovato: {_model_path}',
              flush=True)
        _time.sleep(attesa)
        return

    print(f'[YoloDragAll] Inizio: target=({ex},{ey})', flush=True)
    model = _YOLO(_model_path)

    def _drag_fasi(sx, sy, ex_t, ey_t):
        """
        Drag a fasi ottimizzato per Among Us.

        Ogni fase ha un timing specifico per assicurarsi che il gioco
        registri ogni evento mouse correttamente.
        """
        # === FASE 1: SNAP istantaneo sulla posizione ===
        # Niente tween: vogliamo che il cursore sia ESATTAMENTE sopra
        # la foglia quando arriva il mouseDown. Se uso pyautogui.moveTo
        # con duration=0.15, in quei 150ms la foglia animata si sposta
        # e il click cade fuori.
        _pag.moveTo(sx, sy)

        # === FASE 2: pausa per aggiornamento OS ===
        # Windows aggiorna la posizione del cursore con un piccolo lag.
        # Pausa minima per assicurarsi che il prossimo mouseDown sia
        # registrato alla nuova posizione e non a quella precedente.
        _time.sleep(0.05)

        # === FASE 3: mouseDown + pausa LUNGA di registrazione ===
        # Among Us ha bisogno di tempo per registrare il click come
        # "afferramento di oggetto" prima di vedere il drag. Senza
        # questa pausa, il gioco riceve mouseDown e subito dopo
        # vede il cursore lontano -> non capisce "drag iniziato".
        # 250ms e' stato testato come timing minimo affidabile.
        _pag.mouseDown(button='left')
        _time.sleep(0.25)

        # === FASE 4: micro-movimento di engaging ===
        # Sposto il cursore di 8 px verso il target in 80ms. Questo
        # piccolo movimento "lento" segnala al gioco "ho iniziato a
        # trascinare". Senza questo, il gioco potrebbe interpretare
        # tutto come "click e basta".
        dx_unit = (ex_t - sx)
        dy_unit = (ey_t - sy)
        dist = _math.hypot(dx_unit, dy_unit)
        if dist > 0:
            dx_unit = dx_unit / dist
            dy_unit = dy_unit / dist
        engage_steps = 8
        engage_dur = 0.08
        st_engage = engage_dur / engage_steps
        for i in range(1, engage_steps + 1):
            ex_engage = sx + int(dx_unit * i)
            ey_engage = sy + int(dy_unit * i)
            _pag.moveTo(ex_engage, ey_engage)
            _time.sleep(st_engage)

        # === FASE 5: movimento principale verso il target ===
        # Linea retta lenta (200ms totali). Niente Bezier con offset
        # random: il gioco perderebbe l'oggetto seguendo una curva
        # ampia. Movimento liscio e prevedibile.
        sx_now = sx + int(dx_unit * engage_steps)
        sy_now = sy + int(dy_unit * engage_steps)
        main_steps = 20
        main_dur = max(0.20, durata)
        st_main = main_dur / main_steps
        for i in range(1, main_steps + 1):
            t = i / main_steps
            mx = int(sx_now + (ex_t - sx_now) * t)
            my = int(sy_now + (ey_t - sy_now) * t)
            _pag.moveTo(mx, my)
            _time.sleep(st_main)

        # Snap finale al target esatto (interpolazione integer puo' dare
        # piccoli scarti)
        _pag.moveTo(ex_t, ey_t)

        # === FASE 6: pausa pre-release ===
        # Among Us ha bisogno di vedere "cursore fermo sul target" per
        # registrare il rilascio nella zona giusta. Senza pausa, il
        # gioco potrebbe vedere il release prima ancora che il cursore
        # sia "arrivato".
        _time.sleep(0.20)

        # === FASE 7: mouseUp ===
        _pag.mouseUp(button='left')

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
        monitor = {'top': m_top, 'left': m_left,
                   'width': m_width, 'height': m_height}
        empty_frames = 0
        total_drags = 0
        max_iter = 30   # safety net
        iteration = 0

        while iteration < max_iter:
            iteration += 1
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
                        print(f'[YoloDragAll] Nessuna foglia in 3 frame. '
                              f'Drag completati: {total_drags}', flush=True)
                        break
                    _time.sleep(0.1)
                    continue
                empty_frames = 0
                best_box = max(valid_boxes, key=lambda b: b[2])
                sx, sy = (best_box[0], best_box[1])
                print(f'[YoloDragAll] Drag {total_drags+1}: '
                      f'({sx},{sy}) -> ({ex},{ey}) conf={best_box[2]:.2f}',
                      flush=True)
                _drag_fasi(sx, sy, ex, ey)
                total_drags += 1
                # Pausa POST-drag generosa: il gioco ha tempo di rimuovere
                # visivamente la foglia dal frame buffer prima del prossimo
                # screenshot YOLO.
                _time.sleep(0.4)
            except Exception as e:
                print(f'[YoloDragAll] Errore iterazione: {e}', flush=True)
                break

        if iteration >= max_iter:
            print(f'[YoloDragAll] Limite {max_iter} iter raggiunto. '
                  f'Drag completati: {total_drags}', flush=True)

    _time.sleep(attesa)


def _h_yolo_click(az, cx, cy, cw, ch, hwnd, durata, attesa):
    """
    Handler ``yolo_click``: click sul SINGOLO oggetto rilevato con
    confidence piu' alta dentro la ROI. Cerca per 3s.
    """
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
        print(f'[YoloClick] Oggetto non trovato (modello: {_model_path})')
    _time.sleep(attesa)


def _h_yolo_click_all(az, cx, cy, cw, ch, hwnd, durata, attesa):
    """
    Handler ``yolo_click_all``: click su TUTTI gli oggetti rilevati dentro
    la ROI, uno alla volta con re-detection. Loop con stop dopo N iter
    senza nuovi rilevamenti.
    """
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
                    print(f'[YoloClickAll] Errore iterazione: {e}')
                    break
    else:
        print(f'[YoloClickAll] YOLO o modello non trovato: {_model_path}')
    _time.sleep(attesa)


def _h_yolo_drag_seq(az, cx, cy, cw, ch, hwnd, durata, attesa):
    """
    Handler ``yolo_drag_seq``: drag in sequenza guidata su tappe predefinite.

    Trova l'oggetto con YOLO, poi lo trascina seguendo una sequenza di
    waypoint registrati dall'utente (tipo "drag in poligono" complesso ma
    con punto di partenza dinamico determinato dall'AI).
    """
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
                    print(f'[YoloDragSeq] Errore iterazione: {e}')
                    break
                _time.sleep(0.1)
    else:
        print(f'[YoloDragSeq] YOLO o modello non trovato: {_model_path}')
    _time.sleep(attesa)


