"""Entry point quando si lancia ``python -m among_us_gps``."""

from .ui import GPSVisualizerPro


def main():
    app = GPSVisualizerPro()
    app.run()


if __name__ == "__main__":
    main()
