"""
Pathfinder A* su griglia di celle "calpestabili".

Le celle sono ricavate dal trail registrato dal mapper: il bot si muove
solo dove un giocatore umano e' effettivamente passato (`visitati_coords`).

Funzionalita' principali:
- A* con costo euclideo, prevenzione del corner-cutting e penalita' per
  stare lontani dai muri.
- Path smoothing tramite funnel/string-pulling con hitbox a croce.
- Supporto per ostacoli dinamici (porte) tramite `dynamic_obstacles`.
"""

import heapq
import math

from ..core.config import GPSConfig


class Pathfinder:
    """
    Lavora su celle intere: key = (int(round(x/STEP)), int(round(y/STEP))).
    `walkable` e' il set di queste chiavi, costruito dalle celle visitate.
    """

    def __init__(self, step):
        """Inizializza l'istanza con i valori di default."""
        self.step = step
        self.walkable = set()
        self.dynamic_obstacles = set()
        self.penalties = {}

    # ------------------------------------------------------------------
    # Costruzione mappa percorribile
    # ------------------------------------------------------------------

    def rebuild(self, visitati_coords):
        """
        Rigenera il set di celle calpestabili e calcola le penalita' per
        stare lontani dai muri.
        """
        base = set()
        for x, y in visitati_coords:
            base.add(self._key(x, y))

        # NB: nessuna dilatazione - il bot cammina rigorosamente solo dove
        # e' stato registrato il passaggio, evitando di "sbordare" nei muri.
        self.walkable = base

        # Precalcola penalita' per tenere il bot al centro dei corridoi.
        self.penalties.clear()
        for cell in self.walkable:
            p = 0.0
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if (cell[0] + dx, cell[1] + dy) not in self.walkable:
                        p += 0.4  # penalita' morbida -> percorsi piu' dritti
            if p > 0:
                self.penalties[cell] = p

    def _key(self, x, y):
        """Funzione di chiave per ordinare gli elementi."""
        return (int(round(x / self.step)), int(round(y / self.step)))

    def _coord(self, key):
        """Converte coordinate."""
        return (key[0] * self.step, key[1] * self.step)

    def nearest_walkable(self, x, y, radius=80):
        """Trova la cella calpestabile piu' vicina entro un dato raggio."""
        start = self._key(x, y)
        if start in self.walkable:
            return start
        for r in range(1, radius + 1):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    if abs(dx) != r and abs(dy) != r:
                        continue
                    c = (start[0] + dx, start[1] + dy)
                    if c in self.walkable:
                        return c
        # Goal irraggiungibile o limite nodi superato
        return None

    # ------------------------------------------------------------------
    # A*
    # ------------------------------------------------------------------

    def astar(self, start_xy, goal_xy, max_nodes=20000, extra_penalties=None):
        """
        Algoritmo A*: trova il percorso piu' corto da start a goal.

        :param extra_penalties: dict {(cx, cy): float} con penalita'
            aggiuntive PER CELLA, sommate alle `self.penalties` di base.
            Utile per "evita player sospetti": chi chiama costruisce
            un dict con celle vicine ai player sospetti -> A* preferisce
            aggirarle (ma puo' ancora passarci se serve).
        """
        if not self.walkable:
            # Goal irraggiungibile o limite nodi superato
            return None

        start = self.nearest_walkable(start_xy[0], start_xy[1], GPSConfig.NEAREST_SEARCH_RADIUS)
        goal  = self.nearest_walkable(goal_xy[0], goal_xy[1], GPSConfig.NEAREST_SEARCH_RADIUS)
        if start is None or goal is None or start == goal:
            if start == goal and start is not None:
                return [self._coord(start)]
            # Goal irraggiungibile o limite nodi superato
            return None

        def h(a, b):
            """Funzione di euristica per l'algoritmo A*."""
            return math.hypot(a[0] - b[0], a[1] - b[1])

        open_heap = [(h(start, goal), 0, start)]
        came_from = {}
        g_score = {start: 0.0}
        closed = set()
        visited_count = 0

        neighbors = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
                     (-1, -1, 1.4142), (-1, 1, 1.4142),
                     (1, -1, 1.4142), (1, 1, 1.4142)]

        # Helper per leggere penalita' totale di una cella
        extra = extra_penalties or {}

        while open_heap:
            _, _, current = heapq.heappop(open_heap)
            if current in closed:
                continue

            if current == goal:
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                path = self._smooth(path)  # string-pulling
                return [self._coord(k) for k in path]

            # Marca il nodo come visitato (chiuso)
            closed.add(current)
            visited_count += 1
            if visited_count > max_nodes:
                # Goal irraggiungibile o limite nodi superato
                return None

            for dx, dy, cost in neighbors:
                nb = (current[0] + dx, current[1] + dy)
                if nb not in self.walkable or nb in closed:
                    continue
                if nb in self.dynamic_obstacles:
                    continue

                # Prevenzione del corner-cutting in A*
                if dx != 0 and dy != 0:
                    c1 = (current[0] + dx, current[1])
                    c2 = (current[0], current[1] + dy)
                    if c1 not in self.walkable or c1 in self.dynamic_obstacles:
                        continue
                    if c2 not in self.walkable or c2 in self.dynamic_obstacles:
                        continue

                wall_penalty = self.penalties.get(nb, 0.0)
                extra_penalty = extra.get(nb, 0.0)
                tentative = g_score[current] + cost + wall_penalty + extra_penalty
                if tentative < g_score.get(nb, float('inf')):
                    came_from[nb] = current
                    g_score[nb] = tentative
                    f = tentative + h(nb, goal)
                    # Inserisce nodo nella priority queue (ordinato per costo f)
                    heapq.heappush(open_heap, (f, tentative, nb))
        # Goal irraggiungibile o limite nodi superato
        return None

    # ------------------------------------------------------------------
    # Test linee dirette
    # ------------------------------------------------------------------

    def line_has_dynamic_obstacle(self, start_xy, end_xy):
        """Controlla se una linea retta interseca un ostacolo dinamico (porta)."""
        a = self._key(start_xy[0], start_xy[1])
        b = self._key(end_xy[0], end_xy[1])

        dx = b[0] - a[0]
        dy = b[1] - a[1]
        dist = math.hypot(dx, dy)
        if dist == 0:
            return a in self.dynamic_obstacles

        steps = int(dist * 3)
        if steps == 0:
            steps = 1

        for i in range(steps + 1):
            t = i / steps
            cx = int(round(a[0] + dx * t))
            cy = int(round(a[1] + dy * t))

            for offset_x in (-1, 0, 1):
                for offset_y in (-1, 0, 1):
                    cell = (cx + offset_x, cy + offset_y)
                    if cell in self.dynamic_obstacles:
                        return True
        return False

    def line_walkable_coords(self, start_xy, end_xy):
        """Verifica se la linea da A a B passa solo per celle calpestabili."""
        a = self._key(start_xy[0], start_xy[1])
        b = self._key(end_xy[0], end_xy[1])
        return self._line_walkable(a, b)

    def _line_walkable(self, a, b):
        """
        Linea percorribile considerando la LARGHEZZA del bot.
        Hitbox a "croce" (5 celle) per evitare di sbattere nei muri.
        """
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        dist = math.hypot(dx, dy)
        if dist == 0:
            return a in self.walkable

        steps = int(dist * 3)
        if steps == 0:
            steps = 1

        for i in range(steps + 1):
            t = i / steps
            cx = int(round(a[0] + dx * t))
            cy = int(round(a[1] + dy * t))
            for offset_x, offset_y in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                cell = (cx + offset_x, cy + offset_y)
                if cell not in self.walkable or cell in self.dynamic_obstacles:
                    return False
        return True

    def _smooth(self, path):
        """String-pulling: scarta i waypoint visibili in linea retta."""
        if len(path) < 3:
            return path
        result = [path[0]]
        i = 0
        while i < len(path) - 1:
            j = len(path) - 1
            while j > i + 1 and not self._line_walkable(path[i], path[j]):
                j -= 1
            result.append(path[j])
            i = j
        return result

    def astar_straight(self, start_xy, goal_xy):
        """
        Path "fantasma": linea retta che attraversa i muri.

        Usato quando il bot e' crewmate morto (PHASE_GHOST): in Among Us
        i fantasmi possono passare attraverso le pareti, quindi non serve
        un vero pathfinding. Ritorna un path di 2 punti: [start, goal].

        NB: non c'e' clamp alle celle walkable; il fantasma puo' andare
        ovunque sulla mappa.
        """
        sx, sy = float(start_xy[0]), float(start_xy[1])
        gx, gy = float(goal_xy[0]), float(goal_xy[1])
        if sx == gx and sy == gy:
            return [(sx, sy)]
        return [(sx, sy), (gx, gy)]
