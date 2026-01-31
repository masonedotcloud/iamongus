"""
Fine sequenza, descrizione delle azioni, dialoghi e reset.

Mixin di TaskActionEditor.
"""

from ._imports import *


class EditorSequenceMixin:
    """Mixin con i metodi di editor sequence di GPSVisualizerPro."""
    def _show_text_input(self, title, default_text, callback):
        """Mostra un popup modale per inserimento testo nell'editor."""
        tag = "tae_text_input_popup"
        # Se il widget esiste gia', lo rimuovo prima di ricrearlo
        if dpg.does_item_exist(tag):
            # Rimuove l'elemento DPG (cleanup)
            dpg.delete_item(tag)

        def do_ok(*_):
            """Callback del pulsante OK."""
            # Verifica se l'elemento DPG e' gia' stato creato
            if not dpg.does_item_exist(f"{tag}_input"):
                callback(None)
                return
            value = dpg.get_value(f"{tag}_input")
            # Se il widget esiste gia', lo rimuovo prima di ricrearlo
            if dpg.does_item_exist(tag):
                # Rimuove l'elemento DPG (cleanup)
                dpg.delete_item(tag)
            if value and value.strip():
                callback(value.strip())
            else:
                callback(None)

        def do_cancel(*_):
            """Callback del pulsante Annulla."""
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist(tag):
                # Rimuove l'elemento DPG (cleanup)
                dpg.delete_item(tag)
            callback(None)

        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        with dpg.window(label=title, tag=tag, modal=True, no_resize=True,
                        no_collapse=True, width=340, height=135,
                        pos=(max(0, vp_w // 2 - 170), max(0, vp_h // 2 - 68))):
            dpg.add_input_text(tag=f"{tag}_input", default_value=default_text or "", width=-1, on_enter=True, callback=do_ok)
            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True):
                dpg.add_button(label="OK", width=155, callback=do_ok)
                dpg.add_button(label="Annulla", width=155, callback=do_cancel)
        try:
            dpg.focus_item(f"{tag}_input")
        except Exception:
            pass

    def _chiudi_sequenza(self, *_):
        """Chiude sequenza."""
        durata = dpg.get_value(self.TAG_IN_DUR)
        attesa = dpg.get_value(self.TAG_IN_PAUSE)

        if self.stato == self.WAIT_MULTI:
            if len(self.buffer_punti) >= 2:
                self.azioni.append({
                    "tipo":   "drag_multi",
                    "punti":  [list(p) for p in self.buffer_punti],
                    "durata": durata,
                    "attesa": attesa,
                })
                self._imposta_istruzioni(
                    f"Multi-drag aggiunto ({len(self.buffer_punti)} punti).")
            else:
                self._imposta_istruzioni("Servono almeno 2 punti.", (255, 100, 100))
            self._reset_stato()

        elif self.stato == self.WAIT_POLY:
            if len(self.buffer_punti) >= 3:
                self.azioni.append({
                    "tipo":   "click_poly",
                    "poly":   [list(p) for p in self.buffer_punti],
                    "durata": durata,
                    "attesa": attesa,
                })
                self._imposta_istruzioni(
                    f"Click poligono aggiunto ({len(self.buffer_punti)} vertici).")
            else:
                self._imposta_istruzioni("Servono almeno 3 vertici.", (255, 100, 100))
            self._reset_stato()

        elif self.stato == self.WAIT_POLY_ZONE_A:
            if len(self.buffer_punti) >= 3:
                self.buffer_zone_a = list(self.buffer_punti)
                self.buffer_punti = []
                self.stato = self.WAIT_POLY_ZONE_B
                self._imposta_istruzioni(
                    f"ZONA A ok ({len(self.buffer_zone_a)} vertici). Ora disegna ZONA B.",
                    (255, 200, 100))
            else:
                self._imposta_istruzioni("Zona A: servono almeno 3 vertici.",
                                         (255, 100, 100))

        elif self.stato == self.WAIT_POLY_ZONE_B:
            if len(self.buffer_punti) >= 3:
                self.azioni.append({
                    "tipo":    "drag_zone",
                    "zone_a":  [list(p) for p in self.buffer_zone_a],
                    "zone_b":  [list(p) for p in self.buffer_punti],
                    "durata":  durata,
                    "attesa":  attesa,
                })
                self._imposta_istruzioni("Drag zona->zona aggiunto.")
            else:
                self._imposta_istruzioni("Zona B: servono almeno 3 vertici.",
                                         (255, 100, 100))
            self._reset_stato()
        elif self.stato in (self.WAIT_SYNC_CHECK, self.WAIT_SYNC_BTN):
            if len(self.buffer_sync) > 0:
                self.azioni.append({
                    "tipo": "sync_click",
                    "punti": self.buffer_sync,
                    "durata": durata,
                    "attesa": attesa
                })
                self._imposta_istruzioni(f"Sync Click aggiunto ({len(self.buffer_sync)} coppie).")
            else:
                self._imposta_istruzioni("Nessuna coppia aggiunta.", (255, 100, 100))
            self._reset_stato()

        elif self.stato == self.WAIT_YOLO_POLY:
            if len(self.buffer_punti) >= 3:
                self.buffer_zone_a = list(self.buffer_punti)
                self.buffer_punti = []
                self.stato = self.WAIT_YOLO_DEST
                self._imposta_istruzioni(f"ROI registrata ({len(self.buffer_zone_a)} vertici). Ora clicca la DESTINAZIONE sulla preview.", (255, 200, 100))
            else:
                self._imposta_istruzioni("Servono almeno 3 vertici per la ROI.", (255, 100, 100))

        elif self.stato == self.WAIT_YOLO_ALL_POLY:
            if len(self.buffer_punti) >= 3:
                self.buffer_zone_a = list(self.buffer_punti)
                self.buffer_punti = []
                self.stato = self.WAIT_YOLO_ALL_DEST
                self._imposta_istruzioni(f"ROI registrata ({len(self.buffer_zone_a)} vertici). Ora clicca la DESTINAZIONE sulla preview.", (255, 180, 100))
            else:
                self._imposta_istruzioni("Servono almeno 3 vertici per la ROI.", (255, 100, 100))

        elif self.stato == self.WAIT_YOLO_CLICK_POLY:
            if len(self.buffer_punti) >= 3:
                self.azioni.append({
                    "tipo": "yolo_click",
                    "yolo_model": getattr(self, '_tmp_yolo_model', 'best.pt'),
                    "roi_poly": [list(p) for p in self.buffer_punti],
                    "durata": durata, "attesa": attesa
                })
                self._reset_stato()
                self._imposta_istruzioni(f"Click YOLO aggiunto.", (100, 255, 100))
            else:
                self._imposta_istruzioni("Servono almeno 3 vertici per la ROI.", (255, 100, 100))

        elif self.stato == self.WAIT_YOLO_CLICK_ALL_POLY:
            if len(self.buffer_punti) >= 3:
                self.azioni.append({
                    "tipo": "yolo_click_all",
                    "yolo_model": getattr(self, '_tmp_yolo_model', 'best.pt'),
                    "roi_poly": [list(p) for p in self.buffer_punti],
                    "durata": durata, "attesa": attesa
                })
                self._reset_stato()
                self._imposta_istruzioni(f"Click ALL YOLO aggiunto.", (100, 255, 100))
            else:
                self._imposta_istruzioni("Servono almeno 3 vertici per la ROI.", (255, 100, 100))

        elif self.stato == self.WAIT_YOLO_SEQ_POLY:
            if len(self.buffer_punti) >= 3:
                self.azioni.append({
                    "tipo": "yolo_drag_seq",
                    "yolo_model": getattr(self, '_tmp_yolo_model', 'best.pt'),
                    "roi_poly": [list(p) for p in self.buffer_punti],
                    "durata": durata, "attesa": attesa
                })
                self._reset_stato()
                self._imposta_istruzioni(f"Drag Sequenziale YOLO aggiunto.", (100, 255, 100))
            else:
                self._imposta_istruzioni("Servono almeno 3 vertici per la ROI.", (255, 100, 100))

        elif self.stato in (self.WAIT_CUC_CHK, self.WAIT_CUC_BTN):
            if len(self.buffer_cuc) > 0:
                self.azioni.append({
                    "tipo": "click_until",
                    "punti": self.buffer_cuc,
                    "durata": durata,
                    "attesa": attesa
                })
                self._imposta_istruzioni(f"Click Until aggiunto ({len(self.buffer_cuc)} coppie).")
            else:
                self._imposta_istruzioni("Nessuna coppia aggiunta.", (255, 100, 100))
            self._reset_stato()

        elif self.stato == self.WAIT_SIMON_DISPLAY:
            if len(self.buffer_simon_d) > 0:
                self.stato = self.WAIT_SIMON_KEYPAD
                self._imposta_istruzioni(f"Display ok ({len(self.buffer_simon_d)} luci). Ora clicca ESATTAMENTE {len(self.buffer_simon_d)} BOTTONI corrispondenti. Poi CHIUDI PUNTI.", (255, 100, 255))
            else:
                self._imposta_istruzioni("Servono punti per il display.", (255, 100, 100))
                
        elif self.stato == self.WAIT_SIMON_KEYPAD:
            if len(self.buffer_simon_k) == len(self.buffer_simon_d):
                self.azioni.append({"tipo": "simon_says", "display": [list(p) for p in self.buffer_simon_d], "keypad": [list(p) for p in self.buffer_simon_k], "durata": durata, "attesa": attesa})
                self._reset_stato()
                self._imposta_istruzioni("Simon Says registrato correttamente!", (100, 255, 100))
            else:
                self._imposta_istruzioni(f"Errore: hai cliccato {len(self.buffer_simon_k)} bottoni ma le luci sono {len(self.buffer_simon_d)}.", (255, 100, 100))

        elif self.stato in (self.WAIT_ANOMALY_CHK, self.WAIT_ANOMALY_BTN):
            if len(self.buffer_anomaly) >= 3:
                self.azioni.append({
                    "tipo": "click_anomaly",
                    "punti": self.buffer_anomaly,
                    "durata": durata, "attesa": attesa
                })
                self._reset_stato()
                self._imposta_istruzioni(f"Click Anomalia aggiunto ({len(self.buffer_anomaly)} coppie da valutare).", (100, 255, 100))
            else:
                self._imposta_istruzioni("Servono almeno 3 coppie per fare un confronto.", (255, 100, 100))
                
        elif self.stato == self.WAIT_NUM_MATCH_RECT:
            if len(self.buffer_num_match) > 0:
                self.azioni.append({
                    "tipo": "number_match",
                    "buttons": self.buffer_num_match,
                    "durata": durata,
                    "attesa": attesa
                })
                self._imposta_istruzioni(f"Number Match aggiunto ({len(self.buffer_num_match)} numeri in ordine).", (100, 255, 255))
            else:
                self._imposta_istruzioni("Nessun numero registrato.", (255, 100, 100))
            self._reset_stato()

        elif self.stato == self.WAIT_OCR_POLY:
            if len(self.buffer_punti) >= 3:
                self.buffer_zone_a = list(self.buffer_punti)
                self.buffer_punti = []
                self.stato = self.WAIT_OCR_KEYPAD
                self._imposta_istruzioni("Zona OK. Ora clicca 10 TASTI in ordine da 0 a 9.", (255, 100, 255))
            else:
                self._imposta_istruzioni("Servono almeno 3 vertici per la zona display.", (255, 100, 100))

        else:
            self._imposta_istruzioni("Nessuna sequenza attiva.", (150, 150, 150))

        self.aggiorna_lista()
        self.aggiorna_preview()

    def _annulla(self, *_):
        """Annulla l'operazione corrente."""
        self._reset_stato()
        self._imposta_istruzioni("Annullato.", (150, 150, 150))

    def _reset_stato(self):
        """Resetta stato."""
        self.stato = self.IDLE
        self.buffer_punti = []
        self.buffer_zone_a = []
        self.buffer_w_l = []
        self.buffer_w_r = []
        self.buffer_w_c = []
        self.buffer_sync = []
        self.buffer_cuc = []
        self.buffer_simon_d = []
        self.buffer_simon_k = []
        self.buffer_anomaly = []
        self.buffer_num_match = []
        self.buffer_keypad = []
        self.rect_drag_active = False
        self.rect_start = None
        self.rect_end = None

    def _descr_azione(self, a):
        """Descrive azione."""
        t = a.get("tipo")
        if t == "click":
            return f"Click @({a['rx']:.2f},{a['ry']:.2f})"
        if t == "click_rect":
            r = a.get("rect", [0, 0, 0, 0])
            return f"ClickRect [{r[0]:.2f},{r[1]:.2f}]->[{r[2]:.2f},{r[3]:.2f}]"
        if t == "click_poly":
            return f"ClickPoly ({len(a.get('poly', []))} vertici)"
        if t == "drag":
            return f"Drag ({a['start_rx']:.2f},{a['start_ry']:.2f})->({a['end_rx']:.2f},{a['end_ry']:.2f})"
        if t == "drag_multi":
            return f"MultiDrag ({len(a.get('punti', []))} punti)"
        if t == "drag_zone":
            return f"DragZona ({len(a.get('zone_a', []))}v -> {len(a.get('zone_b', []))}v)"
        if t == "drag_hold":
            return (f"DragTieni ({a['start_rx']:.2f},{a['start_ry']:.2f})"
                    f"->({a['end_rx']:.2f},{a['end_ry']:.2f})"
                    f" H:{a.get('hold', 0):.2f}s")
        if t == "wiring":
            return f"Fix Wiring (4 cavi + visore colore)"
        if t == "sync_click":
            return f"Sync Click ({len(a.get('punti', []))} coppie)"
        if t == "yolo_drag":
            return f"Drag YOLO '{a.get('yolo_model')}' ROI({len(a.get('roi_poly', []))}v)"
        if t == "yolo_drag_all":
            return f"Drag ALL YOLO '{a.get('yolo_model')}' ROI({len(a.get('roi_poly', []))}v)"
        if t == "yolo_click":
            return f"Click YOLO '{a.get('yolo_model')}' ROI({len(a.get('roi_poly', []))}v)"
        if t == "yolo_click_all":
            return f"Click ALL YOLO '{a.get('yolo_model')}' ROI({len(a.get('roi_poly', []))}v)"
        if t == "yolo_drag_seq":
            return f"Drag Seq YOLO '{a.get('yolo_model')}' ROI({len(a.get('roi_poly', []))}v)"
        if t == "click_until":
            return f"Click Until ({len(a.get('punti', []))} coppie)"
        if t == "simon_says":
            return f"Simon Says ({len(a.get('display', []))} associazioni)"
        if t == "click_anomaly":
            return f"Click Anomalia ({len(a.get('punti', []))} coppie)"
        if t == "number_match":
            return f"Number Match ({len(a.get('buttons', []))} numeri)"
        if t == "ocr_keypad":
            return f"OCR Keypad (ROI + 10 tasti)"
        if t == "cooldown":
            return f"Cooldown / Cambio Fase ({a.get('durata', 0)}s)"
        return str(t)

    def _toggle_live(self, *_):
        """Inverte lo stato di live."""
        self.is_live = not self.is_live
        dpg.set_item_label(self.TAG_BTN_LIVE,
                           "FERMA Live Preview" if self.is_live else "AVVIA Live Preview")

    def _toggle_freeze(self, *_):
        """Inverte lo stato di freeze."""
        self.frozen = not self.frozen
        # Se il widget esiste gia', lo rimuovo prima di ricrearlo
        if dpg.does_item_exist("tae_label_freeze"):
            if self.frozen:
                # Aggiorna il valore di un widget DPG
                dpg.set_value("tae_label_freeze", "Preview: FROZEN")
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item("tae_label_freeze", color=(100, 200, 255))
            else:
                # Aggiorna il valore di un widget DPG
                dpg.set_value("tae_label_freeze", "Preview: LIVE")
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item("tae_label_freeze", color=(150, 200, 255))
        # Se il widget esiste gia', lo rimuovo prima di ricrearlo
        if dpg.does_item_exist("tae_btn_freeze"):
            dpg.set_item_label("tae_btn_freeze",
                               "Sblocca [F]" if self.frozen else "Freeze [F]")
        self.aggiorna_preview()

    # Callback per l'evento
    def _on_key_freeze(self, *_):
        """Callback per l'evento key freeze."""
        if self.e_aperto():
            self._toggle_freeze()
