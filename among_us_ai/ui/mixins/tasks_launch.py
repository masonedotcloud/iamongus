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
            self.auto_status_msg = "Seleziona una task da avviare"
            return

        nome    = t['nome']
        reg     = t.get('reg_task')
        id_task = reg['id'] if reg else None

        if reg is None:
            self.auto_status_msg = f"'{nome}' non registrata - aggiungila prima"
            return
            
        self._current_auto_all_task_id = id_task

        # Memorizzo l'identita' della task che sto per inseguire, cosi'
        # durante il viaggio posso verificare se e' ancora attiva in RAM.
        # Serve soprattutto per le task VITALI (sabotaggi): se vengono
        # risolte/scompaiono mentre ci sto andando, e' inutile continuare.
        self._target_task_vitale = bool(reg.get('vitale', False))
        self._target_task_tipo = reg.get('tipo')
        self._target_task_stanza = reg.get('id_stanza')
            
        # Controllo Cooldown
        rem = self.task_cooldowns.get(id_task, 0) - time.time()
        if rem > 0:
            self.auto_status_msg = f"Task in cooldown. Riprova tra {int(rem)}s"
            return

        tag = "task_launch_popup"
        # Se il widget esiste gia', lo rimuovo prima di ricrearlo
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        # ── FASE 1: predisposizione (sincrona, prima di aprire il popup) ──
        filepath, pred_log = self.task_mgr.predisponi_esecuzione(id_task)

        # Avvia navigazione A*
        if not self.auto_enabled:
            self.auto_enabled = True
            # Se il widget esiste gia', lo rimuovo prima di ricrearlo
            if dpg.does_item_exist("auto_checkbox"):
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

        # Pannello informativo NON MODALE: piccolo, in basso a destra,
        # non blocca l'interazione con la mappa e gli altri controlli.
        # Il bot continua a essere usabile (zoom, pan, status bar) mentre
        # la task gira.
        panel_w, panel_h = 360, 130
        panel_x = max(0, vp_w - panel_w - 20)
        panel_y = max(0, vp_h - panel_h - 60)
        with dpg.window(label=f"In esecuzione: {nome}", tag=tag,
                        no_resize=True,
                        no_collapse=False,
                        no_close=True,
                        no_focus_on_appearing=True,
                        no_bring_to_front_on_focus=True,
                        width=panel_w, height=panel_h,
                        pos=(panel_x, panel_y)):
            dpg.add_text(viaggio_txt, tag="task_launch_popup_text",
                         color=(0, 200, 255, 255), wrap=panel_w - 20)

        # Disabilita l'animazione a step (il popup e' gia' pieno di testo)
        self.task_launch_active = False
        self._task_launch_nome  = nome
        self._task_launch_id    = id_task
        self._task_fallback_idx = 0

        # === PRE-WARMING ANTICIPATO ===
        # Avvia il subprocess ADESSO (inizio viaggio) con --wait-trigger.
        # Cosi' fa lo startup di Python (1-2s) MENTRE il bot cammina
        # verso la task. Quando arriva e preme SPAZIO, il subprocess
        # e' gia' caricato e parte istantaneo al ricevere "GO" su stdin.
        #
        # NB: e' importante anticiparlo qui (no all'arrivo) perche'
        # gli import sono lenti: mss + ultralytics + cv2 + win32 +
        # numpy = ~1.5s su PC tipico. Se anticipassi solo all'arrivo,
        # in caso di task vicine il GO arriverebbe prima del completamento
        # dello startup -> attesa visibile.
        try:
            self._avvia_subprocess_task(id_task, wait_trigger=True)
            self._task_prewarm_id = id_task  # ricordo che ho fatto pre-warm
            print(f"[PreWarming] Subprocess avviato per '{nome}' "
                  f"(inizio viaggio)", flush=True)
        except Exception as e:
            # Se il pre-warming fallisce, non e' fatale: continueremo
            # con l'avvio classico al momento dell'arrivo.
            print(f"[PreWarming] Errore avvio anticipato: {e}", flush=True)
            self._task_prewarm_id = None

        # ── FASE 2->3: callback all'arrivo ──
        def on_arrivo():
            """Chiamato da _update_auto_move quando il player raggiunge la task."""
            if not dpg.does_item_exist("task_launch_popup_text"):
                self._avvia_subprocess_task(id_task)
                return

            # Se il pre-warming era stato fatto all'inizio del viaggio
            # (`_avvia_task_selezionata`), il subprocess e' gia' avviato
            # e in attesa di "GO". Saltiamo la riavvio.
            if getattr(self, '_task_prewarm_id', None) != id_task:
                # Pre-warming non fatto (o per task diversa): fallback
                # al pre-warming "tardivo" all'arrivo.
                self._avvia_subprocess_task(id_task, wait_trigger=True)

            # === CHECK SE LA TASK E' TEMPO-CRITICA ===
            # Per task con azioni `simon_says` (Start Reactor) o altre
            # task che richiedono partenza istantanea, saltiamo la pausa
            # di stabilita' visiva e il check visuale (USE/alone giallo).
            # Quei 350-450ms di latenza causano la perdita dei primi
            # flash della sequenza nel Simon Says.
            try:
                azioni_eff, _src = self.task_mgr.get_azioni_effettive(id_task)
                is_tempo_critico = any(a.get('tipo') == 'simon_says'
                                        for a in azioni_eff)
            except Exception:
                is_tempo_critico = False

            if not is_tempo_critico:
                time.sleep(0.3) # pausa per stabilita' visiva (frame capture screen)

                # --- CHECK VISUALE (Use Button / Alone Giallo) ---
                # Fix crash 2P: il default usa reg['x']/reg['y'] (sempre
                # disponibili) invece di tx/ty, che NON vengono assegnate
                # quando la task e' a 2 giocatori (ramo `if target_2p`).
                # Vedi _avvia_task_selezionata: tx/ty esistono solo nel
                # ramo `else`, quindi riferirle qui dava un NameError sulle
                # task 2P (es. Reactor Meltdown).
                curr_target = getattr(self, '_current_nav_target',
                                      (reg['x'], reg['y']))
                if not self._controlla_task_attiva(curr_target[0], curr_target[1]):
                    alternativi = reg.get('alternativi', [])
                    curr_alternativo = getattr(self, '_task_alternativo_idx', 0)
                    if curr_alternativo < len(alternativi):
                        next_target = (alternativi[curr_alternativo]['x'], alternativi[curr_alternativo]['y'])
                        self._task_alternativo_idx = curr_alternativo + 1
                        self.auto_status_msg = f"Task non attiva qui, navigo all'alternativo {self._task_alternativo_idx}..."
                        print(f"[VisualCheck] Niente USE o alone giallo. Navigo a alternativo: {next_target}")
                        self._current_nav_target = next_target
                        self._plan_path(next_target)
                        self._on_arrival_callback = on_arrivo
                        return
                    else:
                        # Niente alternativi: invece di lanciare a vuoto
                        # (la task NON partirebbe davvero, il pulsante Use
                        # e' spento), RITENTO il riposizionamento sul target
                        # principale fino a REPOSITION_MAX_RETRY volte.
                        # Solo dopo i tentativi falliti rinuncio, cosi' non
                        # "fingo" di eseguire una task che non si attiva.
                        rip = getattr(self, '_task_reposition_retry', 0)
                        max_rip = int(getattr(GPSConfig,
                                              'REPOSITION_MAX_RETRY', 3))
                        if rip < max_rip:
                            self._task_reposition_retry = rip + 1
                            print(f"[VisualCheck] USE spento e niente "
                                  f"alternativi. Riposiziono "
                                  f"({self._task_reposition_retry}/{max_rip}).",
                                  flush=True)
                            self.auto_status_msg = (
                                f"USE spento: riposiziono "
                                f"({self._task_reposition_retry}/{max_rip})")
                            # Ritorno al target principale e rifaccio
                            # l'avvicinamento (il nudge ritentera' Use).
                            main_target = (reg['x'], reg['y'])
                            self._current_nav_target = main_target
                            self._plan_path(main_target)
                            self._on_arrival_callback = on_arrivo
                            return
                        else:
                            # Esauriti i retry: rinuncio a QUESTA task senza
                            # lanciarla. In Auto-All metto un cooldown cosi'
                            # il planner passa ad un'altra task e non resta
                            # incastrato qui.
                            print(f"[VisualCheck] USE ancora spento dopo "
                                  f"{max_rip} riposizionamenti. Salto la "
                                  f"task '{nome}'.", flush=True)
                            self.auto_status_msg = (
                                f"'{nome}': USE non attivo, task saltata")
                            self._task_reposition_retry = 0
                            if hasattr(self, 'task_cooldowns'):
                                # cooldown breve per non riprovarla subito
                                self.task_cooldowns[id_task] = time.time() + \
                                    float(getattr(GPSConfig,
                                          'REPOSITION_FAIL_COOLDOWN_SEC', 20.0))
                            self._cancel_auto_move(silent=True,
                                                   stop_auto_all=False)
                            if dpg.does_item_exist("task_launch_popup"):
                                dpg.delete_item("task_launch_popup")
                            return
                # Check superato: azzero il contatore retry riposizionamento.
                self._task_reposition_retry = 0
            else:
                print(f"[TaskLaunch] '{nome}' tempo-critica (simon_says): "
                      f"skip pausa stabilita' + check visuale", flush=True)

            # Aggiorna popup con gli step di lancio animati
            self._task_launch_steps     = (TaskManager.STATI_LAUNCH
                                           + [f">> '{nome}' IN ESECUZIONE *"])
            self._task_launch_timer_arr = 0.0
            self._task_launch_arrivo    = True  # flag: siamo in fase 3
            # Cambia le configurazioni di un widget gia' creato
            dpg.configure_item("task_launch_popup_text", color=(0, 220, 120, 255))
            self.auto_status_msg = f"Arrivato a '{nome}' - avvio in corso..."

        self._current_nav_target = target_2p if target_2p else (tx, ty)
        self._task_alternativo_idx = 0
        self._on_arrival_callback   = on_arrivo
        self._task_launch_arrivo    = False
        self._task_launch_timer_arr = 0.0
        self.auto_status_msg        = f"In viaggio verso '{nome}'..."

    def _update_task_launch(self, dt):
        """
        Gestisce l'animazione del popup nelle due fasi attive:
        - Fase 3 (arrivo): anima gli step di lancio e poi avvia il subprocess.
        (La fase 1 popola il popup in modo statico, nessuna animazione.)

        Se GPSConfig.LAUNCH_ANIMATION_ENABLED == False, skippa l'animazione
        e va subito al lancio (risparmia ~2.6s di attesa cosmetica).
        """
        if not getattr(self, '_task_launch_arrivo', False):
            return

        # Se l'animazione e' disabilitata, skippa subito al close
        anim_enabled = getattr(GPSConfig, 'LAUNCH_ANIMATION_ENABLED', False)

        self._task_launch_timer_arr += dt
        steps    = self._task_launch_steps
        interval = 0.4
        idx      = min(int(self._task_launch_timer_arr / interval), len(steps))

        log_text = "\n".join(steps[:idx])
        # Se il widget esiste gia', lo rimuovo prima di ricrearlo
        if dpg.does_item_exist("task_launch_popup_text"):
            dpg.set_value("task_launch_popup_text", log_text)

        # Dopo aver mostrato tutti gli step + 1s di pausa: avvia subprocess e chiudi.
        # Se animazione DISABILITATA: close_at = 0 (parte subito).
        if anim_enabled:
            close_at = len(steps) * interval + 1.0
        else:
            close_at = 0.0
        if self._task_launch_timer_arr >= close_at:
            self._task_launch_arrivo = False
            # Se il widget esiste gia', lo rimuovo prima di ricrearlo
            if dpg.does_item_exist("task_launch_popup"):
                dpg.delete_item("task_launch_popup")

            # --- ORDINE OTTIMIZZATO CON PRE-WARMING ---
            # Il subprocess e' gia' stato avviato in `on_arrivo()` con
            # --wait-trigger. Adesso e' caricato e in attesa di "GO" su
            # stdin.
            #
            # FASE B: premi SPAZIO -> il pannello del minigioco si apre.
            # FASE C: invia "GO" sullo stdin -> il subprocess parte
            #   istantaneo (no startup, gia' fatto).
            id_task = getattr(self, '_task_launch_id', None)

            # FASE A (preparatoria): garantisce che Among Us sia in
            # primo piano PRIMA di premere SPAZIO. Cosi':
            #   1. SPAZIO viene ricevuto dalla finestra giusta
            #   2. Il subprocess (quando ricevera' GO subito dopo)
            #      trova `GetForegroundWindow() == hwnd_amongus`
            #      e SALTA il `sleep(0.4)` di grace period.
            # Senza questo, ogni Simon Says/minigioco tempo-critico
            # perdeva 400ms preziosi al primo flash della sequenza.
            try:
                if _WIN_OK:
                    hwnd_au = win32gui.FindWindow(None, "Among Us")
                    if hwnd_au and win32gui.GetForegroundWindow() != hwnd_au:
                        win32gui.SetForegroundWindow(hwnd_au)
            except Exception:
                # Windows puo' rifiutare SetForegroundWindow per UAC
                # o altri motivi: non e' fatale, proseguiamo.
                pass

            # FASE B: APRI il pannello del minigioco.
            # Opzione IBRIDA: se il pulsante Use e' calibrato, clicchiamo
            # direttamente il suo centro (piu' affidabile: colpisce il
            # punto esatto del pulsante, indipendente dalla posizione
            # precisa del personaggio). Se non e' calibrato, fallback sulla
            # pressione di SPAZIO (comportamento classico).
            opened = False
            if bool(getattr(GPSConfig, 'USE_CLICK_TO_OPEN', True)):
                try:
                    from ...execution.use_button import (
                        carica_calibrazione, centro_use_button)
                    _calib = carica_calibrazione()
                    if _calib and _calib.get('calibrated', False) and _WIN_OK:
                        hwnd_au = win32gui.FindWindow(None, "Among Us")
                        if hwnd_au:
                            rect = win32gui.GetClientRect(hwnd_au)
                            pt = win32gui.ClientToScreen(
                                hwnd_au, (rect[0], rect[1]))
                            client_rect = (pt[0], pt[1], rect[2], rect[3])
                            centro = centro_use_button(client_rect, _calib)
                            if centro is not None:
                                time.sleep(0.05)  # assicura player fermo
                                pyautogui.click(centro[0], centro[1])
                                print(f"[Input] Click pulsante Use @ {centro} "
                                      f"per aprire il pannello.", flush=True)
                                opened = True
                except Exception as e:
                    print(f"[Input] Click Use fallito ({e}), "
                          f"fallback su SPAZIO.", flush=True)

            if not opened:
                # Fallback: premi SPAZIO per aprire il pannello del minigioco.
                try:
                    _send_scan(SCAN_CODES['SPACE'], keyup=False)
                    time.sleep(0.05)
                    _send_scan(SCAN_CODES['SPACE'], keyup=True)
                except Exception as e:
                    print(f"[Input] Errore pressione SPAZIO: {e}")

            # FASE C: invia il trigger al subprocess pre-warmed.
            # A questo punto il subprocess e' caricato e in attesa.
            # Mandando "GO" parte istantaneo.
            if id_task is not None:
                self._invia_trigger_subprocess()
            # ---------------------------------------

    def _esegui_generazione_py(self, t):
        """
        Genera (o rigenera) il file ``.py`` autonomo della task ``t`` e
        aggiorna l'etichetta di stato nella UI.

        Chiamato dal bottone "Genera/Rigenera codice .py" del popup task.
        Per task con ``codice_personalizzato=True``, la chiamata e' gia'
        stata filtrata da un dialog di conferma (lo richiama il callback
        :func:`on_confirm`).
        """
        # Genera (o ri-genera) il file .py autonomo della task
        filepath = self.task_mgr.crea_file_esecuzione(t['id'])

        if filepath:
            filename = os.path.basename(filepath)
            self.auto_status_msg = f"File creato: {filename}"
            # Se il widget esiste gia', lo rimuovo prima di ricrearlo
            if dpg.does_item_exist("genera_py_status"):
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item("genera_py_status", color=(0, 220, 120, 255))
                dpg.set_value("genera_py_status", f"OK {filename}")
            # Aggiorna anche il riferimento nel JSON (exec_info['file'])
            exec_info = t.setdefault('esecuzione', {
                'file': None, 'stato': 'idle', 'params': {}
            })
            exec_info['file'] = filepath
            # Salva il registro delle task su disco
            self.task_mgr.salva()
        else:
            self.auto_status_msg = "Errore creazione file .py"
            # Se il widget esiste gia', lo rimuovo prima di ricrearlo
            if dpg.does_item_exist("genera_py_status"):
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item("genera_py_status", color=(255, 80, 80, 255))
                dpg.set_value("genera_py_status", "X errore")

    def _genera_file_esecuzione(self):
        """
        Genera (o rigenera) il file .py di esecuzione per la task registrata
        selezionata nella listbox. Mostra feedback inline accanto al pulsante.
        """
        t = self._get_selected_reg_task()
        if t is None:
            self.auto_status_msg = "Seleziona una task registrata"
            # Se il widget esiste gia', lo rimuovo prima di ricrearlo
            if dpg.does_item_exist("genera_py_status"):
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item("genera_py_status", color=(255, 100, 80, 255))
                dpg.set_value("genera_py_status", "<- seleziona prima")
            return

        azioni_eff, src_id = self.task_mgr.get_azioni_effettive(t['id'])
        if src_id is not None and src_id != t['id']:
            self.auto_status_msg = f"La task eredita il file dal padre [{src_id}]"
            # Se il widget esiste gia', lo rimuovo prima di ricrearlo
            if dpg.does_item_exist("genera_py_status"):
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item("genera_py_status", color=(255, 180, 100, 255))
                dpg.set_value("genera_py_status", f"Eredita dal padre [{src_id}]")
            return

        if t.get('codice_personalizzato', False):
            def on_confirm(yes):
                """Callback del dialog: se ``yes``, sovrascrive il file custom rigenerandolo."""
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
        return None

    # ============================================================
    # RIGENERA TUTTI I .PY NON CUSTOM
    # ============================================================

    def _rigenera_tutti_py_non_custom(self):
        """
        Rigenera tutti i file .py di esecuzione delle task registrate,
        escludendo quelle con `codice_personalizzato=True`.

        Utile quando:
        - Il task_writer e' stato aggiornato (es. nuovi marker, nuovi campi
          in TASK_META) e i file esistenti sono diventati obsoleti
        - Hai modificato i parametri di config (es. SIMON_PANEL_TIMEOUT_SEC)
          e vuoi propagarli a tutti i file
        - Vuoi forzare una pulizia globale dei .py

        Mostra un popup con un sommario alla fine.
        """
        try:
            registrate = self.task_mgr.task_list
        except Exception as e:
            print(f"[Rigenera] Errore lettura task: {e}", flush=True)
            return

        total = len(registrate)
        rigenerate = 0
        saltate_custom = 0
        errori = 0
        errori_dettagli = []

        for t in registrate:
            id_task = t.get('id')
            nome = t.get('nome', '?')
            if t.get('codice_personalizzato', False):
                saltate_custom += 1
                continue
            try:
                fp = self.task_mgr.crea_file_esecuzione(id_task)
                if fp:
                    rigenerate += 1
                else:
                    errori += 1
                    errori_dettagli.append(
                        f"  - {nome} (id={id_task}): nessun file generato"
                    )
            except Exception as e:
                errori += 1
                errori_dettagli.append(
                    f"  - {nome} (id={id_task}): {e}"
                )

        # Salva il registro (per propagare eventuali aggiornamenti dei
        # campi 'esecuzione.file' nelle task).
        try:
            self.task_mgr.salva()
        except Exception as e:
            print(f"[Rigenera] Errore salva registro: {e}", flush=True)

        # Log a console
        print(f"[Rigenera] Totale: {total}, rigenerate: {rigenerate}, "
              f"saltate custom: {saltate_custom}, errori: {errori}",
              flush=True)
        for line in errori_dettagli[:10]:
            print(f"[Rigenera] {line}", flush=True)

        # Popup riassuntivo
        self._mostra_popup_rigenera(
            total=total,
            rigenerate=rigenerate,
            saltate_custom=saltate_custom,
            errori=errori,
            errori_dettagli=errori_dettagli,
        )

    def _mostra_popup_rigenera(self, total, rigenerate, saltate_custom,
                                 errori, errori_dettagli):
        """Popup riassuntivo dopo la rigenerazione bulk."""
        tag = "popup_rigenera_bulk"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        w, h = 480, 320
        with dpg.window(label="Rigenerazione file .py",
                          tag=tag,
                          modal=True,
                          width=w, height=h,
                          pos=((vp_w - w) // 2, (vp_h - h) // 2),
                          no_close=False,
                          on_close=lambda *a: dpg.delete_item(tag)):
            dpg.add_text("Operazione completata.",
                          color=(120, 220, 120))
            dpg.add_separator()
            dpg.add_text(f"Task totali registrate :  {total}")
            dpg.add_text(f"File .py rigenerati    :  {rigenerate}",
                          color=(120, 200, 220))
            dpg.add_text(f"Saltate (codice custom):  {saltate_custom}",
                          color=(180, 180, 100))
            err_color = (220, 80, 80) if errori > 0 else Colors.TEXT_DIM
            dpg.add_text(f"Errori                 :  {errori}",
                          color=err_color)
            if errori > 0:
                dpg.add_separator()
                dpg.add_text("Errori:", color=(220, 80, 80))
                for line in errori_dettagli[:10]:
                    dpg.add_text(line, color=Colors.TEXT_DIM, wrap=440)
                if len(errori_dettagli) > 10:
                    dpg.add_text(f"...e altri {len(errori_dettagli) - 10}",
                                  color=Colors.TEXT_DIM)
            dpg.add_separator()
            dpg.add_button(label="Chiudi",
                            callback=lambda *a: dpg.delete_item(tag))

