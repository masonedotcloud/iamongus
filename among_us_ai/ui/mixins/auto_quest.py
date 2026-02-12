"""
Modalita' Auto-Quest: scelta automatica della prossima task.

Mixin di GPSVisualizerPro: metodi separati per organizzazione, ma
condividono lo stato self.* della classe principale.
"""

from ._imports import *



class AutoQuestMixin:
    """Mixin con i metodi di auto quest di GPSVisualizerPro."""
    def _toggle_auto_all(self):
        """Attiva o disattiva l'esecuzione automatica in loop di tutte le task."""
        self.auto_execute_all = not self.auto_execute_all
        if self.auto_execute_all:
            # Tema personalizzato (colori e spaziature)
            with dpg.theme() as th:
                with dpg.theme_component(dpg.mvButton):
                    dpg.add_theme_color(dpg.mvThemeCol_Text, (0, 255, 100, 255))
            dpg.bind_item_theme("btn_auto_all", th)
            # Cambia le configurazioni di un widget gia' creato
            dpg.configure_item("btn_auto_all", label="[X] Ferma Esecuzione Totale")
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Auto-All attivato: cerco task..."
            self._auto_all_timer = 1.0 # Forza il check immediato
        else:
            self._cancel_auto_move()
            self._ferma_processo_task()

    def _update_auto_all(self, dt):
        """Loop logico dell'Auto-Quest: sceglie e avvia la prossima task se libero."""
        if not self.auto_execute_all:
            return

        # Se il bot sta viaggiando verso una task, eseguendo una task o gestendo popup: aspetta
        if self.auto_path or self._task_process is not None or getattr(self, '_task_launch_arrivo', False):
            return
        # Se il widget esiste gia', lo rimuovo prima di ricrearlo
        if dpg.does_item_exist("task_launch_popup"):
            return

        self._auto_all_timer += dt
        if self._auto_all_timer < 1.0: # Check throttling (1 secondo)
            return
        self._auto_all_timer = 0.0

        if not self.memory_tasks:
            return

        enriched = self.task_mgr.get_memory_tasks_info(self.memory_tasks)
        candidati = []
        in_cooldown = 0
        non_registrate = 0

        for t in enriched:
            if t['done']: continue
            reg = t.get('reg_task')
            if not reg:
                non_registrate += 1
                continue
            rem = self.task_cooldowns.get(reg['id'], 0) - time.time()
            if rem > 0:
                in_cooldown += 1
                continue
            candidati.append(t)

        if not candidati:
            if non_registrate > 0:
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = f"Auto-All in attesa: {non_registrate} task NON registrate."
            elif in_cooldown > 0:
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = f"Auto-All in attesa: {in_cooldown} task in cooldown..."
            else:
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = "Tutte le task completate! Vittoria!"
                self._toggle_auto_all()
            return

        # Trova la task valida PIÙ VICINA
        cx, cy = self.pos_target
        closest = None
        min_dist = float('inf')
        for c in candidati:
            rx, ry = c['reg_task']['x'], c['reg_task']['y']
            dist = math.hypot(cx - rx, cy - ry)
            if dist < min_dist:
                min_dist = dist
                closest = c
                
        if closest:
            print(f"[Auto-All] Scelta task piu' vicina: {closest['reg_task']['nome']} (Dist: {min_dist:.1f})")
            self._avvia_task_selezionata(task_to_run=closest)

    def _check_2p_yolo_thread(self, current_target_is_A):
        """Esegue l'analisi YOLO asincrona per vedere se il pannello e' occupato da un altro player."""
        if getattr(self, '_2p_yolo_active', False): return
        self._2p_yolo_active = True
        try:
            import mss
            import numpy as np
            from ultralytics import YOLO
            import os
            import win32gui

            if not getattr(self, 'yolo_player_loaded', False):
                model_path = getattr(GPSConfig, 'YOLO_PLAYER_MODEL', 'yolo_players.pt')
                if os.path.exists(model_path):
                    self.yolo_player = YOLO(model_path)
                else:
                    self.yolo_player = None
                    print(f"[YOLO 2P] Modello non trovato: {model_path}")
                self.yolo_player_loaded = True

            if getattr(self, 'yolo_player', None) is None:
                self._2p_yolo_active = False
                return

            # Cerca la finestra del gioco per nome
            hwnd = win32gui.FindWindow(None, "Among Us")
            if not hwnd:
                self._2p_yolo_active = False
                return

            rect = win32gui.GetWindowRect(hwnd)
            crect = win32gui.GetClientRect(hwnd)
            bw = int((rect[2] - rect[0] - crect[2]) / 2)
            th = int(rect[3] - rect[1] - crect[3] - bw)
            wx, wy = rect[0] + bw, rect[1] + th
            ww, wh = crect[2], crect[3]

            # Cattura uno screenshot della regione del gioco
            with mss.mss() as sct:
                monitor = {"top": wy, "left": wx, "width": ww, "height": wh}
                img = np.array(sct.grab(monitor))[:, :, :3]

            results = self.yolo_player(img, conf=0.75, verbose=False)
            boxes = results[0].boxes

            # Cerca player che non siamo noi (il nostro player e' al centro dello schermo)
            other_players_found = False
            cx_screen, cy_screen = ww / 2, wh / 2

            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                px = (x1 + x2) / 2
                py = (y1 + y2) / 2

                # Tolleranza di 70px dal centro; se e' oltre, e' sicuramente un altro giocatore
                dist_from_center = math.hypot(px - cx_screen, py - cy_screen)
                if dist_from_center > 70:
                    other_players_found = True
                    break

            if other_players_found:
                new_target = self.auto_2p_loc_B if current_target_is_A else self.auto_2p_loc_A
                
                if new_target and new_target != self.auto_2p_current_target:
                    self.auto_2p_current_target = new_target
                    self._pending_2p_replan = new_target
                    print(f"[YOLO 2P] Player rilevato al pannello! Spostamento alla seconda postazione.")

        except Exception as e:
            print(f"[YOLO 2P] Errore: {e}")
        finally:
            self._2p_yolo_active = False

    def _imposta_navigazione_2p(self, reg):
        """
        Prepara la logica di navigazione per le task a 2 giocatori. 
        Ritorna la coordinata (x,y) iniziale ottimale (la piu' vicina).
        """
        self.auto_is_2p_task = False
        if reg.get('due_giocatori'):
            loc_A = (reg['x'], reg['y'])
            loc_B = None
            if reg.get('fasi') and len(reg['fasi']) > 0:
                loc_B = (reg['fasi'][0]['x'], reg['fasi'][0]['y'])

            if loc_B:
                self.auto_is_2p_task = True
                self.auto_2p_loc_A = loc_A
                self.auto_2p_loc_B = loc_B
                self._2p_last_switch_time = 0.0

                start_pos = (self.pos_target[0], self.pos_target[1])
                
                # Calcola il percorso reale (A*) per capire quale e' effettivamente piu' vicino
                path_A = self.pathfinder.astar(start_pos, loc_A)
                # Calcolo del percorso A* da start a goal
                path_B = self.pathfinder.astar(start_pos, loc_B)
                
                def calc_len(p):
                    """Calcola la lunghezza del percorso restante per la task."""
                    if not p: return float('inf')
                    if len(p) < 2: return 0.0
                    return sum(math.hypot(p[i+1][0]-p[i][0], p[i+1][1]-p[i][1]) for i in range(len(p)-1))
                
                dist_A = calc_len(path_A)
                dist_B = calc_len(path_B)

                if dist_A <= dist_B and dist_A != float('inf'):
                    target = loc_A
                    step = 0
                elif dist_B < float('inf'):
                    target = loc_B
                    step = 1
                else:
                    # Fallback alla distanza in linea d'aria se non ancora mappato
                    d_A = math.hypot(start_pos[0]-loc_A[0], start_pos[1]-loc_A[1])
                    d_B = math.hypot(start_pos[0]-loc_B[0], start_pos[1]-loc_B[1])
                    target = loc_A if d_A <= d_B else loc_B
                    step = 0 if target == loc_A else 1
                    
                self.auto_2p_current_target = target
                return target, step
        return None, None

    def _get_task_target_coords(self, reg_task):
        """
        Calcola la coordinata bersaglio esatta di una task in base allo step 
        registrato in memoria (es: se siamo a 1/2, naviga alla fase 0).
        Ritorna (x, y, step).
        """
        x, y = reg_task['x'], reg_task['y']
        step = 0
        # Cerca lo step attuale in RAM
        for mt in getattr(self, 'memory_tasks', []):
            if mt.get('tipo') == reg_task.get('tipo') and mt.get('id_stanza') == reg_task.get('id_stanza'):
                try:
                    step = int(mt['prog'].split('/')[0])
                except: pass
                break
                
        fasi = reg_task.get('fasi', [])
        # Se lo step e' maggiore di 0 e c'e' una fase mappata corrispondente
        if step > 0 and step <= len(fasi):
            x, y = fasi[step - 1]['x'], fasi[step - 1]['y']
            
        return x, y, step
