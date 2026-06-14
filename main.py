import argparse
import sys

from PyQt6.QtWidgets import QApplication

from main_window import MainWindow


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--player-name", default="", dest="player_name")
    args, qt_argv = parser.parse_known_args()

    app = QApplication([sys.argv[0]] + qt_argv)
    app.setApplicationName("RPG Hex Map Tool")
    window = MainWindow(player_name=args.player_name)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
