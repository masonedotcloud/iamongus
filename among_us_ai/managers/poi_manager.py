"""
Gestione dei Punti di Interesse (POI): emergency button, security, admin, vent,
cadaveri, ecc.

Ogni POI ha un nome, una posizione ``(x, y)`` e (opzionale) un'associazione
ad una zona di mappa per filtri rapidi nella UI. La persistenza e' un file
JSON unico con la lista completa.
"""

import json
import os


class PoiManager:
    """
    Gestisce i Punti di Interesse (POI) su disco.

    Formato di ogni POI:
        ``{id, nome, x, y, id_zona, id_zona_locale, nome_zona}``
    """

    def __init__(self, file_path):
        """
        :param file_path: path del file JSON dei POI (es. ``poi_skeld.json``).
                          Se non esiste, parte con lista vuota.
        """
        self.file_path   = file_path
        self.poi_list    = []
        self.prossimo_id = 1
        self.carica()

    # ------------------------------------------------------------------
    # Persistenza
    # ------------------------------------------------------------------

    def carica(self):
        """Carica la lista POI dal file. Se assente o malformato, ignora."""
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, 'r') as f:
                data = json.load(f)
            self.poi_list = data.get('poi_list', [])
            # prossimo_id = max id esistente + 1 (per non collidere con
            # POI gia' salvati al prossimo aggiungi).
            self.prossimo_id = max((p['id'] for p in self.poi_list), default=0) + 1
            print(f"POI caricati: {len(self.poi_list)}")
        except Exception as e:
            print(f"Errore caricamento POI ({e}).")

    def salva(self):
        """Serializza l'intera lista POI su disco (overwrite atomico via json.dump)."""
        try:
            with open(self.file_path, 'w') as f:
                json.dump({'poi_list': self.poi_list}, f,
                          indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Errore salvataggio POI ({e}).")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def aggiungi(self, nome, x, y,
                 id_zona=None, id_zona_locale=None, nome_zona=None):
        """Crea un nuovo POI con id auto-incrementato e lo persiste."""
        poi = {
            'id':            self.prossimo_id,
            'nome':          nome,
            'x':             float(x),
            'y':             float(y),
            'id_zona':       id_zona,
            'id_zona_locale': id_zona_locale,
            'nome_zona':     nome_zona,
        }
        self.poi_list.append(poi)
        self.prossimo_id += 1
        self.salva()
        return poi

    def aggiorna(self, id_poi, nome, x, y,
                 id_zona=None, id_zona_locale=None, nome_zona=None):
        """Aggiorna un POI esistente (cerca per id). Persiste su disco."""
        for p in self.poi_list:
            if p['id'] == id_poi:
                p['nome']          = nome
                p['x']             = float(x)
                p['y']             = float(y)
                p['id_zona']       = id_zona
                p['id_zona_locale'] = id_zona_locale
                p['nome_zona']     = nome_zona
                break
        self.salva()

    def rimuovi(self, id_poi):
        """Rimuove il POI con l'id dato (no-op se non trovato)."""
        self.poi_list = [p for p in self.poi_list if p['id'] != id_poi]
        self.salva()

    def get_by_id(self, id_poi):
        """Cerca un POI per id. Ritorna il dict oppure ``None``."""
        for p in self.poi_list:
            if p['id'] == id_poi:
                return p
        return None
