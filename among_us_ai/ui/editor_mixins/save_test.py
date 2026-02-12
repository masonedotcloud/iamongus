"""
Salva la sequenza e lancia il test live in un thread separato.

Mixin di TaskActionEditor.
"""

from ._imports import *


class EditorSaveTestMixin:
    """Mixin con i metodi di editor save test di GPSVisualizerPro."""
    def _salva_e_chiudi(self, *_):
        """Salva su file e chiudi."""
        if self.id_task is None:
            self.chiudi(); return
        # Salva le azioni nel file di esecuzione della task
        self.task_mgr.imposta_azioni(self.id_task, self.azioni)
        if self.on_save_cb:
            try:
                self.on_save_cb(self.id_task)
            except Exception as e:
                print(f"[TaskActionEditor] on_save_cb error: {e}")
        self.chiudi()

    def _avvia_test(self, *_):
        """Avvia test."""
        # Flag globale di stop (True quando F4 o FINE viene premuto)
        stop_flag.requested = False
        # Senza ambiente Windows non si fa nulla
        if not _WIN_OK:
            self._imposta_istruzioni("pyautogui/win32 non disponibili.", (255, 100, 100))
            return
        if not self.azioni:
            self._imposta_istruzioni("Nessuna azione da testare.", (255, 100, 100))
            return
        # Avvia un thread separato
        threading.Thread(target=self._esegui_test_thread, daemon=True).start()

    def _esegui_test_thread(self):
        """Esegue test thread."""
        nome_finestra = dpg.get_value(self.TAG_IN_WIN_NAME)
        # Cerca la finestra del gioco per nome
        hwnd = win32gui.FindWindow(None, nome_finestra)
        if not hwnd:
            return
        try:
            # Porta la finestra del gioco in primo piano
            win32gui.SetForegroundWindow(hwnd)
            # Pausa il thread per il tempo specificato (secondi)
            time.sleep(0.5)
        except Exception:
            pass
        esegui_azioni(self.azioni, hwnd, is_test=True)
