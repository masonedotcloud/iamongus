"""
Caricamento mappa da JSON e calcolo dei bounds.

Mixin di GPSVisualizerPro: metodi separati per organizzazione, ma
condividono lo stato self.* della classe principale.
"""

from ._imports import *



class MapLoaderMixin:
    """Mixin con i metodi di map loader di GPSVisualizerPro."""
    def carica_mappa(self):
        """Carica da file mappa."""
        if not os.path.exists(GPSConfig.MAP_FILE): return
        try:
            with open(GPSConfig.MAP_FILE, 'r') as f:
                # Carica e deserializza JSON da file
                data = json.load(f)
                for k in data.get('visitati', []):
                    try:
                        kx, ky = map(float, k.split(','))
                        self.visitati_coords.append((kx, ky))
                    except ValueError:
                        pass
        except Exception as e:
            print(f"Errore caricamento mappa: {e}")

    def _calcola_bounds_mappa(self):
        """Calcola bounds mappa."""
        if not self.visitati_coords:
            self.map_bounds = (-10, -10, 10, 10); return
        xs = [p[0] for p in self.visitati_coords]
        ys = [p[1] for p in self.visitati_coords]
        pad = 2.0
        self.map_bounds = (min(xs) - pad, min(ys) - pad,
                           max(xs) + pad, max(ys) + pad)

    def _ricarica_mappa(self):
        """Ricarica mappa."""
        self.visitati_coords = []
        self.carica_mappa()
        self._calcola_bounds_mappa()
        self.pathfinder.rebuild(self.visitati_coords)
        # Rimuove l'elemento DPG (cleanup)
        dpg.delete_item("map_node", children_only=True)
        dpg.push_container_stack("map_node")
        step_u = GPSConfig.CELL_STEP
        for kx, ky in self.visitati_coords:
            dpg.draw_rectangle((kx, -ky), (kx + step_u, -ky + step_u),
                               color=Colors.VISITED, fill=Colors.VISITED)
        dpg.pop_container_stack()
        # Aggiorna il valore di un widget DPG
        dpg.set_value("stat_visited", f"{len(self.visitati_coords)}")
        # Aggiorna il valore di un widget DPG
        dpg.set_value("stat_walkable", f"{len(self.pathfinder.walkable)}")
