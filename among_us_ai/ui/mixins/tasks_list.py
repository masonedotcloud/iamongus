"""
Liste task (memoria + registrate), navigazione e selezione.

Mixin di GPSVisualizerPro: metodi separati per organizzazione, ma
condividono lo stato self.* della classe principale.
"""

from ._imports import *



class TasksListMixin:
    """Mixin con i metodi di tasks list di GPSVisualizerPro."""
    def _refresh_mem_task_listbox(self):
        """
        Aggiorna la listbox task in memoria senza il match ID.
        Formato: [STATO] [ID:ROOM_ID] LUOGO: NOME TASK [PROG] (COORD)
        """
        enriched = self.task_mgr.get_memory_tasks_info(self.memory_tasks)
        
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist("sort_mem_tasks_chk") and dpg.get_value("sort_mem_tasks_chk"):
            enriched.sort(key=lambda x: (x['reg_task']['nome'] if x.get('reg_task') else x['nome']).lower())
            
        items = []
        for t in enriched:
            # Stato: [V] completata, [-] in corso
            stato = "[V]" if t['done'] else "[-]"
            id_stanza = t.get('id_stanza', '?')
            reg = t['reg_task']
            
            if reg:
                # Controllo Cooldown
                cd = self.task_cooldowns.get(reg['id'], 0)
                rem = cd - time.time()
                
                # Task Registrata: Formato "Luogo: Nome Task"
                # Puliamo il nome da eventuali prefissi doppi
                nome_pulito = reg['nome'].split(": ", 1)[-1]
                luogo = reg.get('nome_zona', 'Mappa')
                display_name = f"{luogo}: {nome_pulito}"
                
                coord_str = f" ({reg['x']:.1f},{reg['y']:.1f})"
                
                if rem > 0:
                    items.append(f"[WAIT {int(rem)}s] [ID:{id_stanza}] {display_name} [{t['prog']}]{coord_str}")
                else:
                    items.append(f"{stato} [ID:{id_stanza}] {display_name} [{t['prog']}]{coord_str}")
            else:
                # Task Sconosciuta: Nome base dalla RAM
                items.append(f"{stato} [ID:{id_stanza}] {t['nome']} [{t['prog']}]")
                
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist("mem_task_listbox"):
            # Cambia le configurazioni di un widget gia' creato
            dpg.configure_item("mem_task_listbox", items=items)

    def _refresh_reg_task_listbox(self):
        """
        Aggiorna la listbox delle task registrate dall'utente con tutti i
        dettagli rilevanti: flag vitale/due-giocatori, zona, numero fasi,
        e SOPRATTUTTO il legame padre/figlia (sia da che a) e l'origine
        delle azioni (proprie o ereditate).

        Formato riga:
            [ID] [!][2P] Nome  A:N  +Nf  [Z:gzid=nome]  ->P:XX  +Nfigli
        dove:
            A:N      = numero azioni proprie
            A:0<-PXX  = questa task non ha azioni proprie e le eredita da XX
            ->P:XX    = questa task e' FIGLIA di XX (indipendente dal fatto che
                       erediti o meno: puo' anche avere azioni proprie)
            +Nfigli  = questa task e' PADRE di N task figlie
        """
        items = []
        
        tasks_to_render = list(self.task_mgr.task_list)
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist("sort_reg_tasks_chk") and dpg.get_value("sort_reg_tasks_chk"):
            tasks_to_render.sort(key=lambda x: x['nome'].lower())
            
        for t in tasks_to_render:
            vitale_str = " [!]" if t.get('vitale') else ""
            due_p_str  = " [2P]" if t.get('due_giocatori') else ""
            custom_str = " [C]" if t.get('codice_personalizzato') else ""

            # Fasi
            n_fasi   = len(t.get('fasi', []))
            fasi_str = f" +{n_fasi}f" if n_fasi else ""
            
            # Alternativi
            n_frat   = len(t.get('alternativi', []))
            frat_str = f" ~{n_frat}fr" if n_frat else ""

            # Zona
            id_zona  = t.get('id_zona')
            zona_str = ""
            if id_zona is not None:
                z = self.zone_mgr.get_by_game_zone_id(id_zona)
                zona_str = f" [Z:{id_zona}={z['nome'] if z else '?'}]"

            # Azioni: numero proprie + eventuale ereditarieta'
            n_azioni_proprie = len(t.get('azioni', []))
            if n_azioni_proprie > 0:
                azioni_str = f" A:{n_azioni_proprie}"
            else:
                # Nessuna azione propria: controllo se eredita dal padre
                _, src_id = self.task_mgr.get_azioni_effettive(t['id'])
                if src_id is not None and src_id != t['id']:
                    azioni_str = f" A:0<-P{src_id:02d}"
                else:
                    azioni_str = " A:0"

            # Relazioni padre/figlia
            parent_str  = ""
            id_padre   = t.get('id_padre')
            if id_padre is not None:
                padre = self.task_mgr.get_by_id(id_padre)
                parent_nome = (padre['nome'].split(": ", 1)[-1][:15]
                               if padre else '?')
                parent_str = f"  ->P:{id_padre:02d}({parent_nome})"

            # Task padre di quante figlie?
            figli = self.task_mgr.get_figli(t['id'])
            figli_str = f"  +{len(figli)}figli" if figli else ""

            items.append(
                f"[{t['id']:02d}]{vitale_str}{due_p_str}{custom_str} {t['nome']}"
                f"{azioni_str}{fasi_str}{frat_str}{zona_str}{parent_str}{figli_str}"
            )

        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist("reg_task_listbox"):
            # Cambia le configurazioni di un widget gia' creato
            dpg.configure_item("reg_task_listbox", items=items)

    def _get_selected_mem_task(self):
        """
        Ritorna la task RAM selezionata ricostruendo la stringa esatta per il match.
        """
        if not self.memory_tasks:
            return None
        # Verifica se l'elemento DPG e' gia' stato creato
        if not dpg.does_item_exist("mem_task_listbox"):
            return None
        
        sel = dpg.get_value("mem_task_listbox")
        if not sel:
            return None
            
        enriched = self.task_mgr.get_memory_tasks_info(self.memory_tasks)
        for t in enriched:
            stato = "[V]" if t['done'] else "[-]"
            id_stanza = t.get('id_stanza', '?')
            reg = t['reg_task']
            
            if reg:
                # Sincronizza il prefisso WAIT per far combaciare correttamente la stringa
                cd = self.task_cooldowns.get(reg['id'], 0)
                rem = cd - time.time()
                
                nome_pulito = reg['nome'].split(": ", 1)[-1]
                luogo = reg.get('nome_zona', 'Mappa')
                display_name = f"{luogo}: {nome_pulito}"
                coord_str = f" ({reg['x']:.1f},{reg['y']:.1f})"
                
                if rem > 0:
                    item_str = f"[WAIT {int(rem)}s] [ID:{id_stanza}] {display_name} [{t['prog']}]{coord_str}"
                else:
                    item_str = f"{stato} [ID:{id_stanza}] {display_name} [{t['prog']}]{coord_str}"
            else:
                item_str = f"{stato} [ID:{id_stanza}] {t['nome']} [{t['prog']}]"
                
            if item_str == sel:
                return t
                
        return None

    def _get_selected_reg_task(self):
        """Ritorna selected reg task."""
        if not self.task_mgr.task_list:
            return None
        # Verifica se l'elemento DPG e' gia' stato creato
        if not dpg.does_item_exist("reg_task_listbox"):
            return None
        sel = dpg.get_value("reg_task_listbox")
        if not sel:
            return None
        try:
            id_str = sel.split(']')[0].lstrip('[').strip()
            id_num = int(id_str)
            return self.task_mgr.get_by_id(id_num)
        except (ValueError, IndexError):
            return None

    def _naviga_a_task_memoria(self, task_to_nav=None):
        """Naviga con A* verso la task in memoria selezionata, usando le coordinate registrate."""
        t = task_to_nav if task_to_nav is not None else self._get_selected_mem_task()
        if t is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una task dalla lista memoria"
            return
        reg = t.get('reg_task')
        if reg is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"Task '{t['nome']}' non ancora registrata - aggiungila prima"
            return
            
        # Controllo Cooldown
        rem = self.task_cooldowns.get(reg['id'], 0) - time.time()
        if rem > 0:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"Task in cooldown. Riprova tra {int(rem)}s"
            return
            
        if not self.auto_enabled:
            self.auto_enabled = True
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist("auto_checkbox"):
                # Aggiorna il valore di un widget DPG
                dpg.set_value("auto_checkbox", True)
        
        target_2p, step_2p = self._imposta_navigazione_2p(reg)
        if target_2p:
            self._plan_path(target_2p)
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"Navigo verso '{reg['nome']}' (Tappa {step_2p})"
        else:
            punti_possibili = [(reg['x'], reg['y'])]
            for fr in reg.get('alternativi', []):
                punti_possibili.append((fr['x'], fr['y']))
                
            if len(punti_possibili) > 1:
                self._task_alternativi_pendenti = punti_possibili
                cx, cy = self.pos_target
                closest = min(punti_possibili, key=lambda p: math.hypot(cx - p[0], cy - p[1]))
                tx, ty = closest
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = f"Navigo verso '{reg['nome']}' (Cerco lock visivo...)"
            else:
                self._task_alternativi_pendenti = None
                tx, ty, step = self._get_task_target_coords(reg)
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = f"Navigo verso '{reg['nome']}'"
                
            self._plan_path((tx, ty))

    def _modifica_task_da_memoria(self):
        """
        Apre il popup di modifica per la task REGISTRATA collegata alla task
        in memoria attualmente selezionata.
        Utile per modificare nome, coordinate, azioni, padre/figlia ecc. senza
        dover prima trovare manualmente la corrispondente voce nella lista
        delle task registrate.
        Se la task in memoria non e' ancora registrata, suggerisce di usare
        prima il pulsante 'Registra ?'.
        """
        t = self._get_selected_mem_task()
        if t is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una task dalla lista memoria"
            return
        reg = t.get('reg_task')
        if reg is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = (
                f"'{t['nome']}' non e' ancora registrata - "
                f"usa 'Registra ?' per aggiungere i dettagli, "
                f"poi potrai modificarla qui."
            )
            return
        # Apre il popup di modifica passando la task registrata direttamente,
        # senza bisogno di selezionarla prima nella listbox delle registrate.
        self._apri_popup_modifica_task(task=reg)

    def _naviga_a_task_registrata(self):
        """Avvia la navigazione A* verso task registrata."""
        t = self._get_selected_reg_task()
        if t is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una task registrata"
            return
        if not self.auto_enabled:
            self.auto_enabled = True
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist("auto_checkbox"):
                # Aggiorna il valore di un widget DPG
                dpg.set_value("auto_checkbox", True)
                
        target_2p, step_2p = self._imposta_navigazione_2p(t)
        if target_2p:
            self._plan_path(target_2p)
            label_loc = 'A' if target_2p == getattr(self, 'auto_2p_loc_A', None) else 'B'
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"Navigo verso '{t['nome']}' (2P - Loc {label_loc})"
        else:
            self._plan_path((t['x'], t['y']))
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"Navigo verso '{t['nome']}'"

    def _elimina_task_registrata(self):
        """Elimina task registrata."""
        t = self._get_selected_reg_task()
        if t is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una task da eliminare"
            return
        nome = t['nome']
        id_t = t['id']
        def on_confirm(yes):
            """Callback di conferma."""
            if yes:
                # Rimuove la task dal registro (cancella anche il file di esecuzione)
                self.task_mgr.rimuovi(id_t)
                # Sia la lista registrate (sparisce la task) sia la lista memoria
                # (la voce collegata diventa "non registrata") devono aggiornarsi.
                self._refresh_reg_task_listbox()
                self._refresh_mem_task_listbox()
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = f"Task '{nome}' eliminata"
        self._show_confirm(f"Eliminare la task '{nome}' ?", on_confirm)

    def _get_id_task_da_riga(self, nome_task):
        """
        Cerca l'ID numerico grezzo del gioco per una task dato il suo nome,
        scorrendo le definizioni caricate da tasks.json.
        """
        # Prima prova nei task_def del reader (da tasks.json)
        for tid, info in self.task_reader.skeld_tasks.items():
            if info.get("n", "") == nome_task:
                return tid
        # Fallback: cerca nel TaskManager def
        for tid, info in self.task_mgr.tasks_def.items():
            if info.get("n", "") == nome_task:
                return tid
        return None
