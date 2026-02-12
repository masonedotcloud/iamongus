"""
Entry point comodo: lancia ``python main.py`` dalla cartella del progetto.

Equivalente a ``python -m among_us_ai``: importa ``GPSVisualizerPro`` e
avvia il main loop di DearPyGui.

Per eseguire il bot e' necessario che la cartella di lavoro contenga i file
di dati (mappa, zone, POI, task_registrate, modelli .pt). Vedi README.md.
"""

from among_us_ai.ui import GPSVisualizerPro


def main():
    app = GPSVisualizerPro()
    app.run()


if __name__ == "__main__":
    main()
