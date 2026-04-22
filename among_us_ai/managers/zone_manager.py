"""
Gestione delle zone nominate disegnate a mano sulla mappa.

Ogni zona e' un poligono freehand con un nome, un colore e (opzionalmente)
l'ID della zona corrispondente nel gioco. Il file di persistenza e' un
JSON con la lista di zone e l'ID progressivo del prossimo elemento.
"""

import json
import os

from ..core.config import GPSConfig


class ZoneManager:
    """
    Gestisce le zone nominate (poligoni freehand) e la loro persistenza.

    Formato di ogni zona: ``{id, nome, colore, punti: [[x, y], ...]}``.
    Le coordinate sono in spazio di gioco (y cresce verso l'alto).
    """

    def __init__(self, file_path):
        """
        :param file_path: path del file JSON delle zone (es. ``zone_skeld.json``).
        """
        self.file_path = file_path
        self.zone = []
        self.prossimo_id = 1
        self.carica()

    # ------------------------------------------------------------------
    # Persistenza
    # ------------------------------------------------------------------

    def carica(self):
        """Carica la lista zone dal JSON. Se assente o malformato, ignora."""
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, 'r') as f:
                data = json.load(f)
            raw = data.get('zone', [])
            # Filtra zone valide: dict con 'punti' lista >=3 elementi.
            # Float-cast esplicito per robustezza (i JSON producono float
            # ma alcuni vecchi salvati potrebbero avere int).
            self.zone = []
            for z in raw:
                if (isinstance(z, dict) and 'punti' in z
                        and isinstance(z['punti'], list) and len(z['punti']) >= 3):
                    z['punti'] = [[float(p[0]), float(p[1])] for p in z['punti']]
                    self.zone.append(z)
            # prossimo_id: dal JSON se presente, altrimenti max id + 1.
            self.prossimo_id = data.get(
                'prossimo_id',
                max([z['id'] for z in self.zone], default=0) + 1,
            )
            print(f"Zone caricate: {len(self.zone)}.")
        except Exception as e:
            print(f"Errore caricamento zone ({e}).")

    def salva(self):
        """Serializza zone + prossimo_id su disco."""
        try:
            with open(self.file_path, 'w') as f:
                json.dump({
                    'zone': self.zone,
                    'prossimo_id': self.prossimo_id,
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Errore salvataggio zone ({e}).")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def aggiungi(self, nome, punti, colore=None):
        """Crea una nuova zona; colore auto-ciclato se non specificato."""
        if colore is None:
            # Ciclo nella palette COLORI_ZONE: idx = (id-1) % len_palette.
            # Cosi' zone consecutive hanno colori diversi.
            idx = (self.prossimo_id - 1) % len(GPSConfig.COLORI_ZONE)
            colore = GPSConfig.COLORI_ZONE[idx]
        zona = {
            'id': self.prossimo_id,
            'nome': nome,
            'colore': colore,
            'punti': [[float(p[0]), float(p[1])] for p in punti],
        }
        self.zone.append(zona)
        self.prossimo_id += 1
        self.salva()
        return zona

    def rimuovi(self, id_zona):
        """Rimuove la zona con l'id dato (no-op se non trovata)."""
        self.zone = [z for z in self.zone if z['id'] != id_zona]
        self.salva()

    def rinomina(self, id_zona, nuovo_nome):
        """Rinomina la zona con l'id dato."""
        for z in self.zone:
            if z['id'] == id_zona:
                z['nome'] = nuovo_nome
                break
        self.salva()

    def aggiorna_forma(self, id_zona, punti):
        """Sostituisce i punti del poligono di una zona esistente."""
        for z in self.zone:
            if z['id'] == id_zona:
                z['punti'] = [[float(p[0]), float(p[1])] for p in punti]
                break
        self.salva()

    def cambia_colore(self, id_zona, colore):
        """Cambia il colore (stringa hex) di una zona esistente."""
        for z in self.zone:
            if z['id'] == id_zona:
                z['colore'] = colore
                break
        self.salva()

    # ------------------------------------------------------------------
    # Mapping con le zone del gioco (room id della RAM)
    # ------------------------------------------------------------------

    def set_game_zone_id(self, id_zona, game_zone_id):
        """
        Imposta (o rimuove se ``None``/``""``) l'ID di stanza del gioco
        su una zona disegnata. Serve per matchare ``mt.id_stanza`` letto
        dalla RAM con un poligono visivo nella UI.
        """
        for z in self.zone:
            if z['id'] == id_zona:
                if game_zone_id is None or game_zone_id == "":
                    z.pop('game_zone_id', None)
                else:
                    z['game_zone_id'] = int(game_zone_id)
                break
        self.salva()

    def get_by_game_zone_id(self, game_zone_id):
        """Ritorna la zona con il ``game_zone_id`` indicato, oppure ``None``."""
        for z in self.zone:
            if z.get('game_zone_id') == game_zone_id:
                return z
        return None

    # ------------------------------------------------------------------
    # Helper geometrici (statici: non dipendono dalla persistenza)
    # ------------------------------------------------------------------

    @staticmethod
    def centroide(zona):
        """
        Centroide approssimato (media aritmetica dei vertici) di un poligono.
        Non e' il baricentro vero, ma sufficiente per le label sulla mappa.
        """
        pts = zona.get('punti', [])
        if not pts:
            return (0.0, 0.0)
        sx = sum(p[0] for p in pts) / len(pts)
        sy = sum(p[1] for p in pts) / len(pts)
        return (sx, sy)

    @staticmethod
    def bbox(zona):
        """
        Bounding box assi-allineato del poligono.

        :return: tupla ``(min_x, min_y, max_x, max_y)``.
        """
        pts = zona.get('punti', [])
        if not pts:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))
