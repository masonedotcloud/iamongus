"""
Funzioni varie: trail, esportazione, varie utility.

Mixin di GPSVisualizerPro: metodi separati per organizzazione, ma
condividono lo stato self.* della classe principale.
"""

from ._imports import *



class MiscMixin:
    """Mixin con utility varie (trail, export, distanza percorsa) di :class:`GPSVisualizerPro`."""
    def _clear_trail(self):
        """Cancella il trail (storico delle posizioni) per ricominciare da capo."""
        self.trail = []

    def _reset_distance(self):
        """Azzera contatore distanza totale e tempo di sessione."""
        self.total_distance = 0.0
        self.last_pos_for_dist = None
        self.session_start = time.time()

    def _esporta_trail(self):
        """Salva il trail corrente in `trail_export.json` per riuso o debug."""
        try:
            with open("trail_export.json", "w") as f:
                json.dump({"trail": [[p[0], p[1]] for p in self.trail]}, f)
            print("Trail esportato in trail_export.json")
        except Exception as e:
            print(f"Errore export: {e}")

    def _esporta_tutto(self):
        """
        Esporta in un'unica cartella con timestamp:
          - mappa_skeld.json
          - task_registrate.json
          - zone_skeld.json
          - mappa_preview.png  (rendering vettoriale dall'alto)
          - export.zip         (tutti i file sopra)
        """
        import zipfile, shutil
        from datetime import datetime

        # --- 1. Cartella di destinazione con timestamp ---
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir   = f"export_{ts}"
        os.makedirs(out_dir, exist_ok=True)

        # --- 2. Copia JSON ---
        copiati = []
        for src in (GPSConfig.MAP_FILE, GPSConfig.TASK_FILE,
                    GPSConfig.ZONE_FILE, GPSConfig.POI_FILE):
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(out_dir, os.path.basename(src)))
                copiati.append(os.path.basename(src))

        # --- 3. Genera PNG mappa in 5 risoluzioni ---
        RISOLUZIONI = [512, 1024, 2048, 4096, 8192]
        ok_png = False
        for res in RISOLUZIONI:
            png_nome = f"mappa_{res}px.png"
            png_path = os.path.join(out_dir, png_nome)
            ok = self._genera_png_mappa(png_path, img_size=res)
            if ok:
                ok_png = True
        # --- 4. Crea ZIP ---
        zip_path = f"export_{ts}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(out_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    zf.write(fpath, arcname=fname)

        # --- 5. Feedback ---
        png_msg = "+ 5x PNG (512->8192px)" if ok_png else "(Pillow non installato: PNG saltati)"
        self.auto_status_msg = f"Esportato -> {zip_path}  ({', '.join(copiati)} {png_msg})"
        print(f"[EXPORT] {zip_path}  |  cartella: {out_dir}")

    def _genera_png_mappa(self, output_path, img_size=1200):
        """
        Disegna la mappa su un'immagine PIL e la salva come PNG.
        Colori:
          - sfondo scuro
          - celle visitate = grigio scuro
          - zone = colore zona semi-trasparente
          - task normale = arancione  |  vitale = rosso  |  fatta = (non disponibile offline)
          - fasi task = ciano, collegate da linea
          - trail = giallo (se presente)
        """
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            print("[EXPORT] Pillow non installato. Installa con: pip install Pillow")
            return False

        import math as _m

        # ---- bounds ----
        if not self.visitati_coords:
            return False
        xs = [p[0] for p in self.visitati_coords]
        ys = [p[1] for p in self.visitati_coords]
        pad = 2.0
        min_x, max_x = min(xs) - pad, max(xs) + pad
        min_y, max_y = min(ys) - pad, max(ys) + pad
        span_x = max_x - min_x
        span_y = max_y - min_y
        scale  = img_size / max(span_x, span_y)

        img_w = int(span_x * scale) + 1
        img_h = int(span_y * scale) + 1

        def to_px(gx, gy):
            """Game coords -> pixel (Y invertita: gioco ha Y verso l'alto)."""
            px = int((gx - min_x) * scale)
            py = int((max_y - gy) * scale)   # flip Y
            return (px, py)

        # ---- immagine base ----
        img  = Image.new("RGB", (img_w, img_h), color=(12, 12, 15))
        draw = ImageDraw.Draw(img, "RGBA")

        # ---- celle visitate ----
        cell_px = max(2, int(GPSConfig.CELL_STEP * scale))
        for gx, gy in self.visitati_coords:
            px, py = to_px(gx, gy)
            draw.rectangle([px, py - cell_px, px + cell_px, py], fill=(50, 50, 58))

        # ---- zone (poligoni semi-trasparenti) ----
        for zona in self.zone_mgr.zone:
            punti = zona.get('punti', [])
            if len(punti) < 3:
                continue
            hex_col = zona.get('colore', '#3498DB')
            h = hex_col.lstrip('#')
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            poly_px = [to_px(p[0], p[1]) for p in punti]
            draw.polygon(poly_px, fill=(r, g, b, 45), outline=(r, g, b, 180))
            # Nome zona al centroide
            cx = sum(p[0] for p in punti) / len(punti)
            cy = sum(p[1] for p in punti) / len(punti)
            tx, ty = to_px(cx, cy)
            draw.text((tx, ty), zona['nome'], fill=(r, g, b, 220))

        # ---- trail ----
        if len(self.trail) >= 2:
            trail_px = [to_px(p[0], p[1]) for p in self.trail]
            for i in range(len(trail_px) - 1):
                alpha = int(60 + 160 * (i / max(1, len(trail_px) - 1)))
                draw.line([trail_px[i], trail_px[i + 1]],
                          fill=(255, 200, 0, alpha), width=2)

        # ---- task ----
        R_task = max(5, int(8 * scale / 60))   # raggio proporzionale allo zoom
        # Itera tutte le task registrate
        for t in self.task_mgr.task_list:
            is_vitale = bool(t.get('vitale', False))
            is_due_p  = bool(t.get('due_giocatori', False))

            col = (255, 40, 40) if is_vitale else (255, 140, 0)

            mx, my = to_px(t['x'], t['y'])

            # Glow esterno per task vitali
            if is_vitale:
                draw.ellipse([mx - R_task - 5, my - R_task - 5,
                              mx + R_task + 5, my + R_task + 5],
                             fill=(255, 40, 40, 60), outline=None)

            draw.ellipse([mx - R_task - 3, my - R_task - 3,
                          mx + R_task + 3, my + R_task + 3],
                         fill=(*col, 50), outline=(*col, 200), width=2)
            draw.ellipse([mx - R_task, my - R_task,
                          mx + R_task, my + R_task],
                         fill=(*col, 220))

            # Etichetta task
            tag_str  = ("[!] " if is_vitale else "") + ("[2P] " if is_due_p else "")
            label    = f"{tag_str}{t['nome']}"
            draw.text((mx - len(label) * 3, my - R_task - 14), label,
                      fill=(255, 255, 255, 220))

            # Fasi: linea + cerchio ciano numerato
            fasi = t.get('fasi', [])
            prev_px = (mx, my)
            for i, fase in enumerate(fasi, start=1):
                fsx, fsy = to_px(fase['x'], fase['y'])
                # linea di collegamento con freccia a meta'
                draw.line([prev_px, (fsx, fsy)], fill=(*col, 160), width=2)
                # freccia a meta'
                hx = (prev_px[0] + fsx) // 2
                hy = (prev_px[1] + fsy) // 2
                ang = _m.atan2(fsy - prev_px[1], fsx - prev_px[0])
                al  = 8
                draw.line([(hx, hy),
                            (int(hx - al * _m.cos(ang - 0.4)),
                             int(hy - al * _m.sin(ang - 0.4)))],
                          fill=(*col, 200), width=2)
                draw.line([(hx, hy),
                            (int(hx - al * _m.cos(ang + 0.4)),
                             int(hy - al * _m.sin(ang + 0.4)))],
                          fill=(*col, 200), width=2)
                # cerchio fase
                draw.ellipse([fsx - R_task, fsy - R_task,
                               fsx + R_task, fsy + R_task],
                             fill=(100, 200, 255, 220),
                             outline=(*col, 180), width=2)
                draw.text((fsx - 4, fsy - 7), str(i), fill=(10, 10, 10, 255))
                draw.text((fsx - len(fase['nome']) * 3, fsy - R_task - 14),
                          fase['nome'], fill=(200, 230, 255, 210))
                prev_px = (fsx, fsy)

        # ---- punti di interesse ----
        COL_POI = (80, 200, 255)
        # Itera tutti i POI
        for p in self.poi_mgr.poi_list:
            ppx, ppy = to_px(p['x'], p['y'])
            r_poi = max(6, int(10 * scale / 60))
            draw.ellipse([ppx - r_poi - 3, ppy - r_poi - 3,
                          ppx + r_poi + 3, ppy + r_poi + 3],
                         fill=(*COL_POI, 40), outline=(*COL_POI, 200), width=2)
            draw.ellipse([ppx - r_poi, ppy - r_poi,
                          ppx + r_poi, ppy + r_poi],
                         fill=(*COL_POI, 200))
            draw.text((ppx - 4, ppy - 7), "*", fill=(15, 15, 15, 255))
            zona_sfx  = f"  [{p['nome_zona']}]" if p.get('nome_zona') else ""
            poi_label = f"{p['nome']}{zona_sfx}"
            draw.text((ppx - len(poi_label) * 3, ppy - r_poi - 14),
                      poi_label, fill=(*COL_POI, 230))

        # ---- giocatore (posizione attuale) ----
        if self.pos_target != [0.0, 0.0]:
            ppx, ppy = to_px(self.pos_target[0], self.pos_target[1])
            draw.ellipse([ppx - 10, ppy - 10, ppx + 10, ppy + 10],
                         fill=(0, 255, 100, 60))
            draw.ellipse([ppx - 6, ppy - 6, ppx + 6, ppy + 6],
                         fill=(0, 255, 100, 230))
            draw.text((ppx + 10, ppy - 8), "YOU", fill=(0, 255, 100, 255))

        # ---- legenda ----
        lx, ly = 10, img_h - 90
        draw.rectangle([lx - 4, ly - 4, lx + 220, ly + 82],
                       fill=(20, 20, 25, 200))
        items_leg = [
            ((255, 140,  0), "Task da fare"),
            ((255,  40, 40), "[!] Task vitale"),
            ((100, 200, 255), "Fase secondaria"),
            ((0,  255, 100), "Posizione giocatore"),
        ]
        for i, (col_l, txt_l) in enumerate(items_leg):
            draw.ellipse([lx, ly + i*18, lx+10, ly + i*18 + 10], fill=col_l)
            draw.text((lx + 16, ly + i*18 - 1), txt_l, fill=(220, 220, 220))

        img.save(output_path, "PNG")
        return True

    def _update_trail_and_distance(self):
        """Aggiunge un punto al trail (a ritmo `TRAIL_INTERVAL`) e accumula la distanza percorsa."""
        now = time.time()
        if now - self.last_trail_time >= GPSConfig.TRAIL_INTERVAL:
            self.trail.append((self.pos_target[0], self.pos_target[1]))
            if len(self.trail) > GPSConfig.TRAIL_MAX:
                self.trail.pop(0)
            self.last_trail_time = now
        if self.last_pos_for_dist is not None:
            dx = self.pos_target[0] - self.last_pos_for_dist[0]
            dy = self.pos_target[1] - self.last_pos_for_dist[1]
            d = math.hypot(dx, dy)
            if 0.0005 < d < 5.0:
                self.total_distance += d
        self.last_pos_for_dist = list(self.pos_target)
