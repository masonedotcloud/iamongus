"""
Ciclo di vita del subprocess: avvio, controllo, fermo, rilevamento completamento dal RAM.

Mixin di GPSVisualizerPro.
"""

from ._imports import *


class TasksProcessMixin:
    """Mixin con i metodi di tasks process di GPSVisualizerPro."""
    def _avvia_subprocess_task(self, id_task, start_from_action=0,
                               wait_trigger=False):
        """
        Avvia il file .py della task come processo separato (non bloccante).
        Se c'e' gia' un processo attivo per la stessa task, non ne avvia un secondo.

        Parametri
        ---------
        id_task : int
            ID della task da eseguire.
        start_from_action : int (default 0)
            Numero di azioni iniziali del chunk da SALTARE. Usato in
            modalita' "ripeti azione": dopo un fallimento, il bot rilancia
            il subprocess con start_from_action = indice della prima azione
            con [Ripeti]=True, in modo da non rifare le azioni precedenti
            (gia' completate dal punto di vista RAM).
        wait_trigger : bool (default False)
            Modalita' pre-warming: il subprocess viene avviato in anticipo
            (es. durante l'arrivo al target) e aspetta una riga "GO\\n" su
            stdin prima di iniziare l'analisi. Il bot principale chiama
            poi `self._task_process.stdin.write(b"GO\\n")` quando vuole
            far partire la task (es. al press SPAZIO).
            Cosi' il startup di Python avviene PRIMA del SPAZIO e
            l'analisi parte istantanea.
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

        # In thread mode non e' richiesto il file .py (il motore riceve
        # direttamente le azioni in memoria), ma lo generiamo lo stesso
        # SOLO se manca, cosi' resta retrocompatibile con subprocess mode
        # e con lancio manuale del .py da shell. Skip della verifica
        # "obsoleto" per non rallentare ogni avvio.
        exec_mode_pre = getattr(GPSConfig, 'EXEC_MODE', 'thread')

        # Se il file non esiste ancora, crealo ora
        if not filepath or not os.path.exists(filepath):
            # Genera (o ri-genera) il file .py autonomo della task
            filepath = self.task_mgr.crea_file_esecuzione(target_id)
            if not filepath:
                if exec_mode_pre != 'thread':
                    # In subprocess mode, senza file e' un errore fatale
                    self.auto_status_msg = f"Errore: impossibile creare file .py per '{target_task['nome']}'"
                    return
            else:
                exec_info['file'] = filepath
                target_exec['file'] = filepath
                self.task_mgr.salva()

        # In subprocess mode: se il file esiste ma e' vecchio (senza
        # blocco __main__), rigeneralo. In thread mode, skip: il file
        # NON viene usato per l'esecuzione, basta che esista.
        if exec_mode_pre != 'thread' and filepath and os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as fh:
                    contenuto = fh.read()
                if ('current_step=TASK_META' not in contenuto or 'sys.exit(1)' not in contenuto or 'GetForegroundWindow() != hwnd' not in contenuto or 'WAIT_TRIGGER' not in contenuto) and not target_task.get('codice_personalizzato', False):
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

        # Salva lo step lanciato per questa task. Serve a `_fase_da_ripetere_ext`
        # per sapere quale fase e' stata "appena eseguita" dal subprocess
        # (l'`internal_step` non e' affidabile in caso di ultima fase senza
        # cooldown finale: il subprocess termina senza stampare __COOLDOWN__:
        # quindi `internal_step` resta fermo).
        if not hasattr(self, 'task_last_launched_step'):
            self.task_last_launched_step = {}
        self.task_last_launched_step[id_task] = script_step

        # Memorizza lo step in RAM al momento del lancio. Serve al
        # "STOP watcher" per rilevare avanzamento durante l'esecuzione:
        # se ad un certo punto il polling RAM trova step > script_step,
        # la fase e' stata risolta dal gioco -> manda STOP al subprocess
        # che interrompe le azioni residue (es. drag inutili).
        if not hasattr(self, 'task_ram_step_at_launch'):
            self.task_ram_step_at_launch = {}
        self.task_ram_step_at_launch[id_task] = ram_step

        try:
            # In thread mode il file potrebbe essere None se la generazione
            # e' fallita; fallback a stringa descrittiva per i log.
            abs_filepath = os.path.abspath(filepath) if filepath else f"<thread:{target_task['nome']}>"
            # cwd = directory di lancio del bot (dove stanno mappa_skeld.json,
            # i modelli .pt, ecc.). Nell'originale __file__ era main.py nella
            # cartella radice; con il package __file__ e' dentro among_us_ai/ui/
            # quindi usiamo os.getcwd() che e' la cwd del processo principale.
            cmd = [sys.executable, "-u", abs_filepath,
                   "--step", str(script_step)]
            # Modalita' "ripeti azione": passa --start-from-action solo se > 0
            # (cosi' i file vecchi che non riconoscono il flag continuano a
            # funzionare grazie a parse_known_args).
            if start_from_action > 0:
                cmd += ["--start-from-action", str(start_from_action)]
            # Modalita' pre-warming: passa --wait-trigger se richiesto.
            # Il subprocess fara' setup/import poi aspettera' "GO" su stdin.
            if wait_trigger:
                cmd += ["--wait-trigger"]

            # === MODALITA' DI ESECUZIONE: thread o subprocess ===
            # In v2.2.17+ il default e' 'thread': il motore gira come
            # thread interno del bot. Risparmia ~300-500ms di startup
            # di Python e tutta l'IPC. Critico per minigiochi reattivi
            # come Simon Says.
            exec_mode = getattr(GPSConfig, 'EXEC_MODE', 'thread')

            if exec_mode == 'thread':
                # ---- THREAD MODE ----
                # Costruisco TASK_META + AZIONI dalla task corrente,
                # IDENTICO a quello che il file .py costruirebbe.
                task_meta = self._build_task_meta_for_thread(
                    target_task, azioni_eff,
                    script_step, start_from_action,
                )
                from ...execution.task_thread_runner import TaskThreadProcess
                self._task_process = TaskThreadProcess(
                    task_meta=task_meta,
                    azioni=list(azioni_eff),
                    nome_task=task['nome'],
                )
                avvio_label = f"thread-{self._task_process.pid}"
            else:
                # ---- SUBPROCESS MODE (legacy) ----
                # Se in modalita' pre-warming, apriamo stdin come PIPE
                # cosi' poi possiamo inviare "GO\n" per triggerare il
                # subprocess. Senza wait_trigger, stdin e' chiuso.
                # stdin=PIPE sempre attivo: il bot principale puo' inviare:
                # - "GO\n" per sbloccare il pre-warming (--wait-trigger)
                # - "STOP\n" per richiedere interruzione quando la fase
                #   e' stata risolta in RAM (anche senza pre-warming)
                popen_stdin = subprocess.PIPE
                self._task_process = subprocess.Popen(
                    cmd,
                    cwd=os.getcwd(),
                    stdin=popen_stdin,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,   # unifica stderr in stdout
                    bufsize=0,
                )
                avvio_label = f"PID {self._task_process.pid}"
                if wait_trigger:
                    avvio_label += " (pre-warm)"
            self._task_process_task_id = id_task
            # Aggiorna lo stato di esecuzione (idle/running/done/error)
            self.task_mgr.imposta_stato_esecuzione(id_task, 'running')
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"> '{task['nome']}' avviata ({avvio_label})"
            print(f"[Exec] Avviato '{abs_filepath}' - {avvio_label}", flush=True)

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

    def _invia_trigger_subprocess(self):
        """
        Invia "GO\\n" sullo stdin del subprocess pre-warmed, facendolo
        partire immediatamente.

        Da chiamare quando si preme SPAZIO per aprire il pannello del
        minigioco. Il subprocess, gia' avviato in anticipo con
        --wait-trigger, era in stand-by. Ricevuto "GO" parte subito.

        IMPORTANTE: NON chiudere stdin dopo l'invio. Il bot principale
        puo' ancora inviare "STOP" durante l'esecuzione (es. quando la
        fase e' risolta in RAM e vogliamo interrompere azioni residue).
        Stdin viene chiuso automaticamente al termine del subprocess.

        Idempotente: se il subprocess non e' attivo, in modalita' thread,
        o gia' triggerato, non fa nulla.
        """
        if self._task_process is None:
            return
        # Solo subprocess mode ha stdin (TaskThreadProcess non lo espone).
        proc_stdin = getattr(self._task_process, 'stdin', None)
        if proc_stdin is None:
            return
        try:
            # Invia "GO\n" e flush. Il subprocess fa readline() su stdin
            # in lifecycle.py:run_task e riprende l'esecuzione.
            proc_stdin.write(b"GO\n")
            proc_stdin.flush()
            # NON chiudere stdin: serve ancora per inviare "STOP" piu' avanti.
            print(f"[Trigger] Inviato GO al subprocess", flush=True)
        except (BrokenPipeError, ValueError, OSError) as e:
            # Il subprocess potrebbe essere gia' terminato o stdin gia'
            # chiuso: non e' un errore fatale.
            print(f"[Trigger] Stdin non scrivibile (subprocess terminato?): {e}",
                  flush=True)

    def _build_task_meta_for_thread(self, target_task, azioni_eff,
                                    script_step, start_from_action):
        """
        Costruisce il dizionario TASK_META per la modalita' thread.

        Replica esattamente la struttura che il file .py autonomo
        costruirebbe via task_writer._build_meta. Cosi' il motore
        riceve un input identico nei due mode (subprocess/thread).
        """
        return {
            'id':            target_task.get('id'),
            'nome':          target_task.get('nome'),
            'x':             float(target_task.get('x', 0.0)),
            'y':             float(target_task.get('y', 0.0)),
            'tipo':          target_task.get('tipo'),
            'id_stanza':     target_task.get('id_stanza'),
            'vitale':        bool(target_task.get('vitale', False)),
            'due_giocatori': bool(target_task.get('due_giocatori', False)),
            'lunghezza':     target_task.get('lunghezza', 'N/A'),
            'id_padre':      target_task.get('id_padre'),
            'fasi':          target_task.get('fasi', []),
            'parametri':     (target_task.get('esecuzione', {})
                              .get('parametri',
                                   target_task.get('esecuzione', {}).get('params', {}))),
            'delay_avvio':   float(target_task.get('delay_avvio', 0.0)),
            'step':                int(script_step),
            'start_from_action':   int(start_from_action),
        }

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
                            # --- Check step avanzato per fasi con ripeti=True ---
                            # Se la fase corrente e' marcata ripeti=True e
                            # lo step in RAM e' avanzato oltre quello interno,
                            # significa che il gioco ha rilevato il
                            # completamento della fase -> stop subprocess
                            # e lascia che il bot principale rilanci la
                            # task con lo step successivo.
                            if self._fase_corrente_e_ripeti(task_reg):
                                internal_step = self.task_internal_steps.get(id_task, 0)
                                try:
                                    cur, _ = mt.get('prog', '0/0').split('/')
                                    ram_step = int(cur)
                                except Exception:
                                    ram_step = 0
                                if ram_step >= internal_step + 1:
                                    print(f"[Ripeti] RAM step avanzato "
                                          f"({ram_step}>={internal_step+1}) - fase finita.")
                                    # Fermiamo il subprocess SENZA marcarlo done.
                                    # Lo stato sara' aggiornato dal flusso normale
                                    # (la task non e' done in RAM ancora, ma la
                                    # fase si). L'auto-runner riprendera' con
                                    # lo step successivo se ce ne sono.
                                    self._ferma_processo_task(success=False)
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

            # --- LOGICA "RIPETI": rilancia il subprocess se la fase
            # corrente ha ripeti=True E la task non e' veramente terminata.
            #
            # Questa logica NON si limita al caso ret==0: anche se il
            # subprocess esce con exit code 1 (es. perche' run_task ha
            # ritornato None/False, oppure il bot non ha trovato un
            # bersaglio temporaneo), la fase puo' ancora essere da
            # ripetere se la RAM dice che la task non e' done.
            #
            # Per capire se la task e' "veramente finita" incrocio 3
            # segnali dalla RAM:
            #   1) La task e' marcata 'done' (step >= mstep)
            #   2) La task e' SCOMPARSA dalla lista in RAM (significa che
            #      il giocatore ha completato e il gioco l'ha rimossa)
            #   3) Lo step in RAM e' avanzato oltre quello interno
            # In tutti e 3 i casi: NON ripetere, lascia che il flusso
            # normale aggiorni lo stato.
            #
            # Altrimenti: se la fase ha ripeti=True, RILANCIA il subprocess.
            # Altrimenti: se la fase ha ripeti=True, RILANCIA il subprocess.
            if task and self._fase_da_ripetere_ext(task, ret):
                # Calcola start_from_action: indice della PRIMA azione con
                # ripeti=True nel chunk corrente. Cosi' al rilancio il
                # subprocess salta le azioni precedenti (che si presume
                # abbiano gia' avuto effetto - es. il click che ha pescato
                # la carta) e riprova solo la parte ripetibile.
                start_from = self._calcola_start_from_action(task)
                print(f"[Ripeti] Fase con ripeti=True, RAM dice non finita. "
                      f"Rilancio subprocess saltando {start_from} azioni iniziali.")
                self._task_process         = None
                self._task_process_task_id = None
                # Cleanup state per riavvio pulito (STOP watcher, retry counts)
                if hasattr(self, "task_stop_sent"):
                    self.task_stop_sent.discard(id_task)
                # Pausa breve prima del rilancio (anti-loop frenetico)
                time.sleep(0.3)
                self._avvia_subprocess_task(id_task, start_from_action=start_from)
                return
            # ----------------------------------------------------------------

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
        # Cleanup state per riavvio pulito (STOP watcher, retry counts)
        if hasattr(self, "task_stop_sent"):
            self.task_stop_sent.discard(id_task)

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
        # Cleanup state per riavvio pulito (STOP watcher, retry counts)
        if hasattr(self, "task_stop_sent"):
            self.task_stop_sent.discard(id_task)

    def _fase_corrente_e_ripeti(self, task):
        """
        Helper: ritorna True se la fase attualmente "in esecuzione" della
        task contiene almeno un'azione marcata con ripeti=True.

        Il flag 'ripeti' puo' essere settato su QUALUNQUE azione (non
        solo sui cooldown). Le azioni della task sono divise in chunk
        separati dai cooldown:
            chunk[0] -> azioni della fase 0
            cooldown[0]                              -> chiude fase 0
            chunk[1] -> azioni della fase 1
            cooldown[1]                              -> chiude fase 1
            ...

        Se ALMENO UNA azione del chunk corrente ha ripeti=True, l'intero
        chunk verra' ripetuto fino a cambio step in RAM.

        task_internal_steps[id] = numero di chunk eseguiti finora.
        Quando vale `k`, lo script sta eseguendo chunk[k] (= fase k).
        """
        if not task:
            return False

        # Recupera le azioni effettive (proprie o ereditate dal padre)
        try:
            azioni_eff, _ = self.task_mgr.get_azioni_effettive(task['id'])
        except Exception:
            azioni_eff = task.get('azioni', [])

        if not azioni_eff:
            return False

        # Spezzo le azioni in chunk in base ai cooldown (stessa logica
        # del dispatcher in _motore_pkg/dispatcher.py)
        chunks = []
        current = []
        for a in azioni_eff:
            if a.get('tipo') == 'cooldown':
                chunks.append(current)
                current = []
                # Anche il cooldown stesso puo' avere ripeti=True
                # (retro-compatibilita' con v2.2.1, lo includiamo nel
                # chunk PRECEDENTE)
                if a.get('ripeti'):
                    chunks[-1].append(a)
            else:
                current.append(a)
        chunks.append(current)

        # Indice fase corrente
        internal_step = self.task_internal_steps.get(task['id'], 0)
        # Clamp
        if internal_step >= len(chunks):
            return False
        chunk_corr = chunks[internal_step]

        # Almeno un'azione del chunk ha ripeti=True?
        return any(a.get('ripeti') for a in chunk_corr)

    def _fase_da_ripetere(self, task):
        """
        Decide se rilanciare il subprocess perche' la fase appena
        eseguita conteneva azioni con ripeti=True e la RAM dice che
        non c'e' stato avanzamento.

        Chiamato dopo che il subprocess e' terminato con ret==0.
        Quando si arriva qui:
        - lo script ha appena finito il chunk corrente
        - se aveva un cooldown finale, ha gia' printato __COOLDOWN__:
          quindi task_internal_steps[id] e' gia' incrementato
        - quindi la fase APPENA finita e' (internal_step - 1)

        Ritorna True se va rilanciato il subprocess con lo stesso step,
        False altrimenti.
        """
        if not task:
            return False

        try:
            azioni_eff, _ = self.task_mgr.get_azioni_effettive(task['id'])
        except Exception:
            azioni_eff = task.get('azioni', [])

        if not azioni_eff:
            return False

        # Spezzo in chunk (stessa logica di _fase_corrente_e_ripeti)
        chunks = []
        current = []
        for a in azioni_eff:
            if a.get('tipo') == 'cooldown':
                chunks.append(current)
                current = []
                if a.get('ripeti'):
                    chunks[-1].append(a)
            else:
                current.append(a)
        chunks.append(current)

        id_task = task['id']
        internal_step = self.task_internal_steps.get(id_task, 0)

        if internal_step == 0:
            # Nessun chunk eseguito ancora. Niente da ripetere.
            return False

        # La fase appena finita e' (internal_step - 1)
        idx_fase = internal_step - 1
        if idx_fase >= len(chunks):
            return False
        chunk_corr = chunks[idx_fase]

        # 1) Almeno un'azione del chunk deve avere ripeti=True
        if not any(a.get('ripeti') for a in chunk_corr):
            return False

        # 2) La task non deve essere done in RAM
        tipo_t = task.get('tipo')
        room_t = task.get('id_stanza')
        ram_step = 0
        ram_done = False
        for mt in getattr(self, 'memory_tasks', []):
            if mt.get('tipo') == tipo_t and mt.get('id_stanza') == room_t:
                # Stringa "step/mstep" -> due interi
                prog = mt.get('prog', '0/0')
                try:
                    cur, _ = prog.split('/')
                    ram_step = int(cur)
                except Exception:
                    pass
                ram_done = mt.get('done', False)
                break

        if ram_done:
            return False  # Task finita: stop

        # 3) La RAM deve avere lo step ANCORA fermo a quello della
        # fase appena eseguita (cioe' il giocatore non ha progredito).
        # Se ram_step >= internal_step, il gioco ha gia' contato il
        # progresso -> fase finita, stop.
        if ram_step >= internal_step:
            return False

        # Tutti i controlli ok: la fase va ripetuta.
        return True

    def _fase_da_ripetere_ext(self, task, ret):
        """
        Versione estesa di _fase_da_ripetere che gestisce ANCHE i casi
        di fallimento del subprocess (ret != 0).

        Logica: la fase va ripetuta se:
          - almeno una azione del chunk corrente ha ripeti=True
          - E la task NON risulta veramente finita in RAM

        "Task veramente finita" = uno qualsiasi di questi 3 segnali:
          (a) Task marcata done in RAM (step >= mstep)
          (b) Task SCOMPARSA dalla RAM (es. nome non piu' presente,
              perche' il gioco l'ha rimossa)
          (c) Step in RAM avanzato oltre lo step interno (la fase
              successiva sta gia' partendo)

        Parametri
        ---------
        task : dict
            La task (dal task_manager).
        ret : int
            Exit code del subprocess (0 = OK, !=0 = errore).
            Non usato direttamente nella decisione: la decisione si
            basa SOLO sui dati RAM. Il return code e' lasciato come
            parametro per eventuale logging/debug.

        Ritorna
        -------
        bool
            True se va rilanciato il subprocess, False se va lasciato
            terminare (e marcato done/error dal flusso normale).
        """
        if not task:
            return False

        id_task = task['id']
        nome_t  = task.get('nome', '?')

        # Recupera azioni effettive (proprie o ereditate dal padre).
        try:
            azioni_eff, src_id = self.task_mgr.get_azioni_effettive(id_task)
        except Exception:
            azioni_eff = task.get('azioni', [])
            src_id = id_task

        # FALLBACK: se le azioni effettive arrivano dal padre, ma la figlia
        # ha azioni proprie con ripeti=True, usa quelle. Questo gestisce
        # il caso in cui l'utente ha cliccato "ripeti" nella figlia ma
        # le azioni effettive sono del padre.
        if src_id != id_task:
            try:
                proprie = self.task_mgr.esecuzione.get_azioni(id_task)
                if proprie and any(a.get('ripeti') for a in proprie):
                    print(f"[Ripeti] Task '{nome_t}': uso azioni proprie "
                          f"della figlia (con ripeti) invece delle paterne.")
                    azioni_eff = proprie
            except Exception:
                pass

        if not azioni_eff:
            print(f"[Ripeti] Task '{nome_t}': nessuna azione, no rilancio.")
            return False

        # Debug: stampo quante azioni ho e quali hanno ripeti
        n_ripeti = sum(1 for a in azioni_eff if a.get('ripeti'))
        print(f"[Ripeti DEBUG] Task '{nome_t}': {len(azioni_eff)} azioni, "
              f"{n_ripeti} con ripeti=True (src_id={src_id})")

        # Spezzo in chunk separati dai cooldown
        chunks = []
        current = []
        for a in azioni_eff:
            if a.get('tipo') == 'cooldown':
                chunks.append(current)
                current = []
                # Cooldown con ripeti=True (retro-compat v2.2.1) si
                # considera parte del chunk PRECEDENTE
                if a.get('ripeti'):
                    chunks[-1].append(a)
            else:
                current.append(a)
        chunks.append(current)

        internal_step = self.task_internal_steps.get(id_task, 0)

        # Determina quale chunk e' "appena finito":
        #
        # PRIMA usavo `internal_step - 1`, ma quel ragionamento e' SBAGLIATO
        # quando l'ultima fase non ha un cooldown dopo: il subprocess
        # termina senza stampare `__COOLDOWN__:`, quindi `internal_step`
        # NON viene incrementato e (internal_step - 1) punta alla fase
        # precedente invece che a quella appena eseguita.
        #
        # La fase appena eseguita e' quella che il subprocess ha ricevuto
        # come parametro `--step`, salvata in `task_last_launched_step`.
        idx_fase = self.task_last_launched_step.get(id_task) if hasattr(self, 'task_last_launched_step') else None
        if idx_fase is None:
            # Fallback: se per qualche motivo non abbiamo lo step lanciato,
            # usiamo la vecchia logica.
            if len(chunks) == 1:
                idx_fase = 0
            elif internal_step == 0:
                print(f"[Ripeti] Task '{nome_t}': multi-fase ma internal_step=0, no rilancio.")
                return False
            else:
                idx_fase = internal_step - 1

        if idx_fase >= len(chunks) or idx_fase < 0:
            print(f"[Ripeti] Task '{nome_t}': idx_fase={idx_fase} fuori range "
                  f"({len(chunks)} chunk), no rilancio.")
            return False
        chunk_corr = chunks[idx_fase]

        # Almeno un'azione del chunk deve avere ripeti=True
        if not any(a.get('ripeti') for a in chunk_corr):
            print(f"[Ripeti] Task '{nome_t}': fase {idx_fase} (chunk con "
                  f"{len(chunk_corr)} azioni) NON ha ripeti=True, no rilancio.")
            return False

        # === CHECK INCROCIATI SULLA RAM ===
        # Cerco la task nella memoria_tasks corrente.
        tipo_t   = task.get('tipo')
        room_t   = task.get('id_stanza')
        nome_t   = task.get('nome', '')

        ram_match = None
        for mt in getattr(self, 'memory_tasks', []):
            if mt.get('tipo') == tipo_t and mt.get('id_stanza') == room_t:
                ram_match = mt
                break

        # SEGNALE A: task non piu' presente in RAM (il gioco l'ha rimossa)
        # Significa che e' stata completata o sostituita -> NON ripetere
        if ram_match is None:
            print(f"[Ripeti] Task '{nome_t}' non piu' in RAM -> "
                  f"considerata completata, no ripetizione.")
            self._reset_retry_count(id_task)  # task finita, reset counter
            return False

        # SEGNALE B: task done in RAM (step == mstep)
        if ram_match.get('done', False):
            print(f"[Ripeti] Task '{nome_t}' done in RAM -> no ripetizione.")
            self._reset_retry_count(id_task)  # task finita, reset counter
            return False

        # SEGNALE C: step in RAM avanzato oltre lo step interno
        # Significa che il gioco ha riconosciuto il progresso della
        # fase appena eseguita -> passa alla fase successiva.
        ram_step = 0
        try:
            cur, _ = ram_match.get('prog', '0/0').split('/')
            ram_step = int(cur)
        except Exception:
            ram_step = 0
        # La fase appena finita ha indice `idx_fase`. Se la RAM ha gia'
        # avanzato a (idx_fase + 1) o oltre, vuol dire che il gioco ha
        # riconosciuto il progresso -> fase finita, stop.
        # NB: usiamo idx_fase+1 invece di internal_step per gestire
        # correttamente sia il caso multi-fase (con cooldown) sia il caso
        # singola fase (idx_fase=0, internal_step=0).
        soglia_avanzamento = idx_fase + 1
        if ram_step >= soglia_avanzamento:
            print(f"[Ripeti] Task '{nome_t}' RAM step={ram_step} "
                  f">= {soglia_avanzamento} -> fase finita, no ripetizione.")
            # Reset del counter tentativi: la fase e' passata
            self._reset_retry_count(id_task, idx_fase)
            return False

        # === LIMITE TENTATIVI ===
        # Tutti i segnali RAM dicono "non finita". Prima di ripetere,
        # controlliamo che non abbiamo gia' raggiunto il numero massimo
        # di tentativi per questa fase (anti-loop).
        #
        # max_tentativi viene letto dalla prima azione del chunk che
        # ha il campo settato; default = 5.
        max_tentativi = 5
        for a in chunk_corr:
            if 'max_tentativi' in a:
                try:
                    max_tentativi = max(1, int(a['max_tentativi']))
                except (ValueError, TypeError):
                    pass
                break

        # Incrementa il counter per questa coppia (id_task, idx_fase)
        if id_task not in self.task_retry_counts:
            self.task_retry_counts[id_task] = {}
        prev = self.task_retry_counts[id_task].get(idx_fase, 0)
        nuovo = prev + 1
        self.task_retry_counts[id_task][idx_fase] = nuovo

        if nuovo >= max_tentativi:
            print(f"[Ripeti] Task '{nome_t}' fase {idx_fase}: "
                  f"raggiunto limite tentativi ({nuovo}/{max_tentativi}). "
                  f"Premo ESC e abbandono la task.")
            # Premi ESC per chiudere eventuale minigioco aperto
            self._premi_esc()
            # Reset counter: prossimo lancio parte pulito
            self._reset_retry_count(id_task, idx_fase)
            # Reset anche dell'internal_step: cosi' al prossimo lancio
            # la task ricomincia da fase 0 (ESC ha presumibilmente
            # chiuso/annullato il minigioco, quindi il gioco riportera'
            # lo step in RAM a 0).
            self.task_internal_steps[id_task] = 0
            # E rimuovo lo step lanciato (per coerenza)
            if hasattr(self, 'task_last_launched_step'):
                self.task_last_launched_step.pop(id_task, None)
            return False

        print(f"[Ripeti] Task '{nome_t}' fase {idx_fase}: "
              f"tentativo {nuovo}/{max_tentativi}.")

        # Tutti i segnali dicono "non finita" e siamo sotto al limite -> ripeti
        return True

    def _reset_retry_count(self, id_task, idx_fase=None):
        """
        Azzera il contatore tentativi per la task.

        Se ``idx_fase`` e' specificato, azzera solo quella fase; altrimenti
        rimuove l'intera entry della task (utile a fine task / reset).
        """
        if id_task not in self.task_retry_counts:
            return
        if idx_fase is None:
            self.task_retry_counts.pop(id_task, None)
        else:
            self.task_retry_counts[id_task].pop(idx_fase, None)
            # Se non restano contatori, rimuovi del tutto
            if not self.task_retry_counts[id_task]:
                self.task_retry_counts.pop(id_task, None)

    def _premi_esc(self):
        """
        Preme il tasto ESC per chiudere un minigioco aperto.

        Usato quando una fase con ripeti=True ha esaurito i tentativi
        senza che la RAM rilevi il completamento: e' la nostra "uscita
        di sicurezza" per non lasciare la finestra del minigioco aperta
        e bloccare la prossima task.
        """
        try:
            import pyautogui
            pyautogui.press('escape')
            time.sleep(0.3)  # grace period perche' il gioco chiuda il pannello
            print("[Ripeti] ESC inviato per chiudere il minigioco.")
        except Exception as e:
            print(f"[Ripeti] Errore invio ESC: {e}")

    def _calcola_start_from_action(self, task):
        """
        Calcola da quale azione del chunk corrente rilanciare il subprocess.

        Logica:
        - Trova il chunk attivo (ultimo lanciato, o derivato da
          internal_step / task_last_launched_step).
        - Trova l'indice della PRIMA azione con `ripeti=True` in quel chunk.
        - Ritorna quell'indice.

        Esempio Swipe Card (no cooldown -> 1 solo chunk):
            azioni = [
                {tipo: click_poly, ripeti: False},
                {tipo: drag_zone,  ripeti: True},
            ]
            -> ritorna 1 (salta il click, ripete solo lo slide)

        Se nessuna azione ha ripeti=True (caso anomalo, non dovrebbe
        accadere perche' siamo qui solo se _fase_da_ripetere_ext ha
        ritornato True), ritorna 0 (= riparte da capo come fallback).
        """
        id_task = task['id']
        azioni_eff, _ = self.task_mgr.get_azioni_effettive(id_task)

        # Ricostruisci i chunk (split sui cooldown, identico al dispatcher)
        chunks = []
        current_chunk = []
        for az in azioni_eff:
            if az.get('tipo') == 'cooldown':
                chunks.append(current_chunk)
                current_chunk = []
            else:
                current_chunk.append(az)
        chunks.append(current_chunk)

        # Quale chunk e' attivo? Uso task_last_launched_step se disponibile
        idx_fase = (self.task_last_launched_step.get(id_task)
                    if hasattr(self, 'task_last_launched_step') else None)
        if idx_fase is None:
            internal_step = self.task_internal_steps.get(id_task, 0)
            idx_fase = internal_step if internal_step < len(chunks) else len(chunks) - 1

        if idx_fase < 0 or idx_fase >= len(chunks):
            return 0

        chunk_corr = chunks[idx_fase]

        # Trova la prima azione con ripeti=True nel chunk
        for i, a in enumerate(chunk_corr):
            if a.get('ripeti', False):
                return i

        # Fallback: nessun ripeti -> riparte da capo
        return 0

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
