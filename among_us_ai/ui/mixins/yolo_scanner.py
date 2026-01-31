"""
Thread di scansione YOLO per altri giocatori e porte chiuse.

Mixin di GPSVisualizerPro: metodi separati per organizzazione, ma
condividono lo stato self.* della classe principale.
"""

from ._imports import *



class YoloScannerMixin:
    """Mixin con i metodi di yolo scanner di GPSVisualizerPro."""
    def _yolo_scanner_loop(self):
        """Gira in background per rilevare altri giocatori a schermo e mapparli sulle coordinate GPS."""
        try:
            from ultralytics import YOLO
            import mss
            import numpy as np
        except ImportError:
            return
            
        model_path = getattr(GPSConfig, 'YOLO_PLAYER_MODEL', 'yolo_players.pt')
        door_model_path = getattr(GPSConfig, 'YOLO_DOOR_MODEL', 'porte.pt')
        
        model = YOLO(model_path) if os.path.exists(model_path) else None
        door_model = YOLO(door_model_path) if os.path.exists(door_model_path) else None
        
        if model is None and door_model is None:
            return
        
        while self.running:
            # Sospende se non deve scansionare nulla
            if not self.show_other_players and not self.auto_enabled and door_model is None:
                # Pausa il thread per il tempo specificato (secondi)
                time.sleep(0.5)
                continue
                
            # Cerca la finestra del gioco per nome
            hwnd = win32gui.FindWindow(None, "Among Us")
            if not hwnd:
                # Pausa il thread per il tempo specificato (secondi)
                time.sleep(1.0)
                continue
                
            rect = win32gui.GetWindowRect(hwnd)
            crect = win32gui.GetClientRect(hwnd)
            bw = int((rect[2] - rect[0] - crect[2]) / 2)
            th = int(rect[3] - rect[1] - crect[3] - bw)
            wx, wy = rect[0] + bw, rect[1] + th
            ww, wh = crect[2], crect[3]
            
            if ww <= 0 or wh <= 0:
                # Pausa il thread per il tempo specificato (secondi)
                time.sleep(0.5)
                continue
                
            # Cattura uno screenshot della regione del gioco
            with mss.mss() as sct:
                monitor = {"top": wy, "left": wx, "width": ww, "height": wh}
                try:
                    img = np.array(sct.grab(monitor))[:, :, :3]
                except Exception:
                    # Pausa il thread per il tempo specificato (secondi)
                    time.sleep(0.5)
                    continue
                    
            
            cx_screen, cy_screen = ww / 2, wh / 2

            # La dimensione ortografica standard di Unity per Among Us e' solitamente 3.0 (6.0 in altezza totale)
            # Utilizziamo la variabile che puo' essere auto-calibrata dal movimento o aggiustata manualmente
            cam_h = getattr(self, 'yolo_camera_height', 6.0)
            pixels_per_unit = wh / cam_h
            
            # IMPORTANTE: La telecamera di gioco punta al petto del giocatore, non ai piedi. Offset di ~0.36 unita' in su.
            camera_world_y = self.pos_target[1] + 0.36
            
            current_time = time.time()
            # --- RILEVAMENTO GIOCATORI ---
            if model and self.show_other_players:
                # Inferenza YOLO sull'immagine catturata
                results = model(img, conf=0.85, verbose=False)
                boxes = results[0].boxes

                # --- AUTO CALIBRAZIONE BASATA SUL MODO DI MUOVERSI ---
                current_pos = tuple(self.pos_target)
                if getattr(self, 'yolo_auto_calibrate', False) and getattr(self, '_yolo_prev_pos', None):
                    prev_pos = self._yolo_prev_pos
                    prev_boxes = getattr(self, '_yolo_prev_boxes', [])
                    
                    dx_w = current_pos[0] - prev_pos[0]
                    dy_w = current_pos[1] - prev_pos[1]
                    dist_w = math.hypot(dx_w, dy_w)
                    
                    # Calibra solo se noi ci muoviamo e vediamo ESATTAMENTE un giocatore (per evitare mixup di ID)
                    if dist_w > 0.05 and len(boxes) == 1 and len(prev_boxes) == 1:
                        b_curr = boxes[0].xyxy[0].tolist()
                        b_prev = prev_boxes[0]
                        
                        # Ignoriamo noi stessi (se e' al centro)
                        if math.hypot(((b_curr[0]+b_curr[2])/2) - cx_screen, ((b_curr[1]+b_curr[3])/2) - cy_screen) > (wh * 0.15):
                            cx_curr = (b_curr[0] + b_curr[2]) / 2
                            cy_curr = b_curr[3]
                            cx_prev = (b_prev[0] + b_prev[2]) / 2
                            cy_prev = b_prev[3]
                            
                            dx_p = cx_curr - cx_prev
                            dy_p = cy_curr - cy_prev
                            dist_p = math.hypot(dx_p, dy_p)
                            
                            # Se il giocatore avvistato si e' spostato a schermo
                            if dist_p > 5:
                                calculated_ppu = dist_p / dist_w
                                calculated_h = wh / calculated_ppu
                                
                                # Filtro passa basso: diamo un piccolo peso al nuovo calcolo (smoothing 5%)
                                if 3.0 < calculated_h < 12.0:
                                    self.yolo_camera_height = self.yolo_camera_height * 0.95 + calculated_h * 0.05
                                    try:
                                        # Se il widget esiste gia', lo rimuovo prima di ricrearlo
                                        if dpg.does_item_exist("yolo_cam_slider"):
                                            # Aggiorna il valore di un widget DPG
                                            dpg.set_value("yolo_cam_slider", self.yolo_camera_height)
                                    except Exception:
                                        pass

                self._yolo_prev_pos = current_pos
                self._yolo_prev_boxes = [box.xyxy[0].tolist() for box in boxes]

                new_detections = []
                
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    center_x = (x1 + x2) / 2
                    center_y = (y1 + y2) / 2
                    
                    cls_id = int(box.cls[0]) if hasattr(box, 'cls') else 36
                    
                    YOLO_COLORS = {
                        0: ('Red', (197, 17, 17)), 1: ('Blue', (19, 46, 209)), 2: ('Green', (17, 127, 45)),
                        3: ('Pink', (237, 84, 186)), 4: ('Orange', (239, 125, 13)), 5: ('Yellow', (245, 245, 87)),
                        6: ('Black', (63, 71, 78)), 7: ('White', (214, 224, 240)), 8: ('Purple', (107, 47, 187)),
                        9: ('Brown', (113, 73, 30)), 10: ('Cyan', (56, 254, 220)), 11: ('Lime', (80, 239, 57)),
                        12: ('Maroon', (107, 43, 60)), 13: ('Rose', (236, 192, 211)), 14: ('Banana', (255, 255, 103)),
                        15: ('Gray', (113, 136, 144)), 16: ('Tan', (145, 136, 119)), 17: ('Coral', (215, 100, 100))
                    }
                    
                    if cls_id < 18:
                        color_name, player_col = YOLO_COLORS.get(cls_id, ('Unknown', (150, 150, 150)))
                        is_dead = False
                    elif cls_id < 36:
                        color_name, player_col = YOLO_COLORS.get(cls_id - 18, ('Unknown', (150, 150, 150)))
                        is_dead = True
                    elif cls_id == 36:
                        color_name, player_col = ('Unknown', (150, 150, 150))
                        is_dead = False
                    else: # 37 o fallback
                        color_name, player_col = ('Unknown', (150, 150, 150))
                        is_dead = True
                    
                    # Ignora il nostro giocatore usando il centro della box e un raggio dinamico (15% dell'altezza dello schermo)
                    if math.hypot(center_x - cx_screen, center_y - cy_screen) < (wh * 0.15):
                        continue
                        
                    px = center_x
                    py = y2  # Base del rettangolo (piedi esatti del giocatore rilevato)
                    
                    dx = px - cx_screen
                    dy = py - cy_screen
                    
                    world_x = self.pos_target[0] + (dx / pixels_per_unit)
                    world_y = camera_world_y - (dy / pixels_per_unit)  # Invertito perche' la Y di gioco va verso l'alto
                    
                    # --- SNAP ALLA MAPPA CALPESTABILE (e filtro muri) ---
                    # Evita che i giocatori vengano renderizzati fuori dai muri o nel vuoto
                    if getattr(self, 'pathfinder', None) and self.pathfinder.walkable:
                        snapped_cell = self.pathfinder.nearest_walkable(world_x, world_y, radius=4)
                        if snapped_cell:
                            snap_x, snap_y = self.pathfinder._coord(snapped_cell)
                            # Se la detection cade troppo profondamente in un muro (dist > 1.2), e' un falso positivo ambientale
                            if math.hypot(world_x - snap_x, world_y - snap_y) > 1.2:
                                continue
                            world_x, world_y = snap_x, snap_y
                        else:
                            # Troppo lontano (oltre ~1.2 mattonelle) dalle zone calpestabili
                            continue

                    # Estrazione fallback se la classe e' sconosciuta
                    if color_name == 'Unknown':
                        perc_y = 0.5 if is_dead else 0.6
                        color_y = int(y1 + (y2 - y1) * perc_y)
                        color_x = int(center_x)
                        color_y = max(0, min(wh - 1, color_y))
                        color_x = max(0, min(ww - 1, color_x))
                        b, g, r = img[color_y, color_x]
                        player_col = (int(r), int(g), int(b))
                    
                    new_detections.append({
                        'x': world_x, 'y': world_y, 'time': current_time, 
                        'color': player_col, 'name': color_name, 'is_dead': is_dead
                    })
                    
                for nd in new_detections:
                    best_match = None
                    best_score = float('inf')
                    
                    for dp in self.detected_players:
                        dist = math.hypot(nd['x'] - dp['x'], nd['y'] - dp['y'])
                        time_diff = nd['time'] - dp['time']
                        
                        # Anti-Teleport: se la velocita' richiesta e' > 15 unita' al secondo, non e' lui
                        if time_diff > 0.1 and (dist / time_diff) > 15.0:
                            continue
                            
                        # Anti-Zombie: Se e' segnato morto, non puo' essere vivo se dello stesso colore
                        if dp.get('is_dead', False) and not nd['is_dead']:
                            if dp.get('name') != 'Unknown' and nd['name'] == dp.get('name'):
                                continue
                                 
                        # 1. Match ESATTO della classe (colore univoco nel gioco)
                        if nd['name'] != 'Unknown' and nd['name'] == dp.get('name'):
                            best_match = dp
                            break
                            
                        # 2. Fallback per classi Unknown
                        if nd['name'] == 'Unknown' or dp.get('name') == 'Unknown':
                            c_diff = abs(nd['color'][0] - dp['color'][0]) + \
                                     abs(nd['color'][1] - dp['color'][1]) + \
                                     abs(nd['color'][2] - dp['color'][2])
                            if dist < 0.8 or (c_diff < 60 and dist < 5.0) or c_diff < 40:
                                score = (dist * 10) + c_diff
                                if score < best_score:
                                    best_score = score
                                    best_match = dp
                                
                    if best_match:
                        best_match['x'] = nd['x']
                        best_match['y'] = nd['y']
                        best_match['time'] = nd['time']
                        best_match['is_dead'] = nd['is_dead']
                        
                        if best_match.get('name') == 'Unknown' and nd['name'] != 'Unknown':
                            best_match['name'] = nd['name']
                            best_match['color'] = nd['color']
                        elif best_match.get('name') == 'Unknown':
                            best_match['color'] = (
                                int((best_match['color'][0] * 0.7) + (nd['color'][0] * 0.3)),
                                int((best_match['color'][1] * 0.7) + (nd['color'][1] * 0.3)),
                                int((best_match['color'][2] * 0.7) + (nd['color'][2] * 0.3))
                            )
                    else:
                        self.detected_players.append(nd)

                # Pulizia fantasmi: se guardiamo un punto e il player non c'e' piu', lo facciamo sparire
                view_radius = 4.5
                if len(new_detections) < 10:
                    for dp in self.detected_players:
                        if not dp.get('is_dead', False):
                            dist_cam = math.hypot(dp['x'] - self.pos_target[0], dp['y'] - self.pos_target[1])
                            if dist_cam < view_radius:
                                if not any(math.hypot(nd['x'] - dp['x'], nd['y'] - dp['y']) < 1.5 for nd in new_detections):
                                    dp['time'] -= 5.0  # Invecchia rapidamente
                                    
                # Rimuovi player troppo vecchi (30s) per non saturare la memoria
                self.detected_players = [dp for dp in self.detected_players if current_time - dp['time'] < 30.0 or dp.get('is_dead', False)]

            # --- RILEVAMENTO PORTE CHIUSE ---
            if door_model:
                door_results = door_model(img, conf=0.80, verbose=False)
                door_boxes = door_results[0].boxes
                new_doors = []
                
                for box in door_boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    center_x = (x1 + x2) / 2
                    center_y = (y1 + y2) / 2
                    
                    dx = center_x - cx_screen
                    dy = center_y - cy_screen
                    
                    world_x = self.pos_target[0] + (dx / pixels_per_unit)
                    world_y = camera_world_y - (dy / pixels_per_unit)
                    
                    # Filtro zone valide per le porte per scartare falsi positivi YOLO
                    valid_zone = False
                    if not self.door_zone_mgr.zone:
                        valid_zone = True # Se non hai disegnato zone, le accetta tutte
                    else:
                        for dz in self.door_zone_mgr.zone:
                            if self._is_point_in_polygon(world_x, world_y, dz.get('punti', [])):
                                valid_zone = True
                                break
                    if not valid_zone:
                        continue

                    new_doors.append({'x': world_x, 'y': world_y, 'time': current_time})
                
                for nd in new_doors:
                    matched = False
                    for d in getattr(self, 'detected_doors', []):
                        if math.hypot(nd['x'] - d['x'], nd['y'] - d['y']) < 1.5:
                            d['x'] = nd['x']
                            d['y'] = nd['y']
                            d['time'] = current_time
                            matched = True
                            break
                    if not matched:
                        if not hasattr(self, 'detected_doors'):
                            self.detected_doors = []
                        self.detected_doors.append(nd)
                
                self.detected_doors = [d for d in getattr(self, 'detected_doors', []) if current_time - d['time'] < 1.0]
            
            # Pausa il thread per il tempo specificato (secondi)
            time.sleep(0.15)  # Circa ~6 FPS per lo scanning radar, per non appesantire la CPU
