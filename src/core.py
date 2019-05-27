import os
import pathlib
from enum import IntFlag


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


class NavStates(IntFlag):
    """Enum to store state of items."""
    IS_DIR = 1
    IS_SELECTED = 2
