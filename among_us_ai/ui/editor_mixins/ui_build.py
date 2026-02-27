"""
Costruzione UI dell'editor: pannello, canvas, slider tempi.

Mixin di TaskActionEditor.
"""

from ._imports import *


class EditorUIMixin:
    """Mixin con i metodi di editor u i di GPSVisualizerPro."""
    def _build_ui(self, task):
        """Costruisce l'interfaccia DPG dell'editor."""
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist(self.TAG_WIN):
            # Rimuove l'elemento DPG (cleanup)
            dpg.delete_item(self.TAG_WIN)

        # Verifica se l'elemento DPG e' gia' stato creato
        if not dpg.does_item_exist(self.TAG_TEX_REG):
            with dpg.texture_registry(show=False, tag=self.TAG_TEX_REG):
                pass

        titolo = f"Editor Azioni - [{task['id']}] {task['nome']}"
        with dpg.window(label=titolo, tag=self.TAG_WIN,
                        width=1180, height=740,
                        on_close=lambda *a: self.chiudi()):
            # Colore unificato per gli header di sezione del pannello sinistro
            col_section = (255, 200, 0)
            with dpg.group(horizontal=True):
                # ----- Colonna sinistra: controlli -----
                # `horizontal_scrollbar=True`: la colonna ha larghezza
                # fissa 420px ma alcuni controlli (input lunghi, label
                # con testi tradotti, ecc.) possono superarla. Lo
                # scrollbar permette di leggere tutto senza tagliare.
                with dpg.child_window(width=420, height=-1,
                                      horizontal_scrollbar=True):

                    # ========== 1. FINESTRA BERSAGLIO ==========
                    dpg.add_text("1. FINESTRA BERSAGLIO", color=col_section)
                    dpg.add_separator()
                    dpg.add_input_text(label="Nome",
                                       default_value="Among Us",
                                       tag=self.TAG_IN_WIN_NAME)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="AVVIA Preview",
                                       tag=self.TAG_BTN_LIVE,
                                       callback=self._toggle_live,
                                       width=125, height=30)
                        dpg.add_button(label="Cattura Frame",
                                       callback=lambda *a: self.aggiorna_frame(True),
                                       width=125, height=30)
                        dpg.add_button(label="Freeze [F]",
                                       tag="tae_btn_freeze",
                                       callback=self._toggle_freeze,
                                       width=125, height=30)
                    dpg.add_text("Preview: LIVE", tag="tae_label_freeze",
                                 color=(150, 200, 255))

                    # ========== 2. TEMPI DEFAULT (NUOVE AZIONI) ==========
                    dpg.add_spacer(height=6)
                    dpg.add_text("2. TEMPI DEFAULT PER NUOVE AZIONI",
                                 color=col_section)
                    dpg.add_separator()
                    dpg.add_text("Questi valori vengono applicati alle nuove azioni "
                                 "che aggiungi sotto. Per modificare i tempi di "
                                 "un'azione GIA' presente, usa la sezione 4.",
                                 color=(150, 150, 150), wrap=380)
                    with dpg.group(horizontal=True):
                        dpg.add_input_float(label="Durata (s)",
                                            tag=self.TAG_IN_DUR,
                                            default_value=0.2, step=0.05,
                                            format="%.2f", width=120,
                                            min_value=0.0, min_clamped=True)
                        dpg.add_input_float(label="Pausa (s)",
                                            tag=self.TAG_IN_PAUSE,
                                            default_value=0.5, step=0.05,
                                            format="%.2f", width=120,
                                            min_value=0.0, min_clamped=True)
                    dpg.add_input_float(
                        label="Mantieni @ B (s)  [solo DRAG+TIENI]",
                        tag=self.TAG_IN_HOLD,
                        default_value=1.0, step=0.1,
                        format="%.2f", width=220,
                        min_value=0.0, min_clamped=True)

                    # ========== 3. AGGIUNGI AZIONE ==========
                    dpg.add_spacer(height=6)
                    dpg.add_text("3. AGGIUNGI AZIONE", color=col_section)
                    dpg.add_separator()
                    dpg.add_text("In attesa...", tag=self.TAG_IST,
                                 color=(150, 150, 150), wrap=380)

                    dpg.add_text("Punto singolo / drag:", color=(180, 255, 180))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ CLICK",
                                       callback=lambda *a: self._avvia(self.WAIT_CLICK,
                                           "CLICK sulla preview per piazzare il punto.",
                                           (0, 255, 0)),
                                       width=125, height=35)
                        dpg.add_button(label="+ DRAG",
                                       callback=lambda *a: self._avvia(self.WAIT_DRAG_START,
                                           "PARTENZA drag: CLICK sulla preview.",
                                           (255, 200, 0)),
                                       width=125, height=35)
                        dpg.add_button(label="+ MULTI-DRAG",
                                       callback=self._avvia_multi,
                                       width=125, height=35)

                    dpg.add_text("Drag con pressione finale al punto B:",
                                 color=(255, 140, 180))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ DRAG + TIENI",
                                       callback=self._avvia_drag_hold,
                                       width=190, height=35)
                        dpg.add_text(
                            "Trascina A->B,\nmantieni premuto su B\nper 'Mantieni (s)'",
                            color=(180, 180, 180))

                    dpg.add_text("Zone (click casuale nell'area):",
                                 color=(200, 180, 255))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ CLICK RETT",
                                       callback=self._avvia_rect_click,
                                       width=125, height=35)
                        dpg.add_button(label="+ CLICK POLY",
                                       callback=lambda *a: self._avvia_poly_click(),
                                       width=125, height=35)
                        dpg.add_button(label="+ DRAG A->B",
                                       callback=self._avvia_drag_zone,
                                       width=125, height=35)
                                       
                    dpg.add_text("Azioni speciali collegate alla vista:",
                                 color=(255, 255, 100))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ FIX WIRING",
                                       callback=self._avvia_wiring,
                                       width=125, height=35)
                        dpg.add_text("Risove i cavi usando i\ncolori dello schermo.",
                                     color=(180, 180, 180))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ SYNC CLICK",
                                       callback=self._avvia_sync_click,
                                       width=125, height=35)
                        dpg.add_text("Attende colore (non\nnero) e clicca bottone.",
                                     color=(180, 180, 180))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ CLICK ANOMALIA",
                                       callback=self._avvia_anomaly_click,
                                       width=125, height=35)
                        dpg.add_text("Seleziona >=3 punti, clicca\nquello col colore diverso.",
                                     color=(180, 180, 180))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ DRAG YOLO",
                                       callback=self._avvia_yolo_drag,
                                       width=125, height=35)
                        dpg.add_text("Usa YOLOv8 per rilevare\nl'oggetto e trascinarlo.",
                                     color=(180, 180, 180))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ COOLDOWN / FASE",
                                       callback=self._avvia_cooldown,
                                       width=125, height=35)
                        dpg.add_text("Divide in FASI e mette il\nbot in attesa per X secondi.",
                                     color=(180, 180, 180))

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ CLICK YOLO",
                                       callback=self._avvia_yolo_click,
                                       width=125, height=35)
                        dpg.add_text("Usa YOLOv8 per rilevare\nl'oggetto e cliccarlo.",
                                     color=(180, 180, 180))

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ CLICK ALL YOLO",
                                       callback=self._avvia_yolo_click_all,
                                       width=125, height=35)
                        dpg.add_text("Clicca TUTTI gli oggetti\nrilevati finche' non finiscono.",
                                     color=(180, 180, 180))

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ DRAG ALL YOLO",
                                       callback=self._avvia_yolo_drag_all,
                                       width=125, height=35)
                        dpg.add_text("Trascina TUTTI gli oggetti\nrilevati finche' non finiscono.",
                                     color=(180, 180, 180))

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ DRAG SEQ YOLO",
                                       callback=self._avvia_yolo_drag_seq,
                                       width=125, height=35)
                        dpg.add_text("Trascina l'oggetto unico\nsugli altri in sequenza.",
                                     color=(180, 180, 180))

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ CLICK UNTIL",
                                       callback=self._avvia_click_until,
                                       width=125, height=35)
                        dpg.add_text("Clicca un bottone finche' il\ncheck non e' bianco.",
                                     color=(180, 180, 180))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ SIMON SAYS",
                                       callback=self._avvia_simon_says,
                                       width=125, height=35)
                        dpg.add_text("Memo reattore: mappa i punti\nluminosi e il tastierino.",
                                     color=(180, 180, 180))

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ NUMBER MATCH",
                                       callback=self._avvia_num_match,
                                       width=125, height=35)
                        dpg.add_text("Trascina i rect dei numeri in\nordine (es: 1 a 10). Poi CHIUDI.", color=(180, 180, 180))

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ OCR KEYPAD",
                                       callback=self._avvia_ocr_keypad,
                                       width=125, height=35)
                        dpg.add_text("Legge numeri (EasyOCR)\ne preme tastierino 0-9.", color=(180, 180, 180))

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="CHIUDI PUNTI (Invio)",
                                       callback=self._chiudi_sequenza,
                                       width=190, height=28)
                        dpg.add_button(label="ANNULLA (Esc)",
                                       callback=self._annulla,
                                       width=190, height=28)

                    # ========== 4. AZIONE SELEZIONATA ==========
                    dpg.add_spacer(height=6)
                    dpg.add_text("4. AZIONE SELEZIONATA", color=col_section)
                    dpg.add_separator()
                    dpg.add_text("Clicca su un punto/poligono nella preview per "
                                 "selezionare l'azione relativa.",
                                 color=(150, 150, 150), wrap=380)
                    dpg.add_text("- nessuna azione selezionata -",
                                 tag="tae_sel_info", color=(150, 150, 150), wrap=380)

                    # --- Modifica tempi dell'azione selezionata (in-place) ---
                    # Prima si poteva cambiare la durata/attesa solo cancellando
                    # e ridisegnando l'azione. Ora c'e' una coppia di input
                    # dedicata che scrive direttamente in self.azioni[sel_idx].
                    with dpg.group(tag=self.TAG_EDIT_GROUP, show=False):
                        dpg.add_text("Modifica tempi (senza ridisegnare la geometria):",
                                     color=(150, 200, 255))
                        with dpg.group(horizontal=True):
                            dpg.add_text("Durata:")
                            dpg.add_input_float(tag=self.TAG_EDIT_DUR,
                                                default_value=0.2, step=0.05,
                                                format="%.2f", width=90,
                                                min_value=0.0, min_clamped=True)
                            dpg.add_text("s    Pausa:")
                            dpg.add_input_float(tag=self.TAG_EDIT_PAUSE,
                                                default_value=0.5, step=0.05,
                                                format="%.2f", width=90,
                                                min_value=0.0, min_clamped=True)
                            dpg.add_text("s")
                        dpg.add_input_float(
                                            tag=self.TAG_EDIT_HOLD,
                                            label="Mantieni @ B (s)  [solo DRAG+TIENI]",
                                            default_value=1.0, step=0.1,
                                            format="%.2f", width=90,
                                            min_value=0.0, min_clamped=True)
                        dpg.add_button(label="Applica tempi all'azione selezionata",
                                       callback=self._applica_tempi_selezione,
                                       width=-1, height=26)

                    dpg.add_spacer(height=2)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Ridisegna geometria",
                                       callback=self._modifica_selezione,
                                       width=190, height=28)
                        dpg.add_button(label="Elimina (Canc)",
                                       callback=self._elimina_selezione,
                                       width=190, height=28)

                    # ========== 5. LISTA AZIONI / TEST / SALVA ==========
                    dpg.add_spacer(height=6)
                    dpg.add_text("5. LISTA AZIONI REGISTRATE", color=col_section)
                    dpg.add_separator()
                    # `horizontal_scrollbar=True`: permette di scorrere lateralmente
                    # quando la descrizione di un'azione e' troppo lunga (es.
                    # poligoni con molti punti, parametri verbose, ecc.) cosi'
                    # tutto il testo resta leggibile senza troncamento.
                    with dpg.child_window(tag=self.TAG_LIST, height=180,
                                          horizontal_scrollbar=True):
                        pass

                    dpg.add_spacer(height=4)
                    dpg.add_button(label="TEST SEQUENZA (esegue tutte le azioni)",
                                   callback=self._avvia_test,
                                   width=-1, height=36)
                    dpg.add_spacer(height=4)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="SALVA e CHIUDI",
                                       callback=self._salva_e_chiudi,
                                       width=200, height=38)
                        dpg.add_button(label="Annulla",
                                       callback=lambda *a: self.chiudi(),
                                       width=180, height=38)

                # ----- Colonna destra: preview -----
                with dpg.child_window(tag=self.TAG_PREVIEW_CONT, width=-1, height=-1, border=False):
                    with dpg.drawlist(width=self.preview_w, height=self.preview_h,
                                      tag=self.TAG_CANVAS):
                        pass

        # Verifica se l'elemento DPG e' gia' stato creato
        if not dpg.does_item_exist("tae_canvas_handler"):
            with dpg.item_handler_registry(tag="tae_canvas_handler"):
                dpg.add_item_clicked_handler(button=0, callback=self._canvas_mouse_down)
        dpg.bind_item_handler_registry(self.TAG_CANVAS, "tae_canvas_handler")

        # Verifica se l'elemento DPG e' gia' stato creato
        if not dpg.does_item_exist("tae_key_handler"):
            with dpg.handler_registry(tag="tae_key_handler"):
                dpg.add_key_press_handler(key=dpg.mvKey_Delete, callback=self._on_key_delete)
                dpg.add_key_press_handler(key=dpg.mvKey_F, callback=self._on_key_freeze)

        # Handler per ridimensionamento
        if not dpg.does_item_exist("tae_win_resize_handler"):
            with dpg.item_handler_registry(tag="tae_win_resize_handler"):
                dpg.add_item_resize_handler(callback=self._on_resize)
        dpg.bind_item_handler_registry(self.TAG_WIN, "tae_win_resize_handler")

    def _ricalcola_dimensioni_preview(self):
        """Ricalcola dimensioni preview."""
        # Verifica se l'elemento DPG e' gia' stato creato
        if not dpg.does_item_exist(self.TAG_PREVIEW_CONT) or self.texture_width <= 0:
            return False
            
        avail_w, avail_h = dpg.get_item_rect_size(self.TAG_PREVIEW_CONT)
        if avail_w <= 0: avail_w = MAX_PREVIEW_W
        if avail_h <= 0: avail_h = MAX_PREVIEW_H
        
        aspect = self.texture_width / self.texture_height
        temp_w = avail_w
        temp_h = int(temp_w / aspect)
        
        if temp_h > avail_h:
            temp_h = avail_h
            temp_w = int(temp_h * aspect)

        if temp_w != self.preview_w or temp_h != self.preview_h:
            self.preview_w, self.preview_h = int(temp_w), int(temp_h)
            dpg.set_item_width(self.TAG_CANVAS, self.preview_w)
            dpg.set_item_height(self.TAG_CANVAS, self.preview_h)
            return True
        return False
