"""
TaskPlanner: pianificazione intelligente delle task per Auto-All.

Decide la sequenza ottimale di task da eseguire considerando:
- Priorita' del tipo (vitali sempre per prime)
- Lunghezza (Long > Common > Short, con N/A = sabotaggi piccoli)
- Multi-fase (task con cooldown interno hanno bonus)
- Distanza A* (non euclidea: rispetta i muri/porte)

L'algoritmo e' nearest-neighbor weighted (greedy):
1. Calcola lo score di ogni task candidata dalla posizione corrente
2. Sceglie la task con score piu' alto (prossima)
3. Ripete dalla nuova posizione (centro della task scelta)
4. Costruisce la sequenza completa per la preview

Lo score e' calcolato come:
    score = bonus_vitale + bonus_lunghezza + bonus_multi_fase - alpha * distanza

I pesi sono configurabili (vedi `core/config.py` PLANNER_*).
"""

import math


class TaskPlanner:
    """
    Pianificatore di task per Auto-All.

    Non ha stato proprio: e' un oggetto-utility che lavora sui dati
    forniti (task candidate + posizione attuale + pesi dalla config).
    """

    # Etichette delle lunghezze (lette dal campo 'lunghezza' della task)
    LUNGHEZZE_NOTE = {'Long', 'Common', 'Short', 'N/A'}

    def __init__(self, pathfinder=None):
        """
        :param pathfinder: istanza di `Pathfinder`. Se None o se l'A*
            fallisce, viene usata la distanza euclidea come fallback.
        """
        self.pathfinder = pathfinder
        # Cache distanze A*: (from_x, from_y, to_x, to_y) -> dist
        # Si svuota ad ogni chiamata di `calcola_giro` per evitare
        # di tenere distanze obsolete (la mappa puo' cambiare con
        # le porte chiuse).
        self._dist_cache = {}

    # ============================================================
    # CALCOLO DISTANZA
    # ============================================================

    def distanza(self, x1, y1, x2, y2, use_astar=True):
        """
        Ritorna la distanza fra due punti.

        Se `use_astar=True` e c'e' un pathfinder, calcola la lunghezza
        del percorso A* (rispetta muri/porte). Altrimenti distanza
        euclidea (line of sight, ignora gli ostacoli).

        Risultato cached durante il calcolo di un giro (si svuota
        ad ogni `calcola_giro`).
        """
        # Distanza euclidea: SEMPRE veloce, usata come fallback
        eucl = math.hypot(x2 - x1, y2 - y1)

        if not use_astar or self.pathfinder is None:
            return eucl

        # Quantizza per cache (1 px di tolleranza)
        key = (round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1))
        if key in self._dist_cache:
            return self._dist_cache[key]

        try:
            path = self.pathfinder.astar((x1, y1), (x2, y2),
                                          max_nodes=20000)
        except Exception:
            path = None

        if not path or len(path) < 2:
            # A* fallita (target irraggiungibile o errore):
            # uso euclidea + penalita' del 50% per dis-incentivare
            # la scelta di task che potrebbero non essere raggiungibili.
            result = eucl * 1.5
        else:
            # Somma le distanze fra waypoint consecutivi
            result = 0.0
            for i in range(1, len(path)):
                ax, ay = path[i-1]
                bx, by = path[i]
                result += math.hypot(bx - ax, by - ay)

        self._dist_cache[key] = result
        return result

    # ============================================================
    # SCORE DI UNA TASK
    # ============================================================

    @staticmethod
    def _ha_cooldown_azioni(task):
        """
        True se la task ha almeno un'azione di tipo 'cooldown'
        nelle sue azioni. Indica una task "multi-fase" (es. Submit Scan,
        Inspect Sample, Empty Garbage).

        Nota: e' chi chiama che deve passare la task con le AZIONI
        EFFETTIVE risolte (con ereditarieta'). Qui guardiamo solo se
        c'e' o no.
        """
        azioni = task.get('azioni') or []
        for a in azioni:
            if a.get('tipo') == 'cooldown':
                return True
        return False

    def calcola_score(self, task, distanza, pesi):
        """
        Calcola lo score di una task.

        :param task: dict della task con campi 'vitale', 'lunghezza',
            'azioni' (eventualmente risolte con ereditarieta').
        :param distanza: distanza A* o euclidea dalla posizione corrente.
        :param pesi: dict dei pesi (vedi `core/config.py` PLANNER_*).
        :return: float, piu' alto = priorita' maggiore.
        """
        score = 0.0

        # Bonus vitale (sabotaggi: priorita' assoluta)
        if task.get('vitale'):
            score += pesi.get('vitale', 1000.0)

        # Bonus lunghezza (Long > Common > Short, N/A ha bonus medio)
        lung = task.get('lunghezza', 'Short')
        if lung == 'Long':
            score += pesi.get('long', 30.0)
        elif lung == 'Common':
            score += pesi.get('common', 20.0)
        elif lung == 'N/A':
            score += pesi.get('na', 25.0)
        else:  # Short o sconosciuto
            score += pesi.get('short', 10.0)

        # Bonus multi-fase (task con cooldown interno: Submit Scan,
        # Inspect Sample, ecc.)
        if self._ha_cooldown_azioni(task):
            score += pesi.get('multi_fase', 15.0)

        # Penalita' distanza
        score -= pesi.get('alpha_distanza', 0.5) * distanza

        return score

    # ============================================================
    # CALCOLO GIRO COMPLETO
    # ============================================================

    def calcola_giro(self, bot_pos, candidati, pesi, use_astar=True):
        """
        Calcola la sequenza ottimale (greedy nearest-neighbor weighted).

        :param bot_pos: tuple (x, y) posizione del bot.
        :param candidati: lista di dict task (gia' filtrate, escluse
            done e in cooldown). Ogni task deve avere 'x', 'y', 'nome',
            'vitale', 'lunghezza', 'azioni' (per check cooldown).
        :param pesi: dict pesi (PLANNER_*).
        :param use_astar: se True usa A* per la distanza.
        :return: lista di tuple (task_dict, distanza_da_precedente, score).
            La prima entry ha distanza dalla bot_pos. Lunghezza = len(candidati).
        """
        # Svuoto la cache: ogni giro e' indipendente
        self._dist_cache.clear()

        if not candidati:
            return []

        # Copia per non mutare l'originale
        rimanenti = list(candidati)
        giro = []
        curr_x, curr_y = bot_pos

        while rimanenti:
            best = None
            best_score = -float('inf')
            best_dist = 0.0

            for t in rimanenti:
                d = self.distanza(curr_x, curr_y, t['x'], t['y'],
                                   use_astar=use_astar)
                s = self.calcola_score(t, d, pesi)
                if s > best_score:
                    best_score = s
                    best = t
                    best_dist = d

            if best is None:
                break

            giro.append((best, best_dist, best_score))
            rimanenti.remove(best)
            curr_x, curr_y = best['x'], best['y']

        return giro

    # ============================================================
    # API PUBBLICA PER L'INTEGRAZIONE
    # ============================================================

    def scegli_prossima(self, bot_pos, candidati, pesi, use_astar=True):
        """
        Ritorna SOLO la prossima task da eseguire (la prima del giro).

        Comoda per `_update_auto_all` che vuole solo "qual e' la
        prossima task ora". Equivale a `calcola_giro(...)[0][0]`.

        :return: dict task scelto, oppure None se lista vuota.
        """
        giro = self.calcola_giro(bot_pos, candidati, pesi,
                                  use_astar=use_astar)
        return giro[0][0] if giro else None


# ============================================================
# DEFAULT PESI (usati come fallback)
# ============================================================

PESI_DEFAULT = {
    'vitale':         1000.0,
    'long':           30.0,
    'common':         20.0,
    'na':             25.0,
    'short':          10.0,
    'multi_fase':     15.0,
    'alpha_distanza': 0.5,
}

# Pesi "percorso piu' breve": la distanza domina nettamente sulle
# preferenze di tipo/lunghezza, cosi' il bot va SEMPRE alla task piu'
# vicina e non "salta" task che ha di fianco. Il bonus vitale resta alto
# (i sabotaggi restano prioritari anche in questa modalita').
#
# alpha_distanza molto piu' alto + bonus lunghezza azzerati => l'ordine
# del giro e' praticamente un nearest-neighbor puro (minor strada totale).
PESI_PERCORSO_BREVE = {
    'vitale':         1000.0,
    'long':           0.0,
    'common':         0.0,
    'na':             0.0,
    'short':          0.0,
    'multi_fase':     0.0,
    'alpha_distanza': 10.0,
}


def carica_pesi_da_config(config):
    """
    Costruisce il dict dei pesi leggendo da GPSConfig.

    Se ``GPSConfig.PLANNER_PERCORSO_BREVE`` e' True, ritorna i pesi
    "percorso piu' breve" (nearest-neighbor quasi puro): il bot fa meno
    strada possibile e non salta task vicine. Altrimenti usa i pesi
    "bilanciati" classici (tipo/lunghezza influenzano l'ordine).

    Usato dall'app per passare i pesi al planner senza doverli
    citare uno per uno.
    """
    if getattr(config, 'PLANNER_PERCORSO_BREVE', False):
        return dict(PESI_PERCORSO_BREVE)
    return {
        'vitale':         getattr(config, 'PLANNER_PESO_VITALE', 1000.0),
        'long':           getattr(config, 'PLANNER_PESO_LONG', 30.0),
        'common':         getattr(config, 'PLANNER_PESO_COMMON', 20.0),
        'na':             getattr(config, 'PLANNER_PESO_NA', 25.0),
        'short':          getattr(config, 'PLANNER_PESO_SHORT', 10.0),
        'multi_fase':     getattr(config, 'PLANNER_PESO_MULTI', 15.0),
        'alpha_distanza': getattr(config, 'PLANNER_ALPHA_DIST', 0.5),
    }
