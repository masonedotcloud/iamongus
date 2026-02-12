"""Entry point quando si lancia ``python -m among_us_ai``."""

from .ui import GPSVisualizerPro


def main():
    """Entry point principale del programma."""
    app = GPSVisualizerPro()
    app.run()


if __name__ == "__main__":
    main()
