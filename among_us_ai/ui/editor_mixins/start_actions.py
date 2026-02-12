"""
Pulsanti che avviano la registrazione di una nuova azione.

Mixin di TaskActionEditor.
"""

from ._imports import *


class EditorStartActionsMixin:
    """Mixin con i metodi di editor start actions di GPSVisualizerPro."""
    def _avvia(self, nuovo_stato, msg, color):
        """Avvia."""
        self.stato = nuovo_stato
        self.buffer_punti = []
        self._imposta_istruzioni(msg, color)

    def _avvia_multi(self, *_):
        """Avvia multi."""
        self.buffer_punti = []
        self.stato = self.WAIT_MULTI
        self._imposta_istruzioni(
            "MULTI-DRAG: CLICK sulla preview per ogni punto (>=2). Poi 'CHIUDI PUNTI'.",
            (255, 180, 100))

    def _avvia_poly_click(self, *_):
        """Avvia poly click."""
        self.buffer_punti = []
        self.stato = self.WAIT_POLY
        self._imposta_istruzioni(
            "POLIGONO: CLICK sulla preview per ogni vertice (>=3). Poi 'CHIUDI PUNTI'.",
            (200, 180, 255))

    def _avvia_drag_zone(self, *_):
        """Avvia drag zone."""
        self.buffer_punti  = []
        self.buffer_zone_a = []
        self.stato = self.WAIT_POLY_ZONE_A
        self._imposta_istruzioni(
            "DRAG ZONA: disegna ZONA A (click vertici, >=3). Poi 'CHIUDI PUNTI'.",
            (255, 150, 200))

    def _avvia_wiring(self, *_):
        """Avvia wiring."""
        self.stato = self.WAIT_WIRING_L
        self.buffer_w_l, self.buffer_w_r, self.buffer_w_c = [], [], []
        self._imposta_istruzioni("WIRING: Clicca sulla punta dei 4 CAVI DI SINISTRA (1/4)",
                                 (200, 255, 100))

    def _avvia_sync_click(self, *_):
        """Avvia sync click."""
        self.stato = self.WAIT_SYNC_CHECK
        self.buffer_sync = []
        self._imposta_istruzioni("SYNC CLICK: Clicca PUNTO DA CONTROLLARE (luce/led).", (255, 255, 100))

    def _avvia_yolo_drag(self, *_):
        """Avvia yolo drag."""
        def on_name(nome):
            """Callback di input del nome."""
            if nome:
                self._tmp_yolo_model = nome
                self.stato = self.WAIT_YOLO_POLY
                self.buffer_punti = []
                self.buffer_zone_a = []
                self._imposta_istruzioni(f"DRAG YOLO '{nome}': Disegna la ZONA DI RICERCA (poly, >=3). Poi 'CHIUDI PUNTI'.", (255, 100, 255))
            else:
                self._imposta_istruzioni("Aggiunta azione annullata.", (255, 100, 100))
        self._show_text_input("Inserisci il nome del modello YOLO (es. arrow.pt)", "best.pt", on_name)

    def _avvia_yolo_drag_all(self, *_):
        """Avvia yolo drag all."""
        def on_name(nome):
            """Callback di input del nome."""
            if nome:
                self._tmp_yolo_model = nome
                self.stato = self.WAIT_YOLO_ALL_POLY
                self.buffer_punti = []
                self.buffer_zone_a = []
                self._imposta_istruzioni(f"DRAG ALL YOLO '{nome}': Disegna la ZONA (poly, >=3). Poi 'CHIUDI PUNTI'.", (255, 120, 100))
            else:
                self._imposta_istruzioni("Aggiunta azione annullata.", (255, 100, 100))
        self._show_text_input("Inserisci il nome del modello YOLO (es. foglie.pt)", "best.pt", on_name)

    def _avvia_click_until(self, *_):
        """Avvia click until."""
        self.stato = self.WAIT_CUC_CHK
        self.buffer_cuc = []
        self._imposta_istruzioni("CLICK UNTIL: Clicca PUNTO DA CONTROLLARE (diventera' bianco).", (255, 255, 255))

    def _avvia_simon_says(self, *_):
        """Avvia simon says."""
        self.stato = self.WAIT_SIMON_DISPLAY
        self.buffer_simon_d = []
        self.buffer_simon_k = []
        self._imposta_istruzioni("SIMON SAYS: Clicca le posizioni delle LUCI/SCHERMO (minimo 1). Poi CHIUDI PUNTI.", (100, 200, 255))

    def _avvia_anomaly_click(self, *_):
        """Avvia anomaly click."""
        self.stato = self.WAIT_ANOMALY_CHK
        self.buffer_anomaly = []
        self._imposta_istruzioni("CLICK ANOMALIA: Clicca PUNTO DA CONTROLLARE (colore).",
                                 (255, 100, 200))

    def _avvia_num_match(self, *_):
        """Avvia num match."""
        self.stato = self.WAIT_NUM_MATCH_RECT
        self.buffer_num_match = []
        self.rect_drag_active = False
        self.rect_start = None
        self.rect_end = None
        self._imposta_istruzioni("NUMBER MATCH: Trascina rect per il numero 1.", (100, 255, 255))

    def _avvia_ocr_keypad(self, *_):
        """Avvia ocr keypad."""
        self.stato = self.WAIT_OCR_POLY
        self.buffer_punti = []
        self.buffer_keypad = []
        self._imposta_istruzioni("OCR KEYPAD: Disegna ZONA DISPLAY (poly, >=3). Poi 'CHIUDI PUNTI'.", (100, 255, 200))

    def _avvia_yolo_click(self, *_):
        """Avvia yolo click."""
        def on_name(nome):
            """Callback di input del nome."""
            if nome:
                self._tmp_yolo_model = nome
                self.stato = self.WAIT_YOLO_CLICK_POLY
                self.buffer_punti = []
                self.buffer_zone_a = []
                self._imposta_istruzioni(f"CLICK YOLO '{nome}': Disegna la ZONA DI RICERCA (poly, >=3). Poi 'CHIUDI PUNTI'.", (100, 255, 100))
            else:
                self._imposta_istruzioni("Aggiunta azione annullata.", (255, 100, 100))
        self._show_text_input("Inserisci il nome del modello YOLO (es. asteroidi.pt)", "best.pt", on_name)

    def _avvia_yolo_click_all(self, *_):
        """Avvia yolo click all."""
        def on_name(nome):
            """Callback di input del nome."""
            if nome:
                self._tmp_yolo_model = nome
                self.stato = self.WAIT_YOLO_CLICK_ALL_POLY
                self.buffer_punti = []
                self.buffer_zone_a = []
                self._imposta_istruzioni(f"CLICK ALL YOLO '{nome}': Disegna la ZONA DI RICERCA (poly, >=3). Poi 'CHIUDI PUNTI'.", (100, 255, 150))
            else:
                self._imposta_istruzioni("Aggiunta azione annullata.", (255, 100, 100))
        self._show_text_input("Inserisci il nome del modello YOLO (es. asteroidi.pt)", "best.pt", on_name)

    def _avvia_yolo_drag_seq(self, *_):
        """Avvia yolo drag seq."""
        def on_name(nome):
            """Callback di input del nome."""
            if nome:
                self._tmp_yolo_model = nome
                self.stato = self.WAIT_YOLO_SEQ_POLY
                self.buffer_punti = []
                self._imposta_istruzioni(f"DRAG SEQ YOLO '{nome}': Disegna la ZONA DI RICERCA (poly, >=3). Poi 'CHIUDI PUNTI'.", (255, 120, 200))
            else:
                self._imposta_istruzioni("Aggiunta azione annullata.", (255, 100, 100))
        self._show_text_input("Nome modello YOLO (es. seq.pt)", "best.pt", on_name)

    def _avvia_cooldown(self, *_):
        """Avvia cooldown."""
        durata = dpg.get_value(self.TAG_IN_DUR)
        self.azioni.append({
            "tipo": "cooldown",
            "durata": durata
        })
        self._imposta_istruzioni(f"Cooldown (cambio fase) aggiunto: {durata}s.", (100, 255, 100))
        self.aggiorna_lista()
        self.aggiorna_preview()

    def _avvia_drag_hold(self, *_):
        """Avvia registrazione drag_hold: due click (A, poi B)."""
        self.buffer_punti = []
        self.stato = self.WAIT_DRAG_HOLD_START
        self._imposta_istruzioni(
            "DRAG+TIENI: CLICK sulla preview per PARTENZA (punto A).",
            (255, 140, 180))

    def _avvia_rect_click(self, *_):
        """Avvia rect click."""
        self.stato = "WAIT_RECT_ON_CANVAS"
        self.rect_drag_active = False
        self.rect_start = None
        self.rect_end   = None
        self._imposta_istruzioni(
            "CLICK RETT: trascina sulla PREVIEW per disegnare il rettangolo.",
            (180, 255, 180))
