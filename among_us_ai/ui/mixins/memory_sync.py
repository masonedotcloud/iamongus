"""
Thread di lettura RAM (posizione + task) e sync nomi.

Mixin di GPSVisualizerPro: metodi separati per organizzazione, ma
condividono lo stato self.* della classe principale.
"""

from ._imports import *



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

            # --- 4) Sleep tra letture ---
            # 50 ms = 20 letture al secondo. Sufficiente per una camera
            # smooth senza sovraccaricare la CPU con accessi RAM.
            time.sleep(0.05)

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
