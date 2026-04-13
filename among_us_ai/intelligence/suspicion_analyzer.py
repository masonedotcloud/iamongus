"""
SuspicionAnalyzer: calcola la "sospettosita'" di ciascun player.

Combina i dati di:
- ActivityDetector (vent uses, stop, near body, ecc.)
- ProximityAnalyzer (chi mi segue di piu')
- TaskInference (chi ha fatto piu' task)
- PlayerTracker (movimento, posizioni)

Output: per ogni player, uno score 0-100% di probabilita' impostore,
con i fattori che hanno contribuito (per spiegare il giudizio).

Pesi configurabili tramite costruttore; default sono valori ragionevoli.
"""

from .activity_detector import (
    EV_VENT_USE, EV_NEAR_BODY, EV_SUDDEN_DISAPPEAR, EV_STOP
)


# Default weights (modificabili da UI in futuro)
W_VENT_USE         = 35.0   # +per ogni vent usata (teletrasporto rilevato)
W_SUDDEN_DISAPPEAR = 25.0   # +per sparizione improvvisa dal raggio di vista
W_NEAR_BODY        = 12.0   # +per essere visto vicino a un cadavere
W_TASK_INFERITA    = -8.0   # -per task inferita (scagiona)
W_FOLLOWING_BOT    = 0.30   # +per secondo speso vicino al bot
W_FOLLOWING_CAP    = 18.0   # max contributo dal follow score
W_ALONE_WITH_SAFE  = -0.5   # -per secondo passato 1v1 vivi (scagiona)
W_ALONE_WITH_CAP   = -20.0  # cap negativo (max bonus dato dal 1v1)
W_NO_TASKS_SEEN    = 8.0    # +se molto tempo senza task viste
W_NO_TASKS_TIME    = 60.0   # soglia di secondi senza task


class SuspicionScore:
    """Risultato del calcolo di sospettosita' per un player."""

    __slots__ = ('player_name', 'score', 'factors', 'verdict')

    def __init__(self, player_name, score, factors, verdict):
        self.player_name = player_name
        self.score = score        # 0-100
        self.factors = factors    # dict factor_name -> contributo
        self.verdict = verdict    # 'safe' | 'sus' | 'super_sus'

    def __repr__(self):
        return (f"<Suspicion {self.player_name} {self.score:.0f}% "
                f"[{self.verdict}]>")


class SuspicionAnalyzer:
    """
    Calcola lo score di sospettosita' per ogni player conosciuto.

    Lo score combina indicatori positivi e negativi:
    - Indicatori POSITIVI (alzano il sospetto):
      * Vent usate (teletrasporto rilevato fra due osservazioni)
      * Sparizione improvvisa dal raggio di vista
      * Vicinanza a cadaveri
      * Follow del bot
      * Nessuna task vista
    - Indicatori NEGATIVI (abbassano il sospetto):
      * Task inferite (chi fa task lavora -> probabile crewmate)
      * Tempo passato 1v1 col bot vivo (avrebbe killato se fosse impostore)
    """

    def __init__(self,
                 w_vent_use=W_VENT_USE,
                 w_sudden_disappear=W_SUDDEN_DISAPPEAR,
                 w_near_body=W_NEAR_BODY,
                 w_task=W_TASK_INFERITA,
                 w_following=W_FOLLOWING_BOT,
                 w_following_cap=W_FOLLOWING_CAP,
                 w_alone_with=W_ALONE_WITH_SAFE,
                 w_alone_with_cap=W_ALONE_WITH_CAP,
                 w_no_tasks=W_NO_TASKS_SEEN,
                 w_no_tasks_time=W_NO_TASKS_TIME,
                 smoothing=0.5):
        self.w_vent_use = w_vent_use
        self.w_sudden_disappear = w_sudden_disappear
        self.w_near_body = w_near_body
        self.w_task = w_task
        self.w_following = w_following
        self.w_following_cap = w_following_cap
        self.w_alone_with = w_alone_with
        self.w_alone_with_cap = w_alone_with_cap
        self.w_no_tasks = w_no_tasks
        self.w_no_tasks_time = w_no_tasks_time

        # Smoothing: il nuovo score e' una media pesata fra quello vecchio
        # e quello appena calcolato:
        #   smoothed = old * smoothing + new * (1 - smoothing)
        # smoothing=0   -> nessun smoothing (vecchio comportamento)
        # smoothing=0.5 -> dolce: lo score si muove ma senza saltare
        # smoothing=0.9 -> molto pigro
        self.smoothing = smoothing
        # Cache degli score precedenti per smoothing
        self._last_scores = {}

    def analyze(self, player, activity, proximity, task_inf, now=None):
        """
        Calcola il SuspicionScore per un singolo player.

        :param player: PlayerInfo
        :param activity: ActivityDetector
        :param proximity: ProximityAnalyzer
        :param task_inf: TaskInference
        :param now: timestamp corrente
        :return: SuspicionScore
        """
        factors = {}
        score = 0.0

        # 1. Vent usate
        vents = activity.count_events(player.name, EV_VENT_USE)
        if vents > 0:
            contrib = vents * self.w_vent_use
            factors['vent_use'] = (vents, contrib)
            score += contrib

        # 2. Sparizione improvvisa dal raggio di vista
        sudden = activity.count_events(player.name, EV_SUDDEN_DISAPPEAR)
        if sudden > 0:
            contrib = sudden * self.w_sudden_disappear
            factors['sudden_disappear'] = (sudden, contrib)
            score += contrib

        # 3. Vicinanza a cadaveri
        near_body = activity.count_events(player.name, EV_NEAR_BODY)
        if near_body > 0:
            contrib = near_body * self.w_near_body
            factors['near_body'] = (near_body, contrib)
            score += contrib

        # 4. Task inferite (negativo: scagiona)
        task_count = task_inf.task_count(player.name)
        if task_count > 0:
            contrib = task_count * self.w_task
            factors['tasks_done'] = (task_count, contrib)
            score += contrib  # contrib e' negativo

        # 5. Follow del bot
        follow_sec = proximity.follow_score(player.name)
        if follow_sec > 0:
            contrib = min(follow_sec * self.w_following, self.w_following_cap)
            factors['following_me'] = (round(follow_sec, 1), contrib)
            score += contrib

        # 6. 1v1 sicuro (negativo: scagiona)
        # Per ogni secondo passato 1v1 col bot SENZA morire, abbassa
        # lo score (avrebbe killato se fosse impostore).
        alone_sec = proximity.alone_with_safe_score(player.name)
        if alone_sec > 0:
            contrib = max(alone_sec * self.w_alone_with,
                          self.w_alone_with_cap)
            factors['alone_with_safe'] = (round(alone_sec, 1), contrib)
            score += contrib  # contrib negativo

        # 7. Player non visto fare task da molto (sospetto)
        if (task_count == 0 and player.last_snapshot
                and player._last_observation_t is not None):
            # Quanto tempo dal primo avvistamento?
            if len(player.history) > 0:
                age = player.history[-1].t - player.history[0].t
                if age > self.w_no_tasks_time:
                    contrib = self.w_no_tasks
                    factors['no_tasks_seen'] = (round(age, 0), contrib)
                    score += contrib

        # Clampa fra 0 e 100
        # Clamp grezzo fra 0 e 100
        score = max(0.0, min(100.0, score))

        # === SMOOTHING ===
        # Il nuovo score e' una media pesata fra quello precedente e quello
        # appena calcolato. Cosi' eventi che si "auto-rigenerano" o
        # statistiche che oscillano (es. follow score) non causano salti
        # bruschi della barra di sospettosita'.
        if self.smoothing > 0.0:
            old = self._last_scores.get(player.name)
            if old is not None:
                score = old * self.smoothing + score * (1.0 - self.smoothing)
            self._last_scores[player.name] = score

        # Verdetto qualitativo
        if score >= 60:
            verdict = 'super_sus'
        elif score >= 30:
            verdict = 'sus'
        else:
            verdict = 'safe'

        return SuspicionScore(player.name, score, factors, verdict)

    def analyze_all(self, tracker, activity, proximity, task_inf, now=None):
        """Score per tutti i player conosciuti."""
        result = []
        for player in tracker.all_players():
            if player.is_dead:
                continue
            s = self.analyze(player, activity, proximity, task_inf, now)
            result.append(s)
        # Ordina per score decrescente
        result.sort(key=lambda s: s.score, reverse=True)
        return result


def build_avoidance_cost_map(scores, tracker,
                              min_score=40.0,
                              radius=3.0,
                              max_penalty=15.0,
                              now=None):
    """
    Costruisce una `extra_penalties` da passare a `pathfinder.astar()`
    per far evitare al bot le celle vicine ai player sospetti.

    Logica "sorpasso": le celle vicine al sospetto vengono penalizzate
    in modo decrescente con la distanza. Cosi' A* preferisce passare
    accanto (non sopra) il player, come una macchina che fa un sorpasso.

    :param scores: lista di SuspicionScore (da `analyze_all()`)
    :param tracker: PlayerTracker (per recuperare posizione del player)
    :param min_score: solo player con score >= questa soglia sono evitati
    :param radius: raggio (in unita') intorno al player da penalizzare
    :param max_penalty: penalita' al centro (cella del player)
    :param now: timestamp
    :return: dict {(cx, cy): penalty}
    """
    import math
    import time as _time
    if now is None:
        now = _time.time()
    cost = {}
    for sc in scores:
        if sc.score < min_score:
            continue
        p = tracker.get(sc.player_name)
        if p is None or not p.last_snapshot:
            continue
        # Solo player visti di recente (entro 5s)
        if p.seconds_since_last_seen(now) > 5.0:
            continue
        cx0, cy0 = int(round(p.last_snapshot.x)), int(round(p.last_snapshot.y))
        r = int(math.ceil(radius))
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                d = math.hypot(dx, dy)
                if d > radius:
                    continue
                # Penalita' inversa alla distanza: max al centro, 0 al bordo
                penalty = max_penalty * (1.0 - d / radius)
                # Scala anche con quanto e' sospetto (super_sus pesa piu')
                penalty *= sc.score / 100.0
                cell = (cx0 + dx, cy0 + dy)
                # Se la cella ha gia' una penalita' (sovrapposizione di
                # piu' sospetti), tieni la MAGGIORE.
                if penalty > cost.get(cell, 0.0):
                    cost[cell] = penalty
    return cost
