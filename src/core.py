import os
import pathlib
from enum import IntFlag
from PyQt5 import QtWidgets
# from .helper import logger


class Nav:
    """Data store to hold application state."""
    app = str(pathlib.Path(__file__).resolve())
    app_dir = os.path.dirname(app)
    app_data = f"{app_dir}{os.sep}..{os.sep}appdata"
    copier = os.path.join(app_dir, "navcopier.py")
    copy_jobs = 0
    conf_file = os.path.join(str(pathlib.Path.home()), "navgator.json")

    conf = {
        "panes": {"total": 4, "active": "Pane 1", },
        "window": {"main_tree": True, "statusbar": True},
        "history_without_dupes": True,
        "sort_folders_first": True,
        "watch_all_tabs": True,
        "shortcuts": {"back": "backspace", },
        "colors": {"bcbar": {"active": "blue", "inactive": "green"}},
    }

    @classmethod
    def getsizes(cls, k, min, defaults):
        """Helper function to provide sizes for splitter elements."""
        try:
            elem = len(defaults)
            for i in range(elem):
                if cls.conf["dims"][k][i] < min[i]:
                    cls.conf["dims"][k] = defaults
                    break
        except Exception:
            cls.conf["dims"][k] = defaults
        return cls.conf["dims"][k]

    @classmethod
    def build_menu(cls, parent, d: dict, menu: QtWidgets.QMainWindow.menuBar):
        """Build up the menu recursively."""
        if isinstance(d, list):
            for v in d:
                if isinstance(v, QtWidgets.QAction):
                    menu.addAction(v)
                elif isinstance(v, dict):
                    if "sm" in v:
                        m2 = menu.addMenu(v["caption"])
                        cls.build_menu(parent, v["sm"], m2)
        elif isinstance(d, dict):
            for k, v in d.items():
                if "sm" in v:
                    m2 = menu.addMenu(v["caption"])
                    cls.build_menu(parent, v["sm"], m2)


class NavStates(IntFlag):
    """Enum to store state of items."""
    IS_DIR = 1
    IS_SELECTED = 2


class NavView(IntFlag):
    """Enum for different Views"""
    Details = 1
    List = 2
    Icons = 3
    Thumbnails = 4
    # SmallIcons = 3
    # MediumIcons = 4
    # LargeIcons = 5
    # XLIcons = 6
    # SmallThumbs = 7
    # MediumThumbs = 8
    # LargeThumbs = 9
    # XLThumbs = 10


class NavSize(IntFlag):
    Tiny = 1
    Small = 2
    Medium = 3
    Large = 4
    XL = 5