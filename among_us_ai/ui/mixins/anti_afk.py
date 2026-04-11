"""
Anti-AFK: se il bot e' fermo per >N secondi, lancia automaticamente
Auto-All (giro completo delle task).

Funzione attivabile/disattivabile con F3 (o menu Strumenti).

Logica:
- Il bot considera "fermo" quando:
  * Non c'e' un path attivo (`auto_path` vuoto)
  * Non c'e' un processo task in corso (`_task_process` None)
  * Non c'e' un launch task in corso (`_task_launch_arrivo` False)
  * Non e' gia' attiva Auto-All (`auto_execute_all` False)
- Se rimane fermo per piu' di `ANTI_AFK_THRESHOLD_SEC` con F3 ON,
  attiva Auto-All automaticamente.
- Si disattiva subito se l'utente fa qualsiasi click manuale o
  cambia stato (la pressione di F3 funziona come toggle istantaneo).

Mixin separato per modularita': non sporca il resto del codice.
"""

from ._imports import *
import time as _time


# Configurazione default (override-able)
ANTI_AFK_THRESHOLD_SEC = 30.0  # se fermo per >30s, parte


class AntiAfkMixin:
    """Mixin per la funzione anti-fermo (toggle F3)."""

    # ============================================================
    # TOGGLE / SETUP
    # ============================================================

    def _toggle_anti_afk(self):
        """Attiva/disattiva la modalita' anti-AFK (callback F3)."""
        cur = getattr(self, '_anti_afk_enabled', False)
        self._anti_afk_enabled = not cur
        self._anti_afk_idle_since = _time.time()
        # Messaggio di stato mostrato all'utente nel pannello
        if self._anti_afk_enabled:
            self.auto_status_msg = "Anti-AFK ATTIVO (F3 per disattivare)"
            print("[AntiAFK] Attivato", flush=True)
        else:
            self.auto_status_msg = "Anti-AFK disattivato"
            print("[AntiAFK] Disattivato", flush=True)

    # ============================================================
    # LOOP DI CONTROLLO
    # ============================================================

    def _update_anti_afk(self, dt):
        """
        Chiamato ad ogni frame. Se anti-AFK e' attivo e il bot e'
        fermo da abbastanza tempo, lancia Auto-All.
        """
        if not getattr(self, '_anti_afk_enabled', False):
            return

        threshold = getattr(GPSConfig, 'ANTI_AFK_THRESHOLD_SEC',
                            ANTI_AFK_THRESHOLD_SEC)
        now = _time.time()

        # Considero il bot "occupato" se:
        # - sta navigando (path attivo)
        # - sta eseguendo una task (subprocess vivo)
        # - sta arrivando a una task (launch in corso)
        # - Auto-All e' gia' attivo
        busy = (
            (getattr(self, 'auto_path', None) and
             len(self.auto_path) > 0) or
            (getattr(self, '_task_process', None) is not None) or
            getattr(self, '_task_launch_arrivo', False) or
            getattr(self, 'auto_execute_all', False)
        )

        if busy:
            # Resetto il timer: ora e' occupato
            self._anti_afk_idle_since = now
            return

        # Non e' occupato: misuro da quanto tempo
        idle_since = getattr(self, '_anti_afk_idle_since', now)
        idle_sec = now - idle_since
        if idle_sec < threshold:
            return  # ancora sotto soglia

        # Trigger: il bot e' fermo abbastanza -> lancia Auto-All
        print(f"[AntiAFK] Bot fermo da {idle_sec:.0f}s, lancio Auto-All",
              flush=True)
        # Resetto il timer per evitare ri-trigger immediati
        self._anti_afk_idle_since = now
        # Messaggio di stato mostrato all'utente nel pannello
        self.auto_status_msg = (
            f"Anti-AFK: fermo da {idle_sec:.0f}s, avvio giro task")
        # Attivo Auto-All come se l'utente avesse premuto il bottone
        try:
            self._toggle_auto_all()
        except Exception as e:
            print(f"[AntiAFK] Errore avvio Auto-All: {e}", flush=True)
