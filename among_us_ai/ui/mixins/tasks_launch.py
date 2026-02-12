"""
Avvio di una task: animazione di lancio, decisione del file da eseguire, glow-detection sui alternativi.

Mixin di GPSVisualizerPro.
"""

from ._imports import *


class TasksLaunchMixin:
    """Mixin con i metodi di tasks launch di GPSVisualizerPro."""
    def _avvia_task_selezionata(self, task_to_run=None):
        """
        Flusso coerente in 3 fasi:
          FASE 1 - Predisposizione (immediata):
            Crea/verifica il file .py, mostra popup con log di setup,
            poi avvia la navigazione A* verso la task.
          FASE 2 - In viaggio:
            Il popup rimane aperto e mostra "In viaggio verso X...".
            Il player cammina automaticamente verso la task.
          FASE 3 - Arrivo + Esecuzione:
            Appena il player arriva, il popup aggiorna con gli step di lancio
            (animazione breve), poi avvia il subprocess e si chiude.
        """
        t = task_to_run if task_to_run is not None else self._get_selected_mem_task()
        if t is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una task da avviare"
            return

        nome    = t['nome']
        reg     = t.get('reg_task')
        id_task = reg['id'] if reg else None

        if reg is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"'{nome}' non registrata - aggiungila prima"
            return
            
        self._current_auto_all_task_id = id_task
            
        # Controllo Cooldown
        rem = self.task_cooldowns.get(id_task, 0) - time.time()
        if rem > 0:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"Task in cooldown. Riprova tra {int(rem)}s"
            return

        tag = "task_launch_popup"
        # Se il widget esiste gia', lo rimuovo prima di ricrearlo
        if dpg.does_item_exist(tag):
            # Rimuove l'elemento DPG (cleanup)
            dpg.delete_item(tag)

        # ── FASE 1: predisposizione (sincrona, prima di aprire il popup) ──
        filepath, pred_log = self.task_mgr.predisponi_esecuzione(id_task)

        # Avvia navigazione A*
        if not self.auto_enabled:
            self.auto_enabled = True
            # Se il widget esiste gia', lo rimuovo prima di ricrearlo
            if dpg.does_item_exist("auto_checkbox"):
                # Aggiorna il valore di un widget DPG
                dpg.set_value("auto_checkbox", True)
        
        target_2p, step_2p = self._imposta_navigazione_2p(reg)
        if target_2p:
            self._plan_path(target_2p)
        else:
            punti_possibili = [(reg['x'], reg['y'])]
            for fr in reg.get('alternativi', []):
                punti_possibili.append((fr['x'], fr['y']))
                
            if len(punti_possibili) > 1:
                self._task_alternativi_pendenti = punti_possibili
                cx, cy = self.pos_target
                closest = min(punti_possibili, key=lambda p: math.hypot(cx - p[0], cy - p[1]))
                tx, ty = closest
            else:
                self._task_alternativi_pendenti = None
                tx, ty, step = self._get_task_target_coords(reg)
                
            self._plan_path((tx, ty))

        # ── Apri popup con log di setup + messaggio "in viaggio" ──
        setup_lines = "\n".join(pred_log)
        viaggio_txt = f"{setup_lines}\n\n>> Navigazione verso '{nome}'...\n>> In attesa di arrivo..."

        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()

        with dpg.window(label=f"Task: {nome}", tag=tag,
                        modal=True, no_resize=True, no_collapse=True,
                        no_close=True,
                        width=440, height=260,
                        pos=(max(0, vp_w // 2 - 220),
                             max(0, vp_h // 2 - 130))):
            dpg.add_text(viaggio_txt, tag="task_launch_popup_text",
                         color=(0, 200, 255, 255), wrap=420)

        # Disabilita l'animazione a step (il popup e' gia' pieno di testo)
        self.task_launch_active = False
        self._task_launch_nome  = nome
        self._task_launch_id    = id_task
        self._task_fallback_idx = 0

        # ── FASE 2->3: callback all'arrivo ──
        def on_arrivo():
            """Chiamato da _update_auto_move quando il player raggiunge la task."""
            # Verifica se l'elemento DPG e' gia' stato creato
            if not dpg.does_item_exist("task_launch_popup_text"):
                self._avvia_subprocess_task(id_task)
                return

            # Pausa il thread per il tempo specificato (secondi)
            time.sleep(0.3) # pausa per stabilita' visiva (frame capture screen)

            # --- CHECK VISUALE (Use Button / Alone Giallo) ---
            curr_target = getattr(self, '_current_nav_target', (tx, ty))
            if not self._controlla_task_attiva(curr_target[0], curr_target[1]):
                alternativi = reg.get('alternativi', [])
                curr_alternativo = getattr(self, '_task_alternativo_idx', 0)
                if curr_alternativo < len(alternativi):
                    next_target = (alternativi[curr_alternativo]['x'], alternativi[curr_alternativo]['y'])
                    self._task_alternativo_idx = curr_alternativo + 1
                    # Messaggio di stato mostrato all'utente nel pannello
                    self.auto_status_msg = f"Task non attiva qui, navigo al alternativo {self._task_alternativo_idx}..."
                    print(f"[Visual Check] Niente USE o alone giallo. Navigo a alternativo: {next_target}")
                    self._current_nav_target = next_target
                    self._plan_path(next_target)
                    self._on_arrival_callback = on_arrivo
                    return
                else:
                    print(f"[Visual Check] Nessun alternativo rimanente o tutti inattivi, procedo comunque.")

            # Aggiorna popup con gli step di lancio animati
            self._task_launch_steps     = (TaskManager.STATI_LAUNCH
                                           + [f">> '{nome}' IN ESECUZIONE *"])
            self._task_launch_timer_arr = 0.0
            self._task_launch_arrivo    = True  # flag: siamo in fase 3
            # Cambia le configurazioni di un widget gia' creato
            dpg.configure_item("task_launch_popup_text", color=(0, 220, 120, 255))
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"Arrivato a '{nome}' - avvio in corso..."

        self._current_nav_target = target_2p if target_2p else (tx, ty)
        self._task_alternativo_idx = 0
        self._on_arrival_callback   = on_arrivo
        self._task_launch_arrivo    = False
        self._task_launch_timer_arr = 0.0
        # Messaggio di stato mostrato all'utente nel pannello
        self.auto_status_msg        = f"In viaggio verso '{nome}'..."

    def _update_task_launch(self, dt):
        """
        Gestisce l'animazione del popup nelle due fasi attive:
        - Fase 3 (arrivo): anima gli step di lancio e poi avvia il subprocess.
        (La fase 1 popola il popup in modo statico, nessuna animazione.)
        """
        if not getattr(self, '_task_launch_arrivo', False):
            return

        self._task_launch_timer_arr += dt
        steps    = self._task_launch_steps
        interval = 0.4
        idx      = min(int(self._task_launch_timer_arr / interval), len(steps))

        log_text = "\n".join(steps[:idx])
        # Se il widget esiste gia', lo rimuovo prima di ricrearlo
        if dpg.does_item_exist("task_launch_popup_text"):
            # Aggiorna il valore di un widget DPG
            dpg.set_value("task_launch_popup_text", log_text)

        # Dopo aver mostrato tutti gli step + 1s di pausa: avvia subprocess e chiudi
        close_at = len(steps) * interval + 1.0
        if self._task_launch_timer_arr >= close_at:
            self._task_launch_arrivo = False
            # Se il widget esiste gia', lo rimuovo prima di ricrearlo
            if dpg.does_item_exist("task_launch_popup"):
                # Rimuove l'elemento DPG (cleanup)
                dpg.delete_item("task_launch_popup")

            # --- PREMUTA DELLA BARRA SPAZIATRICE ---
            # Simula la pressione di SPAZIO per far aprire il minigioco.
            try:
                # Invia un evento tastiera a livello scan-code (DirectInput)
                _send_scan(SCAN_CODES['SPACE'], keyup=False)
                # Pausa il thread per il tempo specificato (secondi)
                time.sleep(0.05)
                # Invia un evento tastiera a livello scan-code (DirectInput)
                _send_scan(SCAN_CODES['SPACE'], keyup=True)
            except Exception as e:
                print(f"[Input] Errore pressione SPAZIO: {e}")
            # ---------------------------------------

            id_task = getattr(self, '_task_launch_id', None)
            if id_task is not None:
                self._avvia_subprocess_task(id_task)

    def _esegui_generazione_py(self, t):
        """Esegue generazione py."""
        # Genera (o ri-genera) il file .py autonomo della task
        filepath = self.task_mgr.crea_file_esecuzione(t['id'])

        if filepath:
            filename = os.path.basename(filepath)
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"File creato: {filename}"
            # Se il widget esiste gia', lo rimuovo prima di ricrearlo
            if dpg.does_item_exist("genera_py_status"):
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item("genera_py_status", color=(0, 220, 120, 255))
                # Aggiorna il valore di un widget DPG
                dpg.set_value("genera_py_status", f"OK {filename}")
            # Aggiorna anche il riferimento nel JSON (exec_info['file'])
            exec_info = t.setdefault('esecuzione', {
                'file': None, 'stato': 'idle', 'params': {}
            })
            exec_info['file'] = filepath
            # Salva il registro delle task su disco
            self.task_mgr.salva()
        else:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Errore creazione file .py"
            # Se il widget esiste gia', lo rimuovo prima di ricrearlo
            if dpg.does_item_exist("genera_py_status"):
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item("genera_py_status", color=(255, 80, 80, 255))
                # Aggiorna il valore di un widget DPG
                dpg.set_value("genera_py_status", "X errore")

    def _genera_file_esecuzione(self):
        """
        Genera (o rigenera) il file .py di esecuzione per la task registrata
        selezionata nella listbox. Mostra feedback inline accanto al pulsante.
        """
        t = self._get_selected_reg_task()
        if t is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una task registrata"
            # Se il widget esiste gia', lo rimuovo prima di ricrearlo
            if dpg.does_item_exist("genera_py_status"):
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item("genera_py_status", color=(255, 100, 80, 255))
                # Aggiorna il valore di un widget DPG
                dpg.set_value("genera_py_status", "<- seleziona prima")
            return

        azioni_eff, src_id = self.task_mgr.get_azioni_effettive(t['id'])
        if src_id is not None and src_id != t['id']:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"La task eredita il file dal padre [{src_id}]"
            # Se il widget esiste gia', lo rimuovo prima di ricrearlo
            if dpg.does_item_exist("genera_py_status"):
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item("genera_py_status", color=(255, 180, 100, 255))
                # Aggiorna il valore di un widget DPG
                dpg.set_value("genera_py_status", f"Eredita dal padre [{src_id}]")
            return

        if t.get('codice_personalizzato', False):
            def on_confirm(yes):
                """Callback di conferma."""
                if yes:
                    self._esegui_generazione_py(t)
            self._show_confirm(f"La task '{t['nome']}' usa 'Codice Custom'.\nSovrascrivere il suo file .py?", on_confirm)
        else:
            self._esegui_generazione_py(t)

    def _cerca_glow_alternativi(self, lista_punti):
        """Scansiona lo schermo per cercare l'alone giallo su una lista di coordinate di gioco."""
        # Senza ambiente Windows non possiamo procedere
        if not _WIN_OK: return None
        try:
            import mss
            import numpy as np
        except ImportError:
            # Goal irraggiungibile o limite nodi superato
            return None

        # Cerca la finestra del gioco per nome
        hwnd = win32gui.FindWindow(None, "Among Us")
        if not hwnd: return None
        # Ottiene il rect (x, y, w, h) dell'area client del gioco
        rect = get_client_rect(hwnd)
        if not rect: return None
        cx_w, cy_w, cw, ch = rect

        # Cattura uno screenshot della regione del gioco
        with mss.mss() as sct:
            monitor = {"top": cy_w, "left": cx_w, "width": cw, "height": ch}
            try:
                img = np.array(sct.grab(monitor))[:, :, :3] # BGR
            except Exception:
                # Goal irraggiungibile o limite nodi superato
                return None
                
        cam_x, cam_y = self.pos_target
        cam_h = getattr(self, 'yolo_camera_height', 6.0)
        ppu = ch / cam_h
        
        for px, py in lista_punti:
            dx = px - cam_x
            dy = py - (cam_y + 0.36) # Offset altezza camera
            screen_x = int(cw / 2 + dx * ppu)
            screen_y = int(ch / 2 - dy * ppu)
            if 0 <= screen_x < cw and 0 <= screen_y < ch:
                r_sz = int(ppu * 0.6) 
                y1 = max(0, screen_y - r_sz); y2 = min(ch, screen_y + r_sz)
                x1 = max(0, screen_x - r_sz); x2 = min(cw, screen_x + r_sz)
                target_region = img[y1:y2, x1:x2]
                if target_region.size > 0:
                    yellow_pixels = np.sum((target_region[:,:,0] < 150) & (target_region[:,:,1] > 200) & (target_region[:,:,2] > 200))
                    if yellow_pixels > 20: return (px, py)
        # Goal irraggiungibile o limite nodi superato
        return None
