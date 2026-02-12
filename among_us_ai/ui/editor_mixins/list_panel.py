"""
Pannello laterale con la lista delle azioni: selezione, spostamento, modifica.

Mixin di TaskActionEditor.
"""

from ._imports import *


class EditorListPanelMixin:
    """Mixin con i metodi di editor list panel di GPSVisualizerPro."""
    def aggiorna_lista(self):
        """Aggiorna la listbox delle azioni nel pannello laterale dell'editor."""
        # Verifica se l'elemento DPG e' gia' stato creato
        if not dpg.does_item_exist(self.TAG_LIST):
            return
        # Rimuove l'elemento DPG (cleanup)
        dpg.delete_item(self.TAG_LIST, children_only=True)
        for i, a in enumerate(self.azioni):
            sel = (i == self.sel_idx)
            col_testo = (255, 255, 0) if sel else (255, 255, 255)
            prefix    = "> " if sel else "  "
            with dpg.group(horizontal=True, parent=self.TAG_LIST):
                dpg.add_text(f"{prefix}{i+1}. {self._descr_azione(a)}",
                             color=col_testo)
                dpg.add_button(label="^", user_data=i, callback=self._sposta_su, width=22)
                dpg.add_button(label="v", user_data=i, callback=self._sposta_giu, width=22)
                dpg.add_button(label="X", user_data=i, callback=self._elimina_azione, width=22)
                _ts = (f"D:{a.get('durata',0):.2f}s"
                       + (f" H:{a.get('hold',0):.2f}s"
                          if a.get("tipo") == "drag_hold" else "")
                       + f" P:{a.get('attesa',0):.2f}s")
                dpg.add_text(_ts, color=(100, 200, 255))

    def _sposta_su(self, sender, app_data, user_data):
        """Sposta su."""
        i = user_data
        if i > 0:
            self.azioni[i], self.azioni[i-1] = self.azioni[i-1], self.azioni[i]
            if self.sel_idx == i:
                self.sel_idx = i - 1
            elif self.sel_idx == i - 1:
                self.sel_idx = i
            self.aggiorna_lista(); self.aggiorna_preview()
            self._aggiorna_pannello_selezione()

    def _sposta_giu(self, sender, app_data, user_data):
        """Sposta giu."""
        i = user_data
        if i < len(self.azioni) - 1:
            self.azioni[i], self.azioni[i+1] = self.azioni[i+1], self.azioni[i]
            if self.sel_idx == i:
                self.sel_idx = i + 1
            elif self.sel_idx == i + 1:
                self.sel_idx = i
            self.aggiorna_lista(); self.aggiorna_preview()
            self._aggiorna_pannello_selezione()

    def _elimina_azione(self, sender, app_data, user_data):
        """Elimina azione."""
        i = user_data
        if 0 <= i < len(self.azioni):
            self.azioni.pop(i)
            if self.sel_idx == i:
                self.sel_idx = -1
            elif self.sel_idx > i:
                self.sel_idx -= 1
            self.aggiorna_lista(); self.aggiorna_preview()
            self._aggiorna_pannello_selezione()

    def _aggiorna_pannello_selezione(self):
        """Aggiorna pannello selezione."""
        # Verifica se l'elemento DPG e' gia' stato creato
        if not dpg.does_item_exist("tae_sel_info"):
            return
        if self.sel_idx < 0 or self.sel_idx >= len(self.azioni):
            # Aggiorna il valore di un widget DPG
            dpg.set_value("tae_sel_info", "- nessuna azione selezionata -")
            # Cambia le configurazioni di un widget gia' creato
            dpg.configure_item("tae_sel_info", color=(150, 150, 150))
            # Nascondi il gruppo di modifica tempi: non c'e' nulla su cui agire
            if dpg.does_item_exist(self.TAG_EDIT_GROUP):
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item(self.TAG_EDIT_GROUP, show=False)
        else:
            a = self.azioni[self.sel_idx]
            # Aggiorna il valore di un widget DPG
            dpg.set_value("tae_sel_info",
                          f"#{self.sel_idx + 1}: {self._descr_azione(a)}")
            # Cambia le configurazioni di un widget gia' creato
            dpg.configure_item("tae_sel_info", color=(255, 200, 0))
            # Pre-compila i campi tempi con i valori correnti dell'azione
            # selezionata, cosi' l'utente vede subito cosa sta modificando.
            if dpg.does_item_exist(self.TAG_EDIT_DUR):
                # Aggiorna il valore di un widget DPG
                dpg.set_value(self.TAG_EDIT_DUR, float(a.get("durata", 0.0)))
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist(self.TAG_EDIT_PAUSE):
                # Aggiorna il valore di un widget DPG
                dpg.set_value(self.TAG_EDIT_PAUSE, float(a.get("attesa", 0.0)))
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist(self.TAG_EDIT_HOLD):
                # Aggiorna il valore di un widget DPG
                dpg.set_value(self.TAG_EDIT_HOLD, float(a.get("hold", 0.0)))
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist(self.TAG_EDIT_GROUP):
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item(self.TAG_EDIT_GROUP, show=True)

    def _applica_tempi_selezione(self, *_):
        """
        Aggiorna durata e attesa dell'azione selezionata senza toccarne la
        geometria. Scritto come operazione in-place sulla lista azioni:
        nessun pop/re-draw, nessun cambio di sel_idx.
        """
        if self.sel_idx < 0 or self.sel_idx >= len(self.azioni):
            self._imposta_istruzioni("Seleziona prima un'azione.", (255, 150, 100))
            return
        dur_nuova   = max(0.0, float(dpg.get_value(self.TAG_EDIT_DUR)))
        pausa_nuova = max(0.0, float(dpg.get_value(self.TAG_EDIT_PAUSE)))
        self.azioni[self.sel_idx]["durata"] = dur_nuova
        self.azioni[self.sel_idx]["attesa"] = pausa_nuova
        _az = self.azioni[self.sel_idx]
        # Verifica se l'elemento DPG e' gia' stato creato
        if _az.get("tipo") == "drag_hold" and dpg.does_item_exist(self.TAG_EDIT_HOLD):
            _az["hold"] = max(0.0, float(dpg.get_value(self.TAG_EDIT_HOLD)))
        _h = (f", H={_az['hold']:.2f}s" if _az.get("tipo") == "drag_hold" else "")
        self._imposta_istruzioni(
            f"#{self.sel_idx + 1}: tempi aggiornati (D={dur_nuova:.2f}s{_h}, P={pausa_nuova:.2f}s)",
            (150, 255, 150))
        # La lista mostra i tempi per ogni azione: basta ridisegnarla.
        self.aggiorna_lista()

    def _elimina_selezione(self, *_):
        """Elimina selezione."""
        if self.sel_idx < 0 or self.sel_idx >= len(self.azioni):
            self._imposta_istruzioni("Nessuna azione selezionata.", (255, 150, 100))
            return
        rimossa = self.azioni.pop(self.sel_idx)
        self._imposta_istruzioni(
            f"Eliminata: {self._descr_azione(rimossa)}", (255, 150, 100))
        self.sel_idx = -1
        self._aggiorna_pannello_selezione()
        self.aggiorna_lista()
        self.aggiorna_preview()

    def _modifica_selezione(self, *_):
        """Modifica selezione."""
        if self.sel_idx < 0 or self.sel_idx >= len(self.azioni):
            self._imposta_istruzioni("Nessuna azione selezionata.", (255, 150, 100))
            return
        a = self.azioni.pop(self.sel_idx)
        self.sel_idx = -1
        
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist(self.TAG_IN_DUR):
            # Aggiorna il valore di un widget DPG
            dpg.set_value(self.TAG_IN_DUR, a.get("durata", 0.2))
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist(self.TAG_IN_PAUSE):
            # Aggiorna il valore di un widget DPG
            dpg.set_value(self.TAG_IN_PAUSE, a.get("attesa", 0.5))
            
        tipo = a.get("tipo")
        if tipo == "click":
            self._avvia(self.WAIT_CLICK,
                        "MODIFICA: CLICK sulla preview per nuovo punto.", (0, 255, 0))
        elif tipo == "drag":
            self._avvia(self.WAIT_DRAG_START,
                        "MODIFICA: CLICK sulla preview per PARTENZA drag.", (255, 200, 0))
        elif tipo == "click_rect":
            self._avvia_rect_click()
            self._imposta_istruzioni(
                "MODIFICA: trascina sulla PREVIEW per il nuovo rettangolo.",
                (180, 255, 180))
        elif tipo == "click_poly":
            self._avvia_poly_click()
            self._imposta_istruzioni(
                "MODIFICA: CLICK per nuovi vertici, poi CHIUDI PUNTI.",
                (200, 180, 255))
        elif tipo == "drag_multi":
            self._avvia_multi()
            self._imposta_istruzioni(
                "MODIFICA: CLICK per nuovi punti (>=2), poi CHIUDI PUNTI.",
                (255, 180, 100))
        elif tipo == "drag_hold":
            self._avvia_drag_hold()
            self._imposta_istruzioni(
                "MODIFICA: CLICK per nuova PARTENZA, poi CLICK per nuovo ARRIVO.",
                (255, 140, 180))
        elif tipo == "drag_zone":
            self._avvia_drag_zone()
            self._imposta_istruzioni(
                "MODIFICA: ridisegna ZONA A, poi ZONA B.", (255, 150, 200))
        elif tipo == "wiring":
            self._avvia_wiring()
            self._imposta_istruzioni("MODIFICA: Ridisegna intero Fix Wiring.", (200, 255, 100))
        elif tipo == "sync_click":
            self._avvia_sync_click()
            self._imposta_istruzioni("MODIFICA: Ridisegna intero Sync Click.", (200, 255, 100))
        elif tipo == "yolo_drag":
            self._tmp_yolo_model = a.get("yolo_model")
            self.stato = self.WAIT_YOLO_POLY
            self.buffer_punti = []
            self.buffer_zone_a = []
            self._imposta_istruzioni(f"MODIFICA YOLO '{self._tmp_yolo_model}': Ridisegna ZONA DI RICERCA, poi CHIUDI PUNTI.", (255, 100, 255))
        elif tipo == "yolo_drag_all":
            self._tmp_yolo_model = a.get("yolo_model")
            self.stato = self.WAIT_YOLO_ALL_POLY
            self.buffer_punti = []
            self.buffer_zone_a = []
            self._imposta_istruzioni(f"MODIFICA ALL YOLO '{self._tmp_yolo_model}': Ridisegna ZONA DI RICERCA, poi CHIUDI PUNTI.", (255, 150, 50))
        elif tipo == "yolo_click":
            self._tmp_yolo_model = a.get("yolo_model")
            self.stato = self.WAIT_YOLO_CLICK_POLY
            self.buffer_punti = []
            self.buffer_zone_a = []
            self._imposta_istruzioni(f"MODIFICA YOLO CLICK '{self._tmp_yolo_model}': Ridisegna ZONA DI RICERCA, poi CHIUDI PUNTI.", (100, 255, 100))
        elif tipo == "yolo_click_all":
            self._tmp_yolo_model = a.get("yolo_model")
            self.stato = self.WAIT_YOLO_CLICK_ALL_POLY
            self.buffer_punti = []
            self.buffer_zone_a = []
            self._imposta_istruzioni(f"MODIFICA ALL YOLO CLICK '{self._tmp_yolo_model}': Ridisegna ZONA DI RICERCA, poi CHIUDI PUNTI.", (100, 255, 150))
        elif tipo == "yolo_drag_seq":
            self._tmp_yolo_model = a.get("yolo_model")
            self.stato = self.WAIT_YOLO_SEQ_POLY
            self.buffer_punti = []
            self.buffer_zone_a = []
            self._imposta_istruzioni(f"MODIFICA SEQ YOLO '{self._tmp_yolo_model}': Ridisegna ZONA DI RICERCA, poi CHIUDI PUNTI.", (255, 120, 200))
        elif tipo == "click_until":
            self._avvia_click_until()
            self._imposta_istruzioni("MODIFICA: Ridisegna intero Click Until.", (200, 255, 255))
        elif tipo == "click_anomaly":
            self._avvia_anomaly_click()
            self._imposta_istruzioni("MODIFICA: Ridisegna intera Anomalia (>=3 coppie).", (255, 100, 200))
        elif tipo == "number_match":
            self._avvia_num_match()
            self._imposta_istruzioni("MODIFICA: Ridisegna intera griglia Number Match.", (100, 255, 255))
        elif tipo == "ocr_keypad":
            self.stato = self.WAIT_OCR_POLY
            self.buffer_punti = []
            self.buffer_keypad = []
            self._imposta_istruzioni("MODIFICA: Ridisegna ZONA SCHERMO (poly), poi i 10 tasti.", (100, 255, 200))
        self._aggiorna_pannello_selezione()
        self.aggiorna_lista()
        self.aggiorna_preview()
