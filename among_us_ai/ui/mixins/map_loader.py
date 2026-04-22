"""
Caricamento mappa da JSON e calcolo dei bounds.

Mixin di GPSVisualizerPro: metodi separati per organizzazione, ma
condividono lo stato self.* della classe principale.
"""

from ._imports import *



class MapLoaderMixin:
    """Mixin con i metodi di caricamento mappa di :class:`GPSVisualizerPro`."""

    def carica_mappa(self):
        """
        Carica le celle calpestabili da ``MAP_FILE`` (file JSON con la
        chiave ``visitati`` = lista di stringhe ``"x,y"``).

        Le celle vengono appese a ``self.visitati_coords``. Non rigenera
        i bounds ne' il pathfinder - lo fa :meth:`_ricarica_mappa`.
        Tollerante a entries malformate (skip silent).
        """
        if not os.path.exists(GPSConfig.MAP_FILE):
            return
        try:
            with open(GPSConfig.MAP_FILE, 'r') as f:
                data = json.load(f)
                for k in data.get('visitati', []):
                    try:
                        kx, ky = map(float, k.split(','))
                        self.visitati_coords.append((kx, ky))
                    except ValueError:
                        # Entry malformata: skip silenzioso
                        pass
        except Exception as e:
            print(f"Errore caricamento mappa: {e}")

    def _calcola_bounds_mappa(self):
        """
        Calcola il bounding box delle celle visitate (con padding di 2
        unita') e lo memorizza in ``self.map_bounds``. Se la mappa e'
        vuota usa un bbox di default ``(-10, -10, 10, 10)``.
        """
        if not self.visitati_coords:
            self.map_bounds = (-10, -10, 10, 10)
            return
        xs = [p[0] for p in self.visitati_coords]
        ys = [p[1] for p in self.visitati_coords]
        pad = 2.0
        self.map_bounds = (min(xs) - pad, min(ys) - pad,
                           max(xs) + pad, max(ys) + pad)

    def _ricarica_mappa(self):
        """
        Ricarica la mappa da zero: svuota le celle in memoria, ricarica
        dal file, ricostruisce bounds + pathfinder e ridisegna i quadrati
        della mappa nel canvas DPG.
        """
        self.visitati_coords = []
        self.carica_mappa()
        self._calcola_bounds_mappa()
        self.pathfinder.rebuild(self.visitati_coords)
        # Pulisci e ridisegna il layer mappa.
        dpg.delete_item("map_node", children_only=True)
        dpg.push_container_stack("map_node")
        step_u = GPSConfig.CELL_STEP
        for kx, ky in self.visitati_coords:
            dpg.draw_rectangle((kx, -ky), (kx + step_u, -ky + step_u),
                               color=Colors.VISITED, fill=Colors.VISITED)
        dpg.pop_container_stack()
        # Aggiorna i contatori in status bar.
        dpg.set_value("stat_visited", f"{len(self.visitati_coords)}")
        dpg.set_value("stat_walkable", f"{len(self.pathfinder.walkable)}")
