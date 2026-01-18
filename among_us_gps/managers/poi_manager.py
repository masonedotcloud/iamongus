"""
Gestione dei Punti di Interesse (POI) come emergency button, security,
admin, ecc.

Ogni POI ha un nome, una posizione (x, y) e un'eventuale associazione
ad una zona (per filtri/scrolling rapido nella UI).
"""

import json
import os


class PoiManager:
    """
    Gestisce i Punti di Interesse (POI).

    Formato: ``{id, nome, x, y, zone_id, zone_local_id, zone_nome}``.
    """

    def __init__(self, file_path):
        self.file_path   = file_path
        self.poi_list    = []
        self.prossimo_id = 1
        self.carica()

    # ------------------------------------------------------------------
    # Persistenza
    # ------------------------------------------------------------------

    def carica(self):
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, 'r') as f:
                data = json.load(f)
            self.poi_list = data.get('poi_list', [])
            self.prossimo_id = max((p['id'] for p in self.poi_list), default=0) + 1
            print(f"POI caricati: {len(self.poi_list)}")
        except Exception as e:
            print(f"Errore caricamento POI ({e}).")

    def salva(self):
        try:
            with open(self.file_path, 'w') as f:
                json.dump({'poi_list': self.poi_list}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Errore salvataggio POI ({e}).")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def aggiungi(self, nome, x, y,
                 zone_id=None, zone_local_id=None, zone_nome=None):
        poi = {
            'id':            self.prossimo_id,
            'nome':          nome,
            'x':             float(x),
            'y':             float(y),
            'zone_id':       zone_id,
            'zone_local_id': zone_local_id,
            'zone_nome':     zone_nome,
        }
        self.poi_list.append(poi)
        self.prossimo_id += 1
        self.salva()
        return poi

    def aggiorna(self, id_poi, nome, x, y,
                 zone_id=None, zone_local_id=None, zone_nome=None):
        for p in self.poi_list:
            if p['id'] == id_poi:
                p['nome']          = nome
                p['x']             = float(x)
                p['y']             = float(y)
                p['zone_id']       = zone_id
                p['zone_local_id'] = zone_local_id
                p['zone_nome']     = zone_nome
                break
        self.salva()

    def rimuovi(self, id_poi):
        self.poi_list = [p for p in self.poi_list if p['id'] != id_poi]
        self.salva()

    def get_by_id(self, id_poi):
        for p in self.poi_list:
            if p['id'] == id_poi:
                return p
        return None
