"""
Thread di lettura RAM (posizione + task) e sync nomi.

Mixin di GPSVisualizerPro: metodi separati per organizzazione, ma
condividono lo stato self.* della classe principale.
"""

from ._imports import *


# Numero di letture consecutive in cui una task deve essere ASSENTE dalla
# RAM prima di considerarla "completata e quindi scomparsa".
# A 50ms di polling RAM, 3 letture = ~150 ms di assenza confermata.
# Anti-flicker: la RAM puo' "perdere" temporaneamente una task per timing,
# quindi richiediamo conferma per non interrompere prematuramente.
STOP_MISSING_READS = 3


class MemorySyncMixin:
    """Mixin con i metodi di memory sync di GPSVisualizerPro."""
    def _leggi_memoria(self):
        """Loop principale del thread di lettura RAM."""
        # Loop infinito finche' l'app e' in running. Il thread vive per
        # tutta la durata dell'applicazione.
        while self.running:
            # --- 1) Posizione giocatore ---
            # Legge dalla RAM le coordinate (x, y) del giocatore locale.
            # Restituisce None se la struct di gioco non e' ancora pronta
            # (es. siamo nella lobby o in transizione di scena).
            pos = self.reader.get_position()
            if pos:
                # Aggiorna il target della camera. Sara' la prossima
                # posizione che il rendering interpolera' nel frame.
                self.pos_target = list(pos)

            # --- 2) Task in memoria del gioco ---
            # Legge la lista task del player dalla RAM. Ognuna ha:
            # tipo, id_stanza, nome (se gia' tradotto dal gioco), done.
            tasks = self.task_reader.get_tasks()
            if tasks is not None:
                self.memory_tasks = tasks
                # Sync automatica: se una task ha raw_game_id e il gioco
                # ora conosce il nome vero (es. "Swipe Card" invece di
                # "Task Type 5"), aggiorna il JSON delle task registrate.
                self._sync_nomi_task_da_ram(tasks)

                # --- 3) Reset step interni delle task completate ---
                # Quando una task viene completata in gioco (done=True),
                # azzeriamo il contatore degli step interni (usato per
                # le task multi-step come "Submit Scan").
                # Itera le task lette dalla RAM del gioco
                for mt in tasks:
                    if mt.get('done', False):
                        # Cerca la task registrata con (tipo, id_stanza)
                        reg = self.task_mgr.find_registered(tipo=mt.get('tipo'), id_stanza=mt.get('id_stanza'))
                        # Se esiste in registro e ha uno step in corso,
                        # resetta a 0 (la task ricomincera' da capo se
                        # riavviata).
                        if reg and reg['id'] in self.task_internal_steps:
                            self.task_internal_steps[reg['id']] = 0
                        # Reset anche del counter tentativi: la task e'
                        # finita, il prossimo lancio parte da zero.
                        if reg and reg['id'] in getattr(self, 'task_retry_counts', {}):
                            self.task_retry_counts.pop(reg['id'], None)

            # --- 5) STOP WATCHER: la fase e' avanzata in RAM? ---
            # Se c'e' un subprocess attivo per una task e lo step di
            # quella task in RAM e' avanzato OLTRE quello al lancio,
            # significa che la fase e' stata completata dal gioco.
            # Mandiamo "STOP\n" sullo stdin del subprocess cosi' che
            # interrompa eventuali azioni residue (utile per task tipo
            # Divert Power dove si fa drag su 8 interruttori e solo
            # uno e' quello giusto).
            self._stop_watcher_check(tasks)

            # --- 6) Sleep tra letture ---
            # 50 ms = 20 letture al secondo. Sufficiente per una camera
            # smooth senza sovraccaricare la CPU con accessi RAM.
            time.sleep(0.05)

    def _stop_watcher_check(self, ram_tasks):
        """
        Se la fase corrente del subprocess attivo e' stata risolta
        in RAM, invia "STOP" allo stdin del subprocess.

        Idempotente: una volta inviato lo STOP per una task, non lo
        rinvia (`task_stop_sent` e' un set di id_task gia' notificati).
        Si pulisce automaticamente quando il subprocess termina (in
        `_controlla_processo_task`).
        """
        # Se non c'e' subprocess attivo, niente da fare
        proc = getattr(self, '_task_process', None)
        proc_id = getattr(self, '_task_process_task_id', None)
        if proc is None or proc_id is None:
            return
        # Se non abbiamo lo step iniziale (fallback safety), niente da fare
        ram_step_launch_dict = getattr(self, 'task_ram_step_at_launch', {})
        if proc_id not in ram_step_launch_dict:
            return
        ram_step_launch = ram_step_launch_dict[proc_id]

        # Set degli id_task gia' notificati con STOP (per non spammare)
        if not hasattr(self, 'task_stop_sent'):
            self.task_stop_sent = set()
        if proc_id in self.task_stop_sent:
            return  # gia' notificato

        # Trovo la task registrata
        try:
            reg = self.task_mgr.get_by_id(proc_id)
        except Exception:
            return
        if reg is None:
            return
        tipo_t = reg.get('tipo')
        id_stanza_t = reg.get('id_stanza')

        # Trovo la task in RAM con lo stesso (tipo, id_stanza)
        ram_match = None
        for mt in (ram_tasks or []):
            if mt.get('tipo') == tipo_t and mt.get('id_stanza') == id_stanza_t:
                ram_match = mt
                break

        # Logica unificata: la task in esecuzione e' "conclusa" se la RAM
        # mostra UNO dei tre segnali:
        #   1. ram_match.done == True             (esplicitamente done)
        #   2. ram_match.step > ram_step_launch   (step avanzato dal lancio)
        #   3. ram_match assente                  (scomparsa = completata)
        #
        # Il caso 3 e' quello che gestisce task multi-azione come Divert
        # Power: appena lo slider giusto e' azzeccato, la task scompare
        # dalla lista RAM. Vogliamo fermarci subito invece di continuare
        # con i drag rimanenti.
        #
        # Per evitare di fermare prematuramente task lunghe (es. Clean O2
        # Filter che potrebbero non essere sempre in RAM durante esecuzione),
        # applico due salvaguardie al caso 3:
        #   a) Anti-flicker: serve assenza per STOP_MISSING_READS letture
        #      consecutive (~150ms)
        #   b) Sentinella "vista almeno una volta": se la task non e' mai
        #      stata vista in RAM dal lancio del subprocess, NON mandiamo
        #      STOP. Probabilmente la RAM non riporta quel tipo del tutto,
        #      l'assenza non significa "completata".
        should_stop = False
        stop_reason = ""

        # Inizializzo i tracker se mancanti (lazy init)
        if not hasattr(self, 'task_missing_reads'):
            self.task_missing_reads = {}
        if not hasattr(self, 'task_seen_in_ram'):
            self.task_seen_in_ram = set()

        if ram_match is not None:
            # Task presente in RAM: marca come "vista", reset counter missing
            self.task_seen_in_ram.add(proc_id)
            self.task_missing_reads.pop(proc_id, None)

            if ram_match.get('done', False):
                should_stop = True
                stop_reason = "task done in RAM"
            else:
                # Confronto step corrente vs step al lancio.
                # ram_match['prog'] di solito e' "N/M" stringa.
                try:
                    prog = ram_match.get('prog', '0/0')
                    curr_step = int(str(prog).split('/')[0])
                    if curr_step > ram_step_launch:
                        should_stop = True
                        stop_reason = (
                            f"step avanzato {ram_step_launch}->{curr_step}"
                        )
                except (ValueError, AttributeError):
                    pass
        else:
            # Task NON presente in RAM.
            # Mandiamo STOP solo se era stata vista almeno una volta dal
            # lancio E l'assenza e' confermata su STOP_MISSING_READS letture
            # consecutive.
            if proc_id in self.task_seen_in_ram:
                self.task_missing_reads[proc_id] = (
                    self.task_missing_reads.get(proc_id, 0) + 1
                )
                if self.task_missing_reads[proc_id] >= STOP_MISSING_READS:
                    should_stop = True
                    stop_reason = (
                        f"task scomparsa dalla RAM "
                        f"(dopo {STOP_MISSING_READS} letture) = completata"
                    )
            # Se non e' mai stata vista in RAM dal lancio: NIENTE STOP.
            # Probabilmente la RAM non supporta questo tipo di task.

        if should_stop:
            print(f"[StopWatcher] Task {proc_id} ({reg.get('nome','?')}): "
                  f"{stop_reason}, invio STOP", flush=True)
            self._invia_stop_subprocess(proc_id)
            self.task_stop_sent.add(proc_id)

    def _invia_stop_subprocess(self, id_task):
        """
        Invia 'STOP\\n' sullo stdin del subprocess attivo.

        Idempotente: se stdin non e' disponibile (subprocess gia' morto,
        thread mode, ecc.), non fa nulla e non logga errore.
        """
        proc = getattr(self, '_task_process', None)
        if proc is None:
            return
        proc_stdin = getattr(proc, 'stdin', None)
        if proc_stdin is None:
            return
        try:
            proc_stdin.write(b"STOP\n")
            proc_stdin.flush()
            print(f"[StopWatcher] Inviato STOP a task {id_task} "
                  f"(RAM avanzata)", flush=True)
        except (BrokenPipeError, ValueError, OSError):
            # subprocess gia' chiuso o stdin non scrivibile: niente da fare
            pass

    def _sync_nomi_task_da_ram(self, ram_tasks):
        """
        Aggiorna i nomi testuali nel JSON se la RAM fornisce nomi migliori.
        Usa la combinazione (tipo, id_stanza) come chiave.
        """
        # Senza task RAM non c'e' niente da sincronizzare
        if not ram_tasks:
            return

        # --- Costruisce mappa (tipo, id_stanza) -> nome dal gioco ---
        # Saltiamo i nomi placeholder "Task Type N" che non sono
        # informativi (vengono usati quando il gioco non ha ancora
        # caricato la traduzione del nome).
        # Mappa (tipo, id_stanza) -> nome dal gioco
        ram_dict = {(mt['tipo'], mt['id_stanza']): mt['nome'] for mt in ram_tasks
                    if not mt['nome'].startswith("Task Type ")}

        # Flag: True se almeno una task e' stata aggiornata (per salvare
        # il JSON solo una volta alla fine, non a ogni iterazione).
        aggiornato = False
        # Itera tutte le task registrate
        for t in self.task_mgr.task_list:
            # Chiave di matching: la stessa coppia (tipo, id_stanza)
            chiave = (t.get('tipo'), t.get('id_stanza'))
            nome_gioco = ram_dict.get(chiave)

            # Niente da fare se la RAM non conosce questa task
            if nome_gioco is None:
                continue

            # --- Costruisce il nome atteso ---
            # Format: "Zona: NomeTask" (es. "Admin: Swipe Card").
            # Se la task non ha zona associata, solo il nome puro.
            prefisso = f"{t.get('nome_zona')}: " if t.get('nome_zona') else ""
            nome_atteso = f"{prefisso}{nome_gioco}"

            # Aggiorna solo se diverso (per non scatenare salvataggi inutili)
            if t['nome'] != nome_atteso:
                t['nome'] = nome_atteso
                aggiornato = True

        # Salva su disco solo se almeno un nome e' cambiato.
        if aggiornato:
            # Salva il registro delle task su disco
            self.task_mgr.salva()
            # Flag per il main thread: deve refreshare la listbox
            # delle task nel pannello (non possiamo farlo da qui
            # perche' DPG non e' thread-safe).
            self._pending_refresh_task_list = True
