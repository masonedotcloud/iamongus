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
    A* su griglia di celle "calpestabili" (registrate dal trail del mapper).

    Logica chiave:
    - Coordinate continue ``(x, y)`` -> chiave intera ``(cx, cy)`` con snap a
      ``step`` (vedi :meth:`_key`). ``walkable`` e' il set di queste chiavi.
    - Penalita' pre-calcolate per stare lontani dai muri (vedi :meth:`rebuild`).
    - Path smoothing con string-pulling + hitbox a croce (vedi :meth:`_smooth`).
    - Supporto a ostacoli dinamici (porte chiuse) via ``dynamic_obstacles``.
    """

    def __init__(self, step):
        """
        :param step: dimensione di una cella della griglia (unita' di gioco).
                     Deve combaciare con lo step del mapper che ha registrato
                     ``visitati_coords`` per garantire l'allineamento.
        """
        self.step = step
        self.walkable = set()          # set di chiavi (cx, cy) percorribili
        self.dynamic_obstacles = set() # ostacoli temporanei (porte chiuse)
        self.penalties = {}            # cella -> penalita' di costo (allontana dai muri)

    # ------------------------------------------------------------------
    # Costruzione mappa percorribile
    # ------------------------------------------------------------------

    def rebuild(self, visitati_coords):
        """
        Rigenera il set di celle calpestabili e pre-calcola le penalita'
        "stai lontano dai muri" da sommare al costo A*.

        :param visitati_coords: iterable di tuple ``(x, y)`` in coordinate
                                di gioco (snappate poi alla griglia).
        """
        # Mappa le coordinate continue -> chiavi discrete della griglia.
        base = set()
        for x, y in visitati_coords:
            base.add(self._key(x, y))

        # NB: nessuna dilatazione - il bot cammina rigorosamente solo dove
        # e' stato registrato il passaggio, evitando di "sbordare" nei muri.
        self.walkable = base

        # Pre-calcolo penalita': per ogni cella, conto quanti vicini (3x3)
        # NON sono walkable. Piu' vicini "muro" = piu' penalita' = A* preferisce
        # rotte piu' centrali nei corridoi.
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
        """Snap di una coordinata continua ``(x, y)`` alla chiave di griglia ``(cx, cy)``."""
        return (int(round(x / self.step)), int(round(y / self.step)))

    def _coord(self, key):
        """Inverso di :meth:`_key`: chiave griglia -> coordinata continua centrata."""
        return (key[0] * self.step, key[1] * self.step)

    def nearest_walkable(self, x, y, radius=80):
        """
        Trova la cella calpestabile piu' vicina al punto dato, cercando
        in anelli concentrici fino a ``radius`` celle.

        Ritorna ``None`` se nessuna cella e' calpestabile nel raggio
        (target effettivamente irraggiungibile).
        """
        start = self._key(x, y)
        if start in self.walkable:
            return start
        # Spirale: per ogni raggio r, controlla solo il "bordo" del quadrato
        # (celle con |dx|==r OR |dy|==r). Evita di ri-controllare gli interni.
        for r in range(1, radius + 1):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    if abs(dx) != r and abs(dy) != r:
                        continue
                    c = (start[0] + dx, start[1] + dy)
                    if c in self.walkable:
                        return c
        return None  # nessuna cella nel raggio

    # ------------------------------------------------------------------
    # A*
    # ------------------------------------------------------------------

    def astar(self, start_xy, goal_xy, max_nodes=20000, extra_penalties=None):
        """
        Trova il percorso piu' corto da ``start_xy`` a ``goal_xy`` con A*.

        :param start_xy:        tupla ``(x, y)`` in coordinate di gioco
        :param goal_xy:         tupla ``(x, y)`` in coordinate di gioco
        :param max_nodes:       safety limit (numero massimo di nodi esplorati).
                                Se superato, ritorna ``None`` per non bloccare
                                il loop principale.
        :param extra_penalties: dict opzionale ``{(cx, cy): penalty}`` con
                                penalita' aggiuntive PER CELLA, sommate alle
                                ``self.penalties`` di base. Utile per "evita
                                player sospetti": il chiamante costruisce un
                                dict con celle vicine ai player sospetti e A*
                                preferisce aggirarle (puo' ancora passarci
                                se non c'e' alternativa).
        :return: lista di tuple ``(x, y)`` (path smoothato) oppure ``None``
                 se non raggiungibile / limite nodi superato.
        """
        if not self.walkable:
            return None  # mappa vuota: nessun percorso possibile

        # Snap di start e goal a celle effettivamente calpestabili: se l'utente
        # clicca leggermente fuori (es. su un muro), trovo la cella valida
        # piu' vicina entro NEAREST_SEARCH_RADIUS.
        start = self.nearest_walkable(start_xy[0], start_xy[1], GPSConfig.NEAREST_SEARCH_RADIUS)
        goal  = self.nearest_walkable(goal_xy[0], goal_xy[1], GPSConfig.NEAREST_SEARCH_RADIUS)
        if start is None or goal is None or start == goal:
            # Casi degeneri: niente da fare. Se start==goal e' un caso valido
            # con path di 1 punto; gli altri sono target irraggiungibili.
            if start == goal and start is not None:
                return [self._coord(start)]
            return None

        def h(a, b):
            """Euristica A*: distanza euclidea (ammissibile su griglia 8-direzioni)."""
            return math.hypot(a[0] - b[0], a[1] - b[1])

        # Min-heap ordinato per costo f = g + h.
        # Tupla: (f_score, g_score, cell) - g_score in posizione 2 fa da
        # tie-breaker stabile in caso di parita' di f.
        open_heap = [(h(start, goal), 0, start)]
        came_from = {}                 # cell -> predecessore (per ricostruzione path)
        g_score = {start: 0.0}         # costo reale minimo trovato da start a cell
        closed = set()                 # celle gia' espanse (skippiamo)
        visited_count = 0

        # 8 vicini (4 cardinali + 4 diagonali) con costo: 1.0 per cardinale,
        # sqrt(2) per diagonale.
        neighbors = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
                     (-1, -1, 1.4142), (-1, 1, 1.4142),
                     (1, -1, 1.4142), (1, 1, 1.4142)]

        # Alias locale per evitare attribute access nel hot loop.
        extra = extra_penalties or {}

        while open_heap:
            _, _, current = heapq.heappop(open_heap)
            if current in closed:
                continue  # gia' espanso con costo minore: skip

            # Goal raggiunto: ricostruisco il path risalendo da goal a start.
            if current == goal:
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                path = self._smooth(path)  # string-pulling: scarta waypoint inutili
                return [self._coord(k) for k in path]

            closed.add(current)
            visited_count += 1
            if visited_count > max_nodes:
                return None  # safety: target probabilmente irraggiungibile

            # Espansione: visito gli 8 vicini.
            for dx, dy, cost in neighbors:
                nb = (current[0] + dx, current[1] + dy)
                if nb not in self.walkable or nb in closed:
                    continue
                if nb in self.dynamic_obstacles:
                    continue  # porta chiusa o ostacolo temporaneo

                # Prevenzione del corner-cutting: per i passi diagonali entrambe
                # le celle adiacenti (ortogonali) devono essere libere, altrimenti
                # A* "scivolerebbe" attraverso un angolo di muro.
                if dx != 0 and dy != 0:
                    c1 = (current[0] + dx, current[1])
                    c2 = (current[0], current[1] + dy)
                    if c1 not in self.walkable or c1 in self.dynamic_obstacles:
                        continue
                    if c2 not in self.walkable or c2 in self.dynamic_obstacles:
                        continue

                # Costo totale al vicino = g_corrente + costo_passo
                #                          + penalita' muri + penalita' extra (sospetti)
                wall_penalty = self.penalties.get(nb, 0.0)
                extra_penalty = extra.get(nb, 0.0)
                tentative = g_score[current] + cost + wall_penalty + extra_penalty
                if tentative < g_score.get(nb, float('inf')):
                    # Rotta migliore al vicino: aggiorno e inserisco in heap.
                    came_from[nb] = current
                    g_score[nb] = tentative
                    f = tentative + h(nb, goal)
                    heapq.heappush(open_heap, (f, tentative, nb))

        # Heap esaurita senza raggiungere il goal: non esiste un percorso.
        return None

    # ------------------------------------------------------------------
    # Test "linea diretta" su griglia (per ostacoli e smoothing)
    # ------------------------------------------------------------------

    def line_has_dynamic_obstacle(self, start_xy, end_xy):
        """
        Verifica se la linea retta da ``start_xy`` a ``end_xy`` interseca
        un ostacolo dinamico (es. una porta chiusa).

        Campionamento a 3 step per cella + hitbox 3x3 attorno ad ogni
        campione per essere robusti ai bordi.
        """
        a = self._key(start_xy[0], start_xy[1])
        b = self._key(end_xy[0], end_xy[1])

        dx = b[0] - a[0]
        dy = b[1] - a[1]
        dist = math.hypot(dx, dy)
        if dist == 0:
            # Punto singolo: basta verificare la sua cella.
            return a in self.dynamic_obstacles

        # 3 campioni per cella di distanza (oversampling per non bucare lati).
        steps = int(dist * 3)
        if steps == 0:
            steps = 1

        for i in range(steps + 1):
            t = i / steps
            cx = int(round(a[0] + dx * t))
            cy = int(round(a[1] + dy * t))

            # Hitbox 3x3 attorno al campione: se UNA delle 9 celle attorno
            # e' un ostacolo dinamico, la linea passa "troppo vicino".
            for offset_x in (-1, 0, 1):
                for offset_y in (-1, 0, 1):
                    cell = (cx + offset_x, cy + offset_y)
                    if cell in self.dynamic_obstacles:
                        return True
        return False

    def line_walkable_coords(self, start_xy, end_xy):
        """Wrapper public: verifica se la linea ``start_xy``->``end_xy`` e' calpestabile."""
        a = self._key(start_xy[0], start_xy[1])
        b = self._key(end_xy[0], end_xy[1])
        return self._line_walkable(a, b)

    def _line_walkable(self, a, b):
        """
        Verifica se la linea fra due celle ``a`` e ``b`` (chiavi griglia)
        e' percorribile, considerando una HITBOX A CROCE attorno al bot.

        La hitbox copre 5 celle (centro + 4 cardinali) per evitare che il
        bot strisci contro un muro durante un path "diagonale ammesso".
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
            # Hitbox a "+" (centro + 4 cardinali): tutte e 5 le celle devono
            # essere walkable e non in ostacoli dinamici.
            for offset_x, offset_y in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                cell = (cx + offset_x, cy + offset_y)
                if cell not in self.walkable or cell in self.dynamic_obstacles:
                    return False
        return True

    def _smooth(self, path):
        """
        String-pulling: scarta i waypoint intermedi visibili in linea retta
        dal punto corrente, lasciando un path piu' "dritto" e leggero.

        Idea: dal punto i, cerco il piu' lontano j tale che la linea
        ``path[i] -> path[j]`` sia calpestabile. Saltiamo tutti gli intermedi.
        """
        if len(path) < 3:
            return path
        result = [path[0]]
        i = 0
        while i < len(path) - 1:
            j = len(path) - 1
            # Trova il piu' lontano j visibile da i in linea retta.
            while j > i + 1 and not self._line_walkable(path[i], path[j]):
                j -= 1
            result.append(path[j])
            i = j
        return result

    def astar_straight(self, start_xy, goal_xy):
        """
        Path "fantasma": linea retta che attraversa anche i muri.

        Usato quando il bot e' crewmate morto (``PHASE_GHOST``): in Among Us
        i fantasmi possono passare attraverso le pareti, quindi non serve
        un vero pathfinding. Ritorna semplicemente ``[start, goal]``.

        NB: niente snap a celle walkable; il fantasma puo' andare ovunque.
        """
        sx, sy = float(start_xy[0]), float(start_xy[1])
        gx, gy = float(goal_xy[0]), float(goal_xy[1])
        if sx == gx and sy == gy:
            return [(sx, sy)]
        return [(sx, sy), (gx, gy)]
