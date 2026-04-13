"""
Pathfinding A*, esecuzione del cammino, anti-stuck e replan.

Mixin di GPSVisualizerPro: metodi separati per organizzazione, ma
condividono lo stato self.* della classe principale.
"""

from ._imports import *



class AutoMoveMixin:
    """Mixin con i metodi di auto move di GPSVisualizerPro."""
    def _plan_path(self, goal_xy):
        """Calcola A* assicurandosi che il target sia su una cella calpestabile."""
        # SNAP: Trova la cella calpestabile piu' vicina al click/centroide
        snapped_goal_key = self.pathfinder.nearest_walkable(goal_xy[0], goal_xy[1], GPSConfig.NEAREST_SEARCH_RADIUS)
        
        if snapped_goal_key is None:
            self.auto_path = []
            self.auto_path_index = 0
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Punto irraggiungibile (non mappato)"
            self.key_ctrl.release_all()
            return

        # Usa le coordinate della cella reale come target finale
        actual_goal = self.pathfinder._coord(snapped_goal_key)
        self.auto_final_target = actual_goal 
        
        start = (self.pos_target[0], self.pos_target[1])
        t0 = time.time()

        # === Cost map per "evita player sospetti" ===
        # Se l'utente ha attivato l'opzione (checkbox nella sidebar F2)
        # E il sistema intelligence e' attivo, costruisco un dict di
        # penalita' extra che fa "girare attorno" ai player sospetti.
        extra_penalties = None
        if (getattr(self, '_avoid_suspects', False)
                and getattr(self, '_intelligence_enabled', False)):
            try:
                from ..intelligence import build_avoidance_cost_map
                scores = self._intelligence_suspicion.analyze_all(
                    self._intelligence_tracker,
                    self._intelligence_activity,
                    self._intelligence_proximity,
                    self._intelligence_task_inf,
                )
                extra_penalties = build_avoidance_cost_map(
                    scores, self._intelligence_tracker,
                    min_score=40.0, radius=3.0, max_penalty=15.0,
                )
            except Exception as e:
                print(f"[Intelligence] Errore build cost map: {e}",
                      flush=True)
                extra_penalties = None

        # Calcola il percorso verso il punto "snappato"
        path = self.pathfinder.astar(
            start, actual_goal,
            max_nodes=GPSConfig.ASTAR_MAX_NODES,
            extra_penalties=extra_penalties,
        )
        elapsed_ms = (time.time() - t0) * 1000

        if not path:
            self.auto_path = []
            self.auto_path_index = 0
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "In attesa (percorso bloccato)..."
            self.key_ctrl.release_all()
            return

        # Aggiungo il goal esatto come ultimo waypoint (per precisione finale
        # rispetto alla cella piu' vicina) SOLO se e' raggiungibile in linea
        # retta dal goal snapped - altrimenti il bot tenta di camminare nel
        # muro per arrivarci e va in loop di stuck/replan.
        if path:
            last = path[-1]
            dist_extra = math.hypot(last[0] - goal_xy[0], last[1] - goal_xy[1])
            # Verifica se la linea e' tutta in zone calpestabili
            if 0.05 < dist_extra < 1.0 and self.pathfinder.line_walkable_coords(last, goal_xy):
                path.append(goal_xy)

        self.auto_path = path
        self.auto_path_index = 0
        self.auto_stuck_pos = tuple(self.pos_target)
        self.auto_stuck_timer = 0.0
        # Messaggio di stato mostrato all'utente nel pannello
        self.auto_status_msg = f"Path: {len(path)} wp ({elapsed_ms:.0f}ms)"

    def _toggle_auto_enabled(self):
        """Inverte lo stato di auto enabled."""
        self.auto_enabled = not self.auto_enabled
        # Se il widget esiste gia', lo rimuovo prima di ricrearlo
        if dpg.does_item_exist("auto_checkbox"):
            # Aggiorna il valore di un widget DPG
            dpg.set_value("auto_checkbox", self.auto_enabled)
        if not self.auto_enabled:
            self._cancel_auto_move(silent=True)
        else:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Pronto: clicca sulla mappa"

    def _cancel_auto_move(self, silent=False, stop_auto_all=True):
        """Annulla auto move."""
        self.auto_final_target = None
        self.auto_path = []
        self.auto_path_index = 0
        self.auto_is_2p_task = False
        self._task_alternativi_pendenti = None
        self.key_ctrl.release_all()

        # Se c'e' un subprocess pre-warmed in attesa, killalo: l'utente
        # ha cancellato la task prima dell'arrivo, il subprocess non
        # serve piu' (resterebbe appeso in attesa del "GO").
        if (getattr(self, '_task_prewarm_id', None) is not None
                and self._task_process is not None
                and self._task_process.poll() is None):
            try:
                self._task_process.terminate()
            except Exception:
                pass
            self._task_process = None
            self._task_process_task_id = None
            self._task_prewarm_id = None

        if stop_auto_all:
            self.auto_execute_all = False
            self._current_auto_all_task_id = None
            # Se il widget esiste gia', lo rimuovo prima di ricrearlo
            if dpg.does_item_exist("btn_auto_all"):
                # Tema personalizzato (colori e spaziature)
                with dpg.theme() as th:
                    with dpg.theme_component(dpg.mvButton):
                        dpg.add_theme_color(dpg.mvThemeCol_Text, Colors.TEXT)
                dpg.bind_item_theme("btn_auto_all", th)
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item("btn_auto_all", label="> Esegui TUTTE le Task")

        if not silent:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Annullato"

    def _cancel_all(self):
        """Annulla sia il disegno/modifica zona sia il pathfinding."""
        if (self.zone_draw_mode or self.zone_draw_points
                or getattr(self, 'door_rect_start', None)
                or self.zona_in_modifica is not None):
            self.zone_draw_mode = False
            self.zone_draw_type = "normal"
            self.zone_draw_points = []
            self.door_rect_start = None
            self.door_rect_end = None
            self.zone_last_pixel = None
            self.zona_in_modifica = None
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Disegno zona annullato"
        self._cancel_auto_move()

    def _update_auto_move(self, dt):
        """Aggiorna a ogni frame auto move."""
        # --- Aggiornamento ostacoli dinamici (Porte) ---
        if hasattr(self, 'pathfinder'):
            self.pathfinder.dynamic_obstacles.clear()
            current_time = time.time()
            for d in getattr(self, 'detected_doors', []):
                if current_time - d['time'] < 1.0:
                    door_key = self.pathfinder._key(d['x'], d['y'])
                    r = int(1.2 / self.pathfinder.step) # Raggio blocco porta
                    for dx in range(-r, r+1):
                        for dy in range(-r, r+1):
                            if math.hypot(dx, dy) <= r:
                                self.pathfinder.dynamic_obstacles.add((door_key[0]+dx, door_key[1]+dy))

        if (not self.auto_enabled) or (not self.auto_path):
            if self.key_ctrl.pressed:
                self.key_ctrl.release_all()
            
            # Replan periodico se in attesa (es. percorso bloccato)
            if self.auto_enabled and getattr(self, 'auto_final_target', None):
                self.auto_stuck_timer += dt
                if self.auto_stuck_timer > 1.0:
                    self._plan_path(self.auto_final_target)
                    self.auto_stuck_timer = 0.0
            return

        # --- Controllo Finestra in Primo Piano ---
        if _WIN_OK:
            # Cerca la finestra del gioco per nome
            hwnd_au = win32gui.FindWindow(None, "Among Us")
            # Ottiene l'handle della finestra in primo piano
            if hwnd_au and win32gui.GetForegroundWindow() != hwnd_au:
                if self.key_ctrl.pressed:
                    self.key_ctrl.release_all()
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = "In pausa (Focus su altra finestra)"
                return

        cx, cy = self.pos_target
        
        # Replan if current path hits a door
        if self.auto_path:
            path_blocked = False
            start_point = (cx, cy)
            for i in range(self.auto_path_index, len(self.auto_path)):
                wp = self.auto_path[i]
                if self.pathfinder.line_has_dynamic_obstacle(start_point, wp):
                    path_blocked = True
                    break
                start_point = wp
            
            if path_blocked:
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = "Percorso bloccato da porta, ricalcolo..."
                self._plan_path(self.auto_final_target)
                if not self.auto_path:
                    if getattr(self, 'auto_execute_all', False) and getattr(self, '_current_auto_all_task_id', None):
                        tid = self._current_auto_all_task_id
                        self.task_cooldowns[tid] = time.time() + 15.0
                        # Messaggio di stato mostrato all'utente nel pannello
                        self.auto_status_msg = "Task isolata da porte chiuse, cambio task..."
                        self._cancel_auto_move(silent=True, stop_auto_all=False)
                        # Se il widget esiste gia', lo rimuovo prima di ricrearlo
                        if dpg.does_item_exist("task_launch_popup"):
                            # Rimuove l'elemento DPG (cleanup)
                            dpg.delete_item("task_launch_popup")
                    return

        # --- Controllo Radar per task 2P ---
        if getattr(self, 'auto_is_2p_task', False):
            target_x, target_y = self.auto_2p_current_target
            dist_to_target = math.hypot(cx - target_x, cy - target_y)
            
            # Controlliamo solo se siamo nel raggio visivo (circa 5 mattonelle) e switch in cooldown
            if dist_to_target < 5.0 and (time.time() - getattr(self, '_2p_last_switch_time', 0) > 3.0):
                occupato = False
                current_time = time.time()
                for p in self.detected_players:
                    # Ignora cadaveri
                    if p.get('is_dead', False): 
                        continue
                    # Considera SOLO avvistamenti in tempo reale (max 0.5 secondi fa)
                    if current_time - p['time'] > 0.5: 
                        continue
                    # Se un giocatore vivo e' a meno di 1.2 unita' dalla postazione della task
                    if math.hypot(p['x'] - target_x, p['y'] - target_y) < 1.2:
                        occupato = True
                        break
                
                if occupato:
                    pending = getattr(self, 'auto_2p_pending_locs', [])
                    if len(pending) > 1:
                        for step, loc in pending:
                            if loc != self.auto_2p_current_target:
                                self.auto_2p_current_target = loc
                                self.auto_2p_current_step = step
                                self._2p_last_switch_time = time.time()
                                self._plan_path(loc)
                                # Messaggio di stato mostrato all'utente nel pannello
                                self.auto_status_msg = f"Player al pannello! Cambio a tappa {step}."
                                return

        # --- Controllo Visuale Dinamico per i Alternativi ---
        pendenti = getattr(self, '_task_alternativi_pendenti', None)
        if pendenti and len(pendenti) > 1:
            lock_target = self._cerca_glow_alternativi(pendenti)
            if lock_target:
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = "Task individuata visivamente! Lock acquisito."
                print(f"[VisualLock] Alone giallo rilevato a {lock_target}! Aggiorno il path.")
                self._current_nav_target = lock_target
                self._task_alternativi_pendenti = None # Lock acquisito
                self.auto_final_target = lock_target
                self._plan_path(lock_target)
                return

        # Waypoint corrente
        wx, wy = self.auto_path[self.auto_path_index]
        dx = wx - cx
        dy = wy - cy
        dist = math.hypot(dx, dy)

        is_last = (self.auto_path_index == len(self.auto_path) - 1)
        advance_th = (GPSConfig.AUTO_ARRIVAL_THRESHOLD
                      if is_last else GPSConfig.WAYPOINT_ADVANCE)

        # ================= 1. ANTICIPAZIONE DELLA CURVA (Lookahead Umano) =================
        # Se non e' l'ultimo waypoint e ci stiamo avvicinando all'angolo
        if not is_last and dist < 0.75:
            next_wx, next_wy = self.auto_path[self.auto_path_index + 1]
            # Verifica se la linea e' tutta in zone calpestabili
            if self.pathfinder.line_walkable_coords((cx, cy), (next_wx, next_wy)):
                self.auto_path_index += 1
                return  # Salta al prossimo ciclo per ricalcolare la curva fluida

        # Avanzamento waypoint standard
        if dist < advance_th:
            if is_last:
                # === FINAL NUDGE: ultimi centimetri per arrivare nel raggio
                # di attivazione del pulsante Use del gioco ===
                #
                # === MICRO-NUDGE ITERATIVO + CHECK PULSANTE USE ===
                #
                # Il pathfinding lascia un piccolo margine (advance_th =
                # AUTO_ARRIVAL_THRESHOLD) per evitare di "incollarsi" al
                # target. Pero' a volte questo margine e' troppo grande e
                # il bot non entra nel raggio di interazione del gioco
                # (il pulsante Use non si illumina).
                #
                # Strategia:
                #   1) Se la calibrazione del pulsante Use e' presente,
                #      controlla se gia' acceso. Se SI -> lancia subito.
                #   2) Altrimenti fai un micro-nudge WASD verso il target
                #      e ricontrolla. Ripeti fino a USE_BUTTON_MAX_NUDGES.
                #   3) Se la calibrazione manca o ancora spento dopo N
                #      tentativi -> fai il nudge fisso classico
                #      (AUTO_FINAL_NUDGE_SEC) e lancia la task comunque.
                self._do_arrival_nudge(cx, cy)

                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = "Arrivato OK"
                self._cancel_auto_move(silent=True, stop_auto_all=False)
                # Esegui callback di arrivo (es. avvio subprocess task)
                if self._on_arrival_callback is not None:
                    cb = self._on_arrival_callback
                    self._on_arrival_callback = None
                    cb()
                return
            self.auto_path_index += 1
            self.auto_stuck_pos = (cx, cy)
            self.auto_stuck_timer = 0.0
            return

        # Stuck detection
        if self.auto_stuck_pos is None:
            self.auto_stuck_pos = (cx, cy)
        moved = math.hypot(cx - self.auto_stuck_pos[0],
                           cy - self.auto_stuck_pos[1])
        if moved > GPSConfig.AUTO_STUCK_DELTA:
            self.auto_stuck_pos = (cx, cy)
            self.auto_stuck_timer = 0.0
        else:
            self.auto_stuck_timer += dt
            if self.auto_stuck_timer > GPSConfig.AUTO_STUCK_TIME:
                if GPSConfig.AUTO_REPLAN_ON_STUCK and self.auto_final_target:
                    # Messaggio di stato mostrato all'utente nel pannello
                    self.auto_status_msg = "Bloccato - replan"
                    self.key_ctrl.release_all()
                    self._plan_path(self.auto_final_target)
                    return
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = "Bloccato - stop"
                self._cancel_auto_move(silent=True)
                return

        move_x = 0
        move_y = 0

        # ================= 2. MOVIMENTO FLUIDO (PWM Direzionale) =================
        # Per evitare l'effetto "onde" (zig-zag) sulle diagonali, premiamo 
        # sempre l'asse principale al 100% e "tappiamo" l'asse secondario in 
        # proporzione all'angolo (Pulse Width Modulation).
        
        if dist > 0:
            vx = dx / dist
            vy = dy / dist
            
            # Normalizziamo affinche' l'asse maggiore sia esattamente 1.0
            max_v = max(abs(vx), abs(vy))
            if max_v > 0:
                vx /= max_v
                vy /= max_v
                
            freq = 25.0  # Frequenza del tap (25 Hz = micro-correzioni fluide)
            phase = (time.time() * freq) % 1.0
            
            stop_th = 0.03  # Tolleranza finale per fermarsi perfettamente
            
            if abs(dx) > stop_th:
                if abs(vx) >= 1.0 or abs(vx) > phase:
                    move_x = 1 if dx > 0 else -1
                    
            if abs(dy) > stop_th:
                if abs(vy) >= 1.0 or abs(vy) > phase:
                    move_y = 1 if dy > 0 else -1

        # Wiggle anti-incastro
        if self.auto_stuck_timer > 0.3:
            if int(self.auto_stuck_timer * 15) % 2 == 0:
                # Forza movimento trasversale casuale per sbloccarsi dall'angolo
                if move_x != 0 and move_y == 0:
                    move_y = 1 if random.random() < 0.5 else -1
                elif move_y != 0 and move_x == 0:
                    move_x = 1 if random.random() < 0.5 else -1
                else:
                    move_x = -move_x if random.random() < 0.5 else move_x
                    move_y = -move_y if random.random() < 0.5 else move_y

        # ================= 3. SCIVOLAMENTO SUI MURI =================
        def is_safe(offset_x, offset_y):
            """Ritorna se safe."""
            test_x = cx + offset_x
            test_y = cy + offset_y
            key = self.pathfinder._key(test_x, test_y)
            # Aggiungiamo spessore per non tagliare troppo i muri (hitbox)
            ox_range = (0, 1) if offset_x > 0 else ((0, -1) if offset_x < 0 else (0,))
            oy_range = (0, 1) if offset_y > 0 else ((0, -1) if offset_y < 0 else (0,))
            for ox in ox_range:
                for oy in oy_range:
                    if (key[0]+ox, key[1]+oy) not in self.pathfinder.walkable:
                        return False
            return True

        # Se la mossa calcolata ci manda a sbattere, proviamo a muoverci solo su un asse (sliding)
        if move_x != 0 or move_y != 0:
            step_check = 0.25 # Aumentato da 0.15 per rilevare i muri prima
            if not is_safe(move_x * step_check, move_y * step_check):
                if move_x != 0 and is_safe(move_x * step_check, 0):
                    move_y = 0
                elif move_y != 0 and is_safe(0, move_y * step_check):
                    move_x = 0
                else:
                    self.auto_stuck_timer += dt * 1.5 
            
        # Assegna i tasti finali
        want = set()
        if move_x == 1: want.add('D')
        elif move_x == -1: want.add('A')
        if move_y == 1: want.add('W')
        elif move_y == -1: want.add('S')

        current = set(self.key_ctrl.pressed)
        for k in want - current:  self.key_ctrl.press(k)
        for k in current - want:  self.key_ctrl.release(k)

        total_wp = len(self.auto_path)
        # Messaggio di stato mostrato all'utente nel pannello
        self.auto_status_msg = (f"wp {self.auto_path_index+1}/{total_wp}  "
                                f"d={dist:.2f}")

    def _do_arrival_nudge(self, cx, cy):
        """
        Esegue il "nudge finale" per arrivare nel raggio di attivazione
        del pulsante Use del gioco.

        Strategia:
          1) Se la calibrazione del pulsante Use e' presente e
             USE_BUTTON_CHECK_ENABLED=True:
             - Controlla periodicamente il pulsante Use
             - Se acceso -> esci (massima precisione raggiunta)
             - Se spento -> fa un micro-nudge WASD verso il target
                            (MICRO_NUDGE_DURATION_SEC) e ricontrolla
             - Ripete fino a USE_BUTTON_MAX_NUDGES
          2) Altrimenti (o calibrazione mancante o ancora spento dopo
             N tentativi): fa il nudge fisso classico
             (AUTO_FINAL_NUDGE_SEC) come fallback.

        Parametri
        ---------
        cx, cy : float
            Posizione attuale del giocatore (mondo, non schermo). Usata
            per calcolare la direzione del nudge verso `auto_final_target`.
        """
        target = getattr(self, 'auto_final_target', None)
        if not target:
            return

        # Direzione corrente verso il target (in coordinate mondo)
        def _calc_nudge_keys(_cx, _cy):
            tx, ty = target
            dx, dy = tx - _cx, ty - _cy
            keys = set()
            if   dx >  0.05: keys.add('D')
            elif dx < -0.05: keys.add('A')
            if   dy >  0.05: keys.add('W')
            elif dy < -0.05: keys.add('S')
            return keys

        # Helper per cattura del client rect del gioco (in coordinate
        # schermo). Necessaria per il check del pulsante Use.
        def _client_rect():
            try:
                hwnd = win32gui.FindWindow(None, "Among Us")
                if not hwnd:
                    return None
                rect = win32gui.GetClientRect(hwnd)
                pt = win32gui.ClientToScreen(hwnd, (rect[0], rect[1]))
                cx_s, cy_s = pt
                cw_s, ch_s = rect[2], rect[3]
                return (cx_s, cy_s, cw_s, ch_s)
            except Exception:
                return None

        # === FASE 1: tentativi iterativi con check pulsante Use ===
        check_enabled = getattr(GPSConfig, 'USE_BUTTON_CHECK_ENABLED', False)
        max_nudges = int(getattr(GPSConfig, 'USE_BUTTON_MAX_NUDGES', 10))
        nudge_dur = float(getattr(GPSConfig, 'MICRO_NUDGE_DURATION_SEC', 0.05))

        if check_enabled:
            try:
                from ...execution.use_button import is_lit, carica_calibrazione
                calib = carica_calibrazione()
            except Exception:
                calib = None

            if calib is not None and calib.get('calibrated', False):
                # Per ridurre overhead apriamo mss una sola volta in tutti
                # i check (cattura ROI veloce).
                import mss as _mss
                with _mss.mss() as sct:
                    # Check iniziale: forse siamo gia' nel raggio
                    rect = _client_rect()
                    if rect:
                        lit = is_lit(rect, calib, sct_optional=sct)
                        if lit:
                            print("[Arrival] Pulsante Use gia' acceso "
                                  "all'arrivo, no nudge necessario.")
                            return

                    # Loop di micro-nudge
                    for attempt in range(1, max_nudges + 1):
                        # Posizione corrente (puo' essere cambiata dai
                        # nudge precedenti)
                        pos = self.pos_target if self.pos_target else (cx, cy)
                        keys = _calc_nudge_keys(pos[0], pos[1])
                        if not keys:
                            # Esattamente sul target - non servono altri
                            # nudge, usciamo.
                            break

                        # Esegui micro-nudge
                        self.key_ctrl.release_all()
                        for k in keys:
                            self.key_ctrl.press(k)
                        time.sleep(nudge_dur)
                        self.key_ctrl.release_all()

                        # Ricontrolla pulsante
                        rect = _client_rect()
                        if rect:
                            lit = is_lit(rect, calib, sct_optional=sct)
                            if lit:
                                print(f"[Arrival] Pulsante Use acceso "
                                      f"dopo {attempt} micro-nudge.")
                                return

                    # Esauriti i tentativi senza accendere il pulsante.
                    # Non blocchiamo: lanciamo la task comunque (best-effort).
                    print(f"[Arrival] Esauriti {max_nudges} micro-nudge, "
                          f"pulsante Use ancora spento. Lancio comunque.")
                    return

        # === FASE 2: fallback nudge fisso (calibrazione mancante o
        # disabilitata) - nudge fisso classico ===
        nudge_sec = getattr(GPSConfig, 'AUTO_FINAL_NUDGE_SEC', 0.0)
        if nudge_sec > 0:
            tx, ty = target
            fdx, fdy = tx - cx, ty - cy
            fdist = math.hypot(fdx, fdy)
            if fdist > 0.05:
                keys = _calc_nudge_keys(cx, cy)
                if keys:
                    self.key_ctrl.release_all()
                    for k in keys:
                        self.key_ctrl.press(k)
                    time.sleep(nudge_sec)
                    self.key_ctrl.release_all()
