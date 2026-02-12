"""
Ciclo di vita del subprocess: avvio, controllo, fermo, rilevamento completamento dal RAM.

Mixin di GPSVisualizerPro.
"""

from ._imports import *


class TasksProcessMixin:
    """Mixin con i metodi di tasks process di GPSVisualizerPro."""
    def _avvia_subprocess_task(self, id_task):
        """
        Avvia il file .py della task come processo separato (non bloccante).
        Se c'e' gia' un processo attivo per la stessa task, non ne avvia un secondo.
        """
        task = self.task_mgr.get_by_id(id_task)
        if task is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Errore: task non trovata"
            return

        exec_info = task.setdefault('esecuzione', {})

        azioni_eff, src_id = self.task_mgr.get_azioni_effettive(id_task)
        target_id = src_id if (src_id is not None and src_id != id_task) else id_task
        target_task = self.task_mgr.get_by_id(target_id)
        
        # Assicuriamoci di usare sempre il file del padre se si eredita
        target_exec = target_task.setdefault('esecuzione', {})
        filepath  = target_exec.get('file')

        # Se il file non esiste ancora, crealo ora
        if not filepath or not os.path.exists(filepath):
            # Genera (o ri-genera) il file .py autonomo della task
            filepath = self.task_mgr.crea_file_esecuzione(target_id)
            if not filepath:
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = f"Errore: impossibile creare file .py per '{target_task['nome']}'"
                return
            exec_info['file'] = filepath
            target_exec['file'] = filepath
            # Salva il registro delle task su disco
            self.task_mgr.salva()

        # Se il file esiste ma e' vecchio (senza blocco __main__), rigeneralo
        try:
            with open(filepath, 'r', encoding='utf-8') as fh:
                contenuto = fh.read()
            if ('current_step=TASK_META' not in contenuto or 'sys.exit(1)' not in contenuto or 'GetForegroundWindow() != hwnd' not in contenuto) and not target_task.get('codice_personalizzato', False):
                print(f"[Exec] File '{os.path.basename(filepath)}' obsoleto - rigenero")
                # Genera (o ri-genera) il file .py autonomo della task
                filepath = self.task_mgr.crea_file_esecuzione(target_id)
                exec_info['file'] = filepath
                target_exec['file'] = filepath
                # Salva il registro delle task su disco
                self.task_mgr.salva()
        except Exception:
            pass

        # Evita doppio avvio dello stesso processo
        if (self._task_process is not None
                and self._task_process.poll() is None
                and self._task_process_task_id == id_task):
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"'{task['nome']}' e' gia' in esecuzione"
            return

        _, _, ram_step = self._get_task_target_coords(task)
        
        # Prende lo step massimo tra quello della RAM (se il giocatore l'ha fatto a mano) 
        # e quello interno (guidato dalle azioni di Cooldown nello script)
        internal_step = self.task_internal_steps.get(id_task, 0)
        script_step = max(ram_step, internal_step)

        try:
            abs_filepath = os.path.abspath(filepath)
            # cwd = directory di lancio del bot (dove stanno mappa_skeld.json,
            # i modelli .pt, ecc.). Nell'originale __file__ era main.py nella
            # cartella radice; con il package __file__ e' dentro among_us_ai/ui/
            # quindi usiamo os.getcwd() che e' la cwd del processo principale.
            self._task_process = subprocess.Popen(
                [sys.executable, "-u", abs_filepath, "--step", str(script_step)],
                cwd=os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,   # unifica stderr in stdout
                bufsize=0,
            )
            self._task_process_task_id = id_task
            # Aggiorna lo stato di esecuzione (idle/running/done/error)
            self.task_mgr.imposta_stato_esecuzione(id_task, 'running')
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"> '{task['nome']}' avviata (PID {self._task_process.pid})"
            print(f"[Exec] Avviato '{abs_filepath}' - PID {self._task_process.pid}", flush=True)

            # Thread che legge stdout del processo e stampa riga per riga
            proc_ref  = self._task_process
            nome_task = task['nome']
            def _leggi_output(proc, nome, tid, sys_ref):
                """Thread che legge stdout del subprocess in modo non bloccante."""
                try:
                    for raw in proc.stdout:
                        line = raw.decode('utf-8', errors='replace').rstrip('\n')
                        print(f"[{nome}] {line}", flush=True)
                        if line.startswith("__COOLDOWN__:"):
                            try:
                                cd_val = float(line.split(":")[1])
                                sys_ref.task_cooldowns[tid] = time.time() + cd_val
                                
                                # Lo script ha eseguito con successo un blocco/fase, salviamo in memoria locale
                                curr = sys_ref.task_internal_steps.get(tid, 0)
                                sys_ref.task_internal_steps[tid] = curr + 1
                                
                                print(f"[{nome}] Timer cooldown impostato per {cd_val}s", flush=True)
                            except ValueError:
                                pass
                except Exception:
                    pass
            # Crea un thread parallelo (per non bloccare l'UI)
            t = threading.Thread(
                target=_leggi_output,
                args=(proc_ref, nome_task, id_task, self),
                daemon=True,
            )
            t.start()
        except Exception as e:
            # Aggiorna lo stato di esecuzione (idle/running/done/error)
            self.task_mgr.imposta_stato_esecuzione(id_task, 'error')
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"Errore avvio: {e}"
            print(f"[Exec] Errore avvio '{filepath}': {e}")

    def _controlla_processo_task(self):
        """
        Controlla se il processo in esecuzione e' terminato e aggiorna lo stato.
        Va chiamato nel loop principale (aggiorna_frame).
        """
        if self._task_process is None:
            return
        ret = self._task_process.poll()
        if ret is None:
            # --- Controllo completamento RAM in tempo reale ---
            id_task = self._task_process_task_id
            if id_task is not None:
                task_reg = self.task_mgr.get_by_id(id_task)
                if task_reg:
                    tipo = task_reg.get('tipo')
                    id_stanza = task_reg.get('id_stanza')
                    # Cerca la task corrispondente in memoria
                    for mt in getattr(self, 'memory_tasks', []):
                        if mt.get('tipo') == tipo and mt.get('id_stanza') == id_stanza:
                            if mt.get('done', False):
                                # La task e' finita nel gioco! Termina il processo.
                                self._ferma_processo_task(success=True)
                                return
            return  # ancora in esecuzione

        # Processo terminato
        id_task = self._task_process_task_id
        if id_task is not None:
            task = self.task_mgr.get_by_id(id_task)
            
            # --- LOGICA DI FALLBACK: Se la task fallisce e ha Alternativi, usali come posizioni alternative ---
            if ret != 0 and task and task.get('alternativi'):
                alternativi = task.get('alternativi', [])
                curr_fallback = getattr(self, '_task_fallback_idx', 0)
                if curr_fallback < len(alternativi):
                    next_target = (alternativi[curr_fallback]['x'], alternativi[curr_fallback]['y'])
                    self._task_fallback_idx = curr_fallback + 1
                    # Messaggio di stato mostrato all'utente nel pannello
                    self.auto_status_msg = f"Task fallita, provo alternativo {self._task_fallback_idx}..."
                    print(f"[Fallback] Errore esecuzione. Navigo al punto alternativo: {next_target}")
                    
                    self._task_process = None
                    self._task_process_task_id = None
                    
                    self._current_nav_target = next_target
                    self._plan_path(next_target)
                    
                    def on_arrivo_fallback():
                        """Callback di fallback: chiamato se il pathfinding fallisce."""
                        self._avvia_subprocess_task(id_task)
                        
                    self._on_arrival_callback = on_arrivo_fallback
                    return
            # -----------------------------------------------------------------------------------------

            nuovo_stato = 'done' if ret == 0 else 'error'
            # Aggiorna lo stato di esecuzione (idle/running/done/error)
            self.task_mgr.imposta_stato_esecuzione(id_task, nuovo_stato)

            # Applica Cooldown se il processo e' finito senza errori e la task lo richiede
            if ret == 0 and task and task.get('cooldown', 0) > 0:
                self.task_cooldowns[id_task] = time.time() + task['cooldown']

            # --- COOLDOWN DI SICUREZZA contro il loop infinito ---
            # Se il subprocess e' terminato (con qualsiasi exit code) ma la
            # task NON risulta done in RAM, applichiamo un cooldown breve
            # per evitare che Auto-All la rilanci subito in ciclo. Succede
            # quando il bot non arriva esatto sul punto, oppure il minigioco
            # non si apre per qualunque motivo.
            if task:
                task_done_in_ram = False
                tipo_t   = task.get('tipo')
                room_t   = task.get('id_stanza')
                for mt in getattr(self, 'memory_tasks', []):
                    if (mt.get('tipo') == tipo_t
                            and mt.get('id_stanza') == room_t
                            and mt.get('done', False)):
                        task_done_in_ram = True
                        break
                if not task_done_in_ram:
                    existing_cd = self.task_cooldowns.get(id_task, 0)
                    safety_cd = time.time() + 8.0   # 8 s di tregua
                    if safety_cd > existing_cd:
                        self.task_cooldowns[id_task] = safety_cd
                        print(f"[Loop guard] Task non completata in RAM - cooldown di sicurezza 8s")

            nome = task['nome'] if task else f"#{id_task}"
            icona = "OK" if ret == 0 else "X"
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"{icona} '{nome}' terminata (exit {ret})"
            print(f"[Exec] '{nome}' terminata - exit code {ret}")

        self._task_process         = None
        self._task_process_task_id = None

    def _ferma_processo_task(self, success=False):
        """Termina il processo attivo (se presente) e aggiorna lo stato a idle."""
        # Rilascia sempre il mouse per evitare che rimanga incastrato sul gioco
        if _WIN_OK:
            try:
                # Rilascia il tasto sinistro del mouse
                pyautogui.mouseUp(button='left')
            except Exception:
                pass
                
        if self._task_process is None or self._task_process.poll() is not None:
            if not success:
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = "Nessun processo da fermare"
            return
        try:
            # Termina forzatamente il subprocess
            self._task_process.terminate()
            self._task_process.wait(timeout=3)
        except Exception:
            try:
                self._task_process.kill()
            except Exception:
                pass
        id_task = self._task_process_task_id
        if id_task is not None:
            nuovo_stato = 'done' if success else 'idle'
            # Aggiorna lo stato di esecuzione (idle/running/done/error)
            self.task_mgr.imposta_stato_esecuzione(id_task, nuovo_stato)
            task = self.task_mgr.get_by_id(id_task)
            nome = task['nome'] if task else f"#{id_task}"
            if success:
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = f"OK '{nome}' completata (Memoria)"
                print(f"[Exec] '{nome}' interrotta automaticamente (successo in RAM)")
            else:
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = f"[X] '{nome}' fermata"
                print(f"[Exec] '{nome}' terminata forzatamente")
        self._task_process         = None
        self._task_process_task_id = None

    def _controlla_task_attiva(self, task_x, task_y):
        """
        Controlla a schermo se c'e' il pulsante USE acceso o l'alone giallo
        sulla task a coordinate di gioco (task_x, task_y).
        Ritorna True se la task sembra attiva qui, False altrimenti.
        """
        # Senza ambiente Windows non possiamo procedere
        if not _WIN_OK:
            return True
            
        try:
            import mss
            import numpy as np
        except ImportError:
            return True

        # Cerca la finestra del gioco per nome
        hwnd = win32gui.FindWindow(None, "Among Us")
        if not hwnd:
            return True 

        # Ottiene il rect (x, y, w, h) dell'area client del gioco
        rect = get_client_rect(hwnd)
        if not rect:
            return True
        cx, cy, cw, ch = rect

        # Cattura uno screenshot della regione del gioco
        with mss.mss() as sct:
            monitor = {"top": cy, "left": cx, "width": cw, "height": ch}
            try:
                img = np.array(sct.grab(monitor))[:, :, :3] # BGR
            except Exception:
                return True

        # 1. Controlla il pulsante USE in basso a destra (16:9 / 16:10)
        use_roi_x1 = int(cw * 0.82)
        use_roi_x2 = int(cw * 0.98)
        use_roi_y1 = int(ch * 0.80)
        use_roi_y2 = int(ch * 0.96)
        use_region = img[use_roi_y1:use_roi_y2, use_roi_x1:use_roi_x2]
        
        use_active = False
        if use_region.size > 0:
            # Cerca densita' di pixel molto luminosi (testo bianco o colori accesi)
            bright_pixels = np.sum(np.all(use_region > 220, axis=2))
            if bright_pixels > 100:
                use_active = True
                
        # 2. Controlla alone giallo sulla task
        cam_x, cam_y = self.pos_target
        cam_h = getattr(self, 'yolo_camera_height', 6.0)
        ppu = ch / cam_h
        
        dx = task_x - cam_x
        dy = task_y - (cam_y + 0.36) # Offset altezza camera
        
        screen_x = int(cw / 2 + dx * ppu)
        screen_y = int(ch / 2 - dy * ppu)
        
        glow_active = False
        if 0 <= screen_x < cw and 0 <= screen_y < ch:
            r_sz = int(ppu * 0.6) 
            y1 = max(0, screen_y - r_sz)
            y2 = min(ch, screen_y + r_sz)
            x1 = max(0, screen_x - r_sz)
            x2 = min(cw, screen_x + r_sz)
            
            target_region = img[y1:y2, x1:x2]
            if target_region.size > 0:
                # Giallo in BGR: B < 150, G > 200, R > 200
                yellow_pixels = np.sum((target_region[:,:,0] < 150) & (target_region[:,:,1] > 200) & (target_region[:,:,2] > 200))
                if yellow_pixels > 20:
                    glow_active = True
                    
        return use_active or glow_active
