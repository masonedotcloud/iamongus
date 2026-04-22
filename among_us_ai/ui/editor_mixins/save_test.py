"""
Salva la sequenza e lancia il test live in un thread separato.

Mixin di TaskActionEditor.
"""

from ._imports import *


class EditorSaveTestMixin:
    """Mixin per le azioni "Salva" e "Test" di :class:`TaskActionEditor`."""

    def _salva_e_chiudi(self, *_):
        """Salva la sequenza azioni nel file di esecuzione della task e chiude l'editor."""
        if self.id_task is None:
            self.chiudi()
            return
        self.task_mgr.imposta_azioni(self.id_task, self.azioni)
        if self.on_save_cb:
            try:
                self.on_save_cb(self.id_task)
            except Exception as e:
                print(f"[TaskActionEditor] on_save_cb error: {e}")
        self.chiudi()

    def _avvia_test(self, *_):
        """
        Lancia la sequenza di azioni in modalita' TEST in un thread daemon.

        In test mode il dispatcher esegue TUTTE le azioni (non solo il
        chunk corrente). Lo stop si richiede col tasto F4/END (vedi
        ``stop_flag``).
        """
        stop_flag.requested = False
        if not _WIN_OK:
            self._imposta_istruzioni(
                "pyautogui/win32 non disponibili.", (255, 100, 100))
            return
        if not self.azioni:
            self._imposta_istruzioni(
                "Nessuna azione da testare.", (255, 100, 100))
            return
        threading.Thread(target=self._esegui_test_thread, daemon=True).start()

    def _esegui_test_thread(self):
        """
        Body del thread di test: porta la finestra del gioco in foreground,
        attende ~500ms per dare al gioco il tempo di "ricevere il focus",
        poi esegue la sequenza completa via :func:`esegui_azioni` con
        ``is_test=True``.
        """
        nome_finestra = dpg.get_value(self.TAG_IN_WIN_NAME)
        hwnd = win32gui.FindWindow(None, nome_finestra)
        if not hwnd:
            return
        try:
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.5)
        except Exception:
            pass
        esegui_azioni(self.azioni, hwnd, is_test=True)
