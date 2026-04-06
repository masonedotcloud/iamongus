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
    EV_VENT_USE, EV_NEAR_BODY, EV_STOP
)


# Default weights (modificabili da UI in futuro)
W_VENT_USE         = 35.0   # +per ogni vent usata (teletrasporto rilevato)
W_NEAR_BODY        = 12.0   # +per essere visto vicino a un cadavere
W_TASK_INFERITA    = -8.0   # -per task inferita (scagiona)
W_FOLLOWING_BOT    = 0.30   # +per secondo speso vicino al bot
W_FOLLOWING_CAP    = 18.0   # max contributo dal follow score
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
      * Vicinanza a cadaveri
      * Follow del bot
      * Nessuna task vista
    - Indicatori NEGATIVI (abbassano il sospetto):
      * Task inferite (chi fa task lavora -> probabile crewmate)
    """

    def __init__(self,
                 w_vent_use=W_VENT_USE,
                 w_near_body=W_NEAR_BODY,
                 w_task=W_TASK_INFERITA,
                 w_following=W_FOLLOWING_BOT,
                 w_following_cap=W_FOLLOWING_CAP,
                 w_no_tasks=W_NO_TASKS_SEEN,
                 w_no_tasks_time=W_NO_TASKS_TIME):
        self.w_vent_use = w_vent_use
        self.w_near_body = w_near_body
        self.w_task = w_task
        self.w_following = w_following
        self.w_following_cap = w_following_cap
        self.w_no_tasks = w_no_tasks
        self.w_no_tasks_time = w_no_tasks_time

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

        # 2. Vicinanza a cadaveri
        near_body = activity.count_events(player.name, EV_NEAR_BODY)
        if near_body > 0:
            contrib = near_body * self.w_near_body
            factors['near_body'] = (near_body, contrib)
            score += contrib

        # 3. Task inferite (negativo: scagiona)
        task_count = task_inf.task_count(player.name)
        if task_count > 0:
            contrib = task_count * self.w_task
            factors['tasks_done'] = (task_count, contrib)
            score += contrib  # contrib e' negativo

        # 4. Follow del bot
        follow_sec = proximity.follow_score(player.name)
        if follow_sec > 0:
            contrib = min(follow_sec * self.w_following, self.w_following_cap)
            factors['following_me'] = (round(follow_sec, 1), contrib)
            score += contrib

        # 5. Player non visto fare task da molto (sospetto)
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
        score = max(0.0, min(100.0, score))

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
