"""
Popup di creazione e modifica task.

Mixin di GPSVisualizerPro.
"""

from ._imports import *


class TasksPopupsEditMixin:
    """Mixin con i metodi di tasks popups edit di GPSVisualizerPro."""
    def _apri_popup_nuova_task(self):
        """Apre il popup nuova task."""
        tag = "popup_nuova_task"
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist(tag):
            # Rimuove l'elemento DPG (cleanup)
            dpg.delete_item(tag)
        px, py = self.pos_target
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()

        # --- Rileva zona corrente ---
        zona_corrente = self._zona_alla_posizione(px, py)
        nome_zona     = zona_corrente['nome']       if zona_corrente else None
        game_zone_id  = zona_corrente.get('game_zone_id') if zona_corrente else None
        id_zona_locale = zona_corrente['id']         if zona_corrente else None

        # Nome vuoto - l'utente lo inserisce manualmente
        nome_default = ""

        # Info zona per mostrare nel popup
        zona_info = ""
        if zona_corrente:
            gzid_str  = f"  game_zone_id={game_zone_id}" if game_zone_id is not None else "  (nessun game_zone_id)"
            zona_info = f"Zona rilevata: [{id_zona_locale:02d}] {nome_zona}{gzid_str}"
        else:
            zona_info = "Posizione fuori da qualsiasi zona registrata"

        def do_salva(*_):
            """Callback del bottone Salva del popup."""
            nome_v      = dpg.get_value("nt_nome").strip()
            x_v         = dpg.get_value("nt_x")
            y_v         = dpg.get_value("nt_y")
            vitale_v    = dpg.get_value("nt_vitale")
            due_p_v     = dpg.get_value("nt_due_p")
            if not nome_v:
                return

            # 1. Ricava zona e ID locali in base alle coordinate
            zona_s  = self._zona_alla_posizione(x_v, y_v)
            gz_id_s = zona_s.get('game_zone_id') if zona_s else None
            zl_id_s = zona_s['id']               if zona_s else None

            # 2. Ricava tipo e id_stanza dalla RAM (identificatori univoci).
            # NB: le memory_tasks non hanno un 'raw_game_id' (vedi
            # AmongUsTaskReader.get_tasks): la chiave univoca e' (tipo, id_stanza).
            matched_mem = None
            nome_bare   = nome_v.split(": ", 1)[-1].lower()

            # Cerca per nome esatto
            for mt in self.memory_tasks:
                if mt['nome'].lower() == nome_bare or mt['nome'].lower() == nome_v.lower():
                    matched_mem = mt
                    break

            # Fallback: prendi una task non ancora registrata che si trova
            # nella stessa stanza di gioco del punto cliccato
            if matched_mem is None and gz_id_s is not None:
                enriched = self.task_mgr.get_memory_tasks_info(self.memory_tasks)
                for mt in enriched:
                    if mt.get('id_stanza') == gz_id_s and not mt.get('registrata'):
                        matched_mem = mt
                        break

            # 3. Costruisce e salva il JSON
            self.task_mgr.aggiungi(
                nome_v, x_v, y_v,
                id_stanza       = matched_mem['id_stanza']  if matched_mem else None,
                tipo          = matched_mem.get('tipo') if matched_mem else None,
                id_zona       = gz_id_s,
                id_zona_locale = zl_id_s,
                nome_zona     = zona_s['nome'] if zona_s else None,
                vitale        = vitale_v,
                due_giocatori = due_p_v,
            )
            self._refresh_reg_task_listbox()
            self._refresh_mem_task_listbox()

            msg = f"Task '{nome_v}' registrata"
            if zona_s:      msg += f" in '{zona_s['nome']}'"
            if matched_mem: msg += f" (tipo={matched_mem.get('tipo')} room={matched_mem.get('id_stanza')})"
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = msg
            
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist(tag):
                # Rimuove l'elemento DPG (cleanup)
                dpg.delete_item(tag)

        def do_usa_pos(*_):
            """Callback del bottone \"Usa posizione attuale\"."""
            nx = round(self.pos_target[0], 3)
            ny = round(self.pos_target[1], 3)
            # Aggiorna il valore di un widget DPG
            dpg.set_value("nt_x", nx)
            # Aggiorna il valore di un widget DPG
            dpg.set_value("nt_y", ny)
            # Aggiorna label zona in tempo reale
            z2 = self._zona_alla_posizione(nx, ny)
            if z2:
                gz2   = z2.get('game_zone_id')
                info2 = f"Zona: [{z2['id']:02d}] {z2['nome']}" + (f"  GZ:{gz2}" if gz2 is not None else "")
            else:
                info2 = "Posizione fuori da qualsiasi zona"
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist("nt_zona_info"):
                # Aggiorna il valore di un widget DPG
                dpg.set_value("nt_zona_info", info2)

        col_zona = Colors.ACCENT if zona_corrente else (200, 120, 30, 255)
        # Apre la finestra
        with dpg.window(label="Nuova Task", tag=tag, modal=True, no_resize=True,
                        no_collapse=True, width=400, height=275,
                        pos=(max(0, vp_w // 2 - 200), max(0, vp_h // 2 - 147))):
            dpg.add_text(zona_info, tag="nt_zona_info", color=col_zona, wrap=390)
            dpg.add_spacer(height=4)
            dpg.add_text("Nome task  (pre-compilato con zona):")
            dpg.add_input_text(tag="nt_nome", default_value=nome_default, width=-1)
            dpg.add_spacer(height=4)
            dpg.add_text("Coordinate posizione principale:")
            with dpg.group(horizontal=True):
                dpg.add_text("X:")
                dpg.add_input_float(tag="nt_x", default_value=round(px, 3), width=155, step=0)
                dpg.add_text("Y:")
                dpg.add_input_float(tag="nt_y", default_value=round(py, 3), width=155, step=0)
            dpg.add_button(label="Usa posizione attuale  (aggiorna zona)", width=-1,
                           callback=do_usa_pos)
            dpg.add_spacer(height=6)
            dpg.add_checkbox(tag="nt_vitale", label=" Task di VITALE importanza  [!]",
                             default_value=False)
            dpg.add_checkbox(tag="nt_due_p", label=" Richiede due giocatori  [2P]",
                             default_value=False)
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Salva", width=190, callback=do_salva)
                dpg.add_button(label="Annulla", width=190,
                               # Rimuove l'elemento DPG (cleanup)
                               callback=lambda *a: dpg.delete_item(tag)
                               # Verifica se l'elemento DPG e' gia' stato creato
                               if dpg.does_item_exist(tag) else None)

    def _apri_popup_modifica_task(self, task=None):
        """Apre il popup modifica task."""
        # task puo' essere passato direttamente (es. aperto da lista memoria)
        # oppure viene risolto dalla listbox delle task registrate.
        t = task if task is not None else self._get_selected_reg_task()
        if t is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una task da modificare"
            return
        tag = "popup_modifica_task"
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist(tag):
            # Rimuove l'elemento DPG (cleanup)
            dpg.delete_item(tag)
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        id_t = t['id']

        def do_salva(*_):
            """Callback del bottone Salva del popup."""
            nome_v   = dpg.get_value("mt_nome").strip()
            x_v      = dpg.get_value("mt_x")
            y_v      = dpg.get_value("mt_y")
            vitale_v = dpg.get_value("mt_vitale")
            due_p_v  = dpg.get_value("mt_due_p")
            custom_v = dpg.get_value("mt_custom")
            lung_v   = dpg.get_value("mt_lunghezza")
            # Verifica se l'elemento DPG e' gia' stato creato
            parent_v = dpg.get_value("mt_parent") if dpg.does_item_exist("mt_parent") else "- (nessuno)"
            if not nome_v:
                return
            # Aggiorna i dati strutturali della task
            self.task_mgr.aggiorna(id_t, nome_v, x_v, y_v, vitale=vitale_v, due_giocatori=due_p_v, codice_personalizzato=custom_v, lunghezza=lung_v)
            # Estrai id del padre dal combo (formato "[ID] nome" o "- (nessuno)")
            new_parent = None
            if parent_v and parent_v.startswith("["):
                try:
                    new_parent = int(parent_v[1:parent_v.index("]")])
                except Exception:
                    new_parent = None
            # Imposta il padre della task (per ereditarieta' delle azioni)
            if not self.task_mgr.imposta_padre(id_t, new_parent):
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = f"Parent invalido (self-loop o padre gia' figlio): ignorato"
            # Refresh di ENTRAMBE le liste: la modifica di una task registrata
            # (nome, coordinate, parent) si riflette in qualunque voce della
            # lista-memoria che la referenzia via (tipo, id_stanza).
            self._refresh_reg_task_listbox()
            self._refresh_mem_task_listbox()
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"Task [{id_t}] aggiornata"
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist(tag):
                # Rimuove l'elemento DPG (cleanup)
                dpg.delete_item(tag)

        def do_usa_pos(*_):
            """Callback del bottone \"Usa posizione attuale\"."""
            # Aggiorna il valore di un widget DPG
            dpg.set_value("mt_x", round(self.pos_target[0], 3))
            # Aggiorna il valore di un widget DPG
            dpg.set_value("mt_y", round(self.pos_target[1], 3))

        def do_apri_editor(*_):
            """Callback: apre l'editor delle azioni della task selezionata."""
            # Chiudi il popup modale: l'editor e' una finestra DPG autonoma
            # e la dashboard deve continuare a renderizzare normalmente.
            if dpg.does_item_exist(tag):
                # Rimuove l'elemento DPG (cleanup)
                dpg.delete_item(tag)

            # Callback per l'evento
            def _on_save(id_salvata):
                """Callback per l'evento save."""
                # Rigenera il file .py con le nuove azioni
                self.task_mgr.crea_file_esecuzione(id_salvata)
                # Il numero di azioni e' mostrato sia nella lista registrate sia
                # (indirettamente, come stato) nella lista memoria: refresh di entrambe.
                self._refresh_reg_task_listbox()
                self._refresh_mem_task_listbox()
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = f"Azioni task [{id_salvata}] salvate + file .py rigenerato"

            self.action_editor.apri(id_t, on_save=_on_save)

        with dpg.window(label=f"Modifica Task [{id_t}]", tag=tag, modal=True,
                        no_resize=True, no_collapse=True, width=460, height=670,
                        pos=(max(0, vp_w // 2 - 230), max(0, vp_h // 2 - 335))):

            # ========== SEZIONE 1: IDENTITA' ==========
            dpg.add_text("IDENTITA'", color=Colors.ACCENT)
            dpg.add_separator()
            dpg.add_text("Nome task:")
            dpg.add_input_text(tag="mt_nome", default_value=t['nome'], width=-1)

            dpg.add_spacer(height=4)
            dpg.add_text("Coordinate posizione principale:")
            with dpg.group(horizontal=True):
                dpg.add_text("X:")
                dpg.add_input_float(tag="mt_x", default_value=t['x'],
                                    width=150, step=0, format="%.3f")
                dpg.add_text("Y:")
                dpg.add_input_float(tag="mt_y", default_value=t['y'],
                                    width=150, step=0, format="%.3f")
            dpg.add_button(label="Usa posizione attuale", width=-1, callback=do_usa_pos)

            # Flag vitale / due giocatori
            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True):
                dpg.add_checkbox(tag="mt_vitale", label=" VITALE [!]",
                                 default_value=bool(t.get('vitale', False)))
                dpg.add_checkbox(tag="mt_due_p", label=" 2 giocatori [2P]",
                                 default_value=bool(t.get('due_giocatori', False)))
            
            with dpg.group(horizontal=True):
                dpg.add_text("Lunghezza:")
                dpg.add_combo(items=["N/A", "Short", "Long", "Common"], tag="mt_lunghezza", default_value=t.get('lunghezza', 'N/A'), width=120)
            
            dpg.add_checkbox(tag="mt_custom", label=" Codice Custom (non sovrascrivere il .py)",
                             default_value=bool(t.get('codice_personalizzato', False)))

            # ========== SEZIONE 2: FASI E FRATELLI ==========
            dpg.add_spacer(height=8)
            dpg.add_text("FASI E FRATELLI", color=Colors.ACCENT)
            dpg.add_separator()
            
            def delete_fase(s, a, u):
                """Callback: elimina una fase dalla task in modifica."""
                # Aggiorna i dati strutturali della task
                self.task_mgr.aggiorna(id_t, dpg.get_value("mt_nome").strip() or t['nome'], dpg.get_value("mt_x"), dpg.get_value("mt_y"), dpg.get_value("mt_vitale"), dpg.get_value("mt_due_p"), dpg.get_value("mt_custom"), lunghezza=dpg.get_value("mt_lunghezza"))
                # Rimuove una fase intermedia dalla task
                self.task_mgr.rimuovi_fase(id_t, u)
                self._apri_popup_modifica_task(task=self.task_mgr.get_by_id(id_t))
                
            def delete_alternativo(s, a, u):
                """Callback: elimina un alternativo dalla task in modifica."""
                # Aggiorna i dati strutturali della task
                self.task_mgr.aggiorna(id_t, dpg.get_value("mt_nome").strip() or t['nome'], dpg.get_value("mt_x"), dpg.get_value("mt_y"), dpg.get_value("mt_vitale"), dpg.get_value("mt_due_p"), dpg.get_value("mt_custom"), lunghezza=dpg.get_value("mt_lunghezza"))
                # Rimuove un punto alternativo dalla task
                self.task_mgr.rimuovi_alternativo(id_t, u)
                self._apri_popup_modifica_task(task=self.task_mgr.get_by_id(id_t))

            with dpg.group(horizontal=True):
                with dpg.child_window(width=210, height=110):
                    fasi = t.get('fasi', [])
                    dpg.add_text(f"Fasi ({len(fasi)}):", color=Colors.TEXT_DIM)
                    for i, f in enumerate(fasi):
                        with dpg.group(horizontal=True):
                            dpg.add_button(label="X", user_data=i, callback=delete_fase)
                            dpg.add_text(f"[{i}] {f['nome'][:12]}..")
                with dpg.child_window(width=210, height=110):
                    alternativi = t.get('alternativi', [])
                    dpg.add_text(f"Alternativi ({len(alternativi)}):", color=Colors.TEXT_DIM)
                    for i, fr in enumerate(alternativi):
                        with dpg.group(horizontal=True):
                            dpg.add_button(label="X", user_data=i, callback=delete_alternativo)
                            dpg.add_text(f"[{i}] ({fr['x']:.1f}, {fr['y']:.1f})")

            # ========== SEZIONE 3: EREDITARIETA' AZIONI (padre/figlia) ==========
            dpg.add_spacer(height=8)
            dpg.add_text("AZIONI E EREDITARIETA'", color=Colors.ACCENT)
            dpg.add_separator()

            azioni_proprie      = len(t.get('azioni', []))
            azioni_eff, src_id  = self.task_mgr.get_azioni_effettive(id_t)

            # Riga riepilogo origine azioni
            if src_id is not None and src_id != id_t:
                p_src = self.task_mgr.get_by_id(src_id)
                p_src_nome = p_src['nome'] if p_src else '?'
                dpg.add_text(
                    f"Azioni proprie: {azioni_proprie}  ->  in uso: {len(azioni_eff)} EREDITATE "
                    f"dal padre [{src_id}] {p_src_nome}",
                    color=(100, 220, 255), wrap=440)
            elif azioni_proprie > 0:
                dpg.add_text(
                    f"Azioni proprie: {azioni_proprie}  ->  in uso: {azioni_proprie} (nessuna ereditarieta')",
                    color=Colors.TEXT_DIM, wrap=440)
            else:
                dpg.add_text(
                    "Nessuna azione (ne' proprie ne' ereditate). "
                    "Registra azioni con l'editor o scegli un padre qui sotto.",
                    color=(255, 180, 100), wrap=440)

            # Eventuali figli di questa task (info utile: non saranno scelti come padre)
            figli = self.task_mgr.get_figli(id_t)
            if figli:
                nomi_figli = ", ".join(f"[{f['id']}] {f['nome']}" for f in figli[:3])
                suffix = "" if len(figli) <= 3 else f" (+{len(figli)-3})"
                dpg.add_text(f"Questa task e' PADRE di {len(figli)} figli: {nomi_figli}{suffix}",
                             color=Colors.TEXT_DIM, wrap=440)

            dpg.add_spacer(height=4)
            dpg.add_text("Scegli task padre (se vuota, le azioni locali hanno priorita'):",
                         color=Colors.TEXT_DIM, wrap=440)

            # Costruzione candidati (vedi logica sopra)
            candidati = ["- (nessuno)"]
            for altro in self.task_mgr.task_list:
                if altro['id'] == id_t:
                    continue
                if altro.get('id_padre') is not None:
                    continue
                n_az   = len(altro.get('azioni', []))
                zona_a = altro.get('nome_zona') or "-"
                candidati.append(f"[{altro['id']}] {altro['nome']} - A:{n_az} ({zona_a})")

            default_parent = "- (nessuno)"
            cur_parent = t.get('id_padre')
            if cur_parent is not None:
                p = self.task_mgr.get_by_id(cur_parent)
                if p is not None:
                    n_az   = len(p.get('azioni', []))
                    zona_a = p.get('nome_zona') or "-"
                    default_parent = f"[{p['id']}] {p['nome']} - A:{n_az} ({zona_a})"
            dpg.add_combo(items=candidati, tag="mt_parent",
                          default_value=default_parent, width=-1)

            dpg.add_spacer(height=4)
            dpg.add_button(label="APRI EDITOR AZIONI  (click / drag / zone / tempi)",
                           width=-1, height=36, callback=do_apri_editor)

            # ========== AZIONI FINALI ==========
            dpg.add_spacer(height=10)
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="Salva", width=220, height=32, callback=do_salva)
                dpg.add_button(label="Annulla", width=220, height=32,
                               # Rimuove l'elemento DPG (cleanup)
                               callback=lambda *a: dpg.delete_item(tag) if dpg.does_item_exist(tag) else None)
