#!/bin/python3

import json
import pathlib
import sys
import subprocess
from PyQt5 import QtGui, QtCore, QtWidgets
from .core import Nav
from .custom import NavTree
from .helper import logger, deep_merge
from .navwatcher import NavWatcher
from .panes import NavPane
from .pub import Pub
from .settings import NavSettings


class NavApp(QtWidgets.QApplication):
    """Initialize application."""
    def __init__(self, args):
        super().__init__(args)
        self.window = Navgator(args)
        sys.exit(self.exec_())


class Navgator(QtWidgets.QMainWindow):
    update_sb = QtCore.pyqtSignal(str, int)

    def __init__(self, *args):
        super().__init__()
        self.title = 'Navgator'
        self.load_settings()
        threadpool = QtCore.QThreadPool()
        threadpool.setMaxThreadCount(1)
        try:
            x, y, w, h = Nav.conf["dims"]["main"][:4]
        except Exception:
            screensize = QtWidgets.QDesktopWidget().screenGeometry(-1)
            if "dims" not in Nav.conf:
                Nav.conf["dims"] = {}
            Nav.conf["dims"]["main"] = [0, 0, screensize.width(),
                                        screensize.height()]
            x, y, w, h = Nav.conf["dims"]["main"]
        self.setGeometry(x, y, w, h)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.sb = self.statusBar()
        self.update_sb.connect(self.status_bar_update)
        self.main_widget = QtWidgets.QWidget(self)
        self.box = QtWidgets.QHBoxLayout(self.main_widget)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.splitter1 = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.splitter2 = QtWidgets.QSplitter(QtCore.Qt.Vertical)

        self.tree = NavTree()
        self.splitter.insertWidget(0, self.tree)
        self.tree.clicked[QtCore.QModelIndex].connect(self.tree_navigate)

        if not Nav.conf["window"]["main_tree"]:
            self.tree.hide()

        self.panes = []
        self.active_pane = None
        for i in range(1, Nav.conf["panes"]["total"] + 1):
            name = f"Pane {i}"
            try:
                p = NavPane(name, Nav.conf["panes"][name])
            except KeyError:
                Nav.conf["panes"][name] = {
                    'visible': True,
                    'tabs': {
                        'total': 1,
                        '0': {'location': str(pathlib.Path.home())},
                        'active': 0
                    }
                }
                p = NavPane(name, Nav.conf["panes"][name])
            p.activated.connect(self.active_pane_changed)

            if i % 2 != 0:
                self.splitter1.addWidget(p)
            else:
                self.splitter2.addWidget(p)
            if not Nav.conf["panes"][name]["visible"]:
                p.hide()
            self.panes.append(p)

            if Nav.conf["panes"]["active"] == name:
                self.active_pane = p
                p.tabbar.setStyleSheet('''
                    QTabBar::tab:selected {background: blue;}
                    NavBreadCrumbsBar{background-color: blue;}
                    QTabWidget::pane {border: 0px;}
                    ''')
                self.setWindowTitle(f"{self.title} - {name}")
            else:
                p.tabbar.setStyleSheet(
                    '''QTabBar::tab:selected {background: green;}
                    NavBreadCrumbsBar{background-color: green;}
                    QTabWidget::pane {border: 0px;}
                    ''')
        self.splitter.addWidget(self.splitter1)
        self.splitter.addWidget(self.splitter2)
        self.splitter.setSizes(
            Nav.getsizes("tp", [50, 50, 50], [w*0.1, w*0.45, w*0.45]))
        self.splitter1.setSizes(Nav.getsizes("p12", [50, 50], [h*0.5, h*0.5]))
        self.splitter2.setSizes(Nav.getsizes("p23", [50, 50], [h*0.5, h*0.5]))

        # delay creating menubar so that we can hook up to panes and tabs
        self.menubar = self.menuBar()
        self.create_menu()
        self.create_toolbar()
        self.box.addWidget(self.splitter)
        self.setCentralWidget(self.main_widget)
        self.show()
        # self.mainThreadID = QtCore.QThread.currentThread().currentThreadId()
        self.active_pane.tabbar.currentWidget().tab.setFocus()
        if Nav.conf["window"]["statusbar"]:
            Pub.subscribe("App", self.update_status_bar)
            self.sb.show()
            self.sb.showMessage("Ready", 2000)
        else:
            self.sb.hide()

    def create_toolbar(self):
        """Creates a toolbar."""
        toolbar = self.addToolBar("Main")
        back = QtWidgets.QAction(
                self.style().standardIcon(QtWidgets.QStyle.SP_ArrowBack),
                "Back", self)
        back.triggered.connect(
            lambda: self.active_pane.tabbar.currentWidget().tab.go_back())
        toolbar.addAction(back)
        forward = QtWidgets.QAction(
                self.style().standardIcon(QtWidgets.QStyle.SP_ArrowForward),
                "Forward", self)
        forward.triggered.connect(
            lambda: self.active_pane.tabbar.currentWidget().tab.go_forward())
        toolbar.addAction(forward)

    def create_menu(self):
        """Creates menu recursively."""
        # Python 3.7 tracks insertion order
        items = {
            "file": {"caption": "&File"},
            "edit": {"caption": "&Edit"},
            "tabs": {"caption": "&Tabs"},
            "user": {"caption": "&User", "sm": {}},
            "window": {"caption": "&Window", "sm": {}}
        }

        if "user_commands" not in Nav.conf:
            del items["user"]

        items["file"]["sm"] = {
            "exit": {
                "caption": "E&xit",
                "icon": QtGui.QIcon.fromTheme('file-exit'),
                "shortcut": "Ctrl+Q",
                "triggered": self.close,
                "statusTip": "Exit application",
            }
        }

        items["edit"]["sm"] = {
            "rename": {
                "caption": "&Rename",
                "shortcut": "F2",
                "triggered": (lambda: self.active_pane.tabbar.
                              currentWidget().tab.rename_file()),
            },
            "cut": {
                "caption": "C&ut",
                "shortcut": "Ctrl+X",
                "triggered": (lambda: self.active_pane.tabbar.
                              currentWidget().tab.copy(cut=True)),
            },
            "copy": {
                "caption": "&Copy",
                "shortcut": "Ctrl+C",
                "triggered": (lambda: self.active_pane.tabbar.
                              currentWidget().tab.copy()),
            },
            "paste": {
                "caption": "&Paste",
                "shortcut": "Ctrl+V",
                "triggered": (lambda: self.active_pane.tabbar.
                              currentWidget().tab.paste()),
            },
            "trash": {
                "caption": "&Trash",
                "shortcut": "del",
                "triggered": (lambda: self.active_pane.tabbar.
                              currentWidget().tab.trash()),
            },
            "delete": {
                "caption": "&Delete",
                "shortcut": "Shift+del",
                "triggered": (lambda: self.active_pane.tabbar.
                              currentWidget().tab.delete()),
            },
            "del_dir_up": {
                "caption": "Delete Dir Up",
                "shortcut": "Ctrl+del",
                "triggered": (lambda: self.active_pane.tabbar.
                              currentWidget().tab.del_dir_up()),
            },
            "new_file": {
                "caption": "&New File",
                "shortcut": "Ctrl+N",
                "triggered": (lambda: self.active_pane.tabbar.
                              currentWidget().tab.new_file("file")),
                "icon": self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
            },
            "new_folder": {
                "caption": "New &Folder",
                "shortcut": "Ctrl+Shift+N",
                "triggered": (lambda: self.active_pane.tabbar.
                              currentWidget().tab.new_file("folder")),
                "icon": self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon),
            },
            "selections": {
                "caption": "&Selections",
                "sm": {
                    "select_all": {
                        "caption": "&Select All",
                        "shortcut": "Ctrl+A",
                        "triggered": (lambda: self.active_pane.tabbar.
                                      currentWidget().tab.selectColumn(0)),
                    },
                    "clear_all": {
                        "caption": "&Clear All",
                        "shortcut": "Ctrl+Shift+A",
                        "triggered": (lambda: self.active_pane.tabbar.
                                      currentWidget().tab.clearSelection()),
                    },
                    "invert": {
                        "caption": "&Invert Select",
                        "shortcut": "Ctrl+Shift+I",
                        "triggered": (lambda: self.active_pane.tabbar.
                                      currentWidget().tab.invert_selection()),
                    }
                }
            }
        }

        items["tabs"]["sm"] = {
            "new_tab": {
                "caption": "&New Tab",
                "shortcut": "Ctrl+T",
                "triggered": (lambda: self.active_pane.new_tab()),
            },
            "close_tab": {
                "caption": "&Close Tab",
                "shortcut": "Ctrl+W",
                "triggered": (lambda: self.active_pane.close_tab(
                    self.active_pane.tabbar.currentIndex())),
            },
            "rename_tab": {
                "caption": "&Rename Tab",
                "shortcut": "Ctrl+E",
                "triggered": (lambda: self.active_pane.rename_tab(
                    self.active_pane.tabbar.currentIndex())),
            },
            "next_tab": {
                "caption": "Ne&xt Tab",
                "shortcut": "Ctrl+Tab",
                "triggered": (lambda: self.active_pane.select_tab("next")),
            },
            "prev_tab": {
                "caption": "Pre&vious Tab",
                "shortcut": "Ctrl+Shift+Tab",
                "triggered": (lambda: self.active_pane.select_tab("prev")),
            },
            "close_other_tabs": {
                "caption": "Close &Other Tabs",
                "triggered": (lambda: self.active_pane.close_other_tabs()),
            },
            "close_left_tabs": {
                "caption": "Close &Left Tabs",
                "triggered": (lambda: self.active_pane.close_left_tabs()),
            },
            "close_right_tabs": {
                "caption": "Close &Right Tabs",
                "triggered": (lambda: self.active_pane.close_right_tabs()),
            },
        }
        pane_count = Nav.conf["panes"]["total"]
        if pane_count > 4:
            pane_count = 4
        items2 = {f"Pane {i}": None for i in range(1, pane_count + 1)}
        items["window"]["sm"] = {
            "maintree": {
                "caption": "&Main Tree",
                "checkable": True,
                "checked": Nav.conf["window"]["main_tree"],
                "shortcut": "F8",
                "triggered": self.tree_toggle,
                "icon": self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
            },
            **items2,
            "settings": {
                "caption": "&Settings",
                "shortcut": "F9",
                "triggered": self.show_settings,
            },
            "statusbar": {
                "caption": "&Status Bar",
                "checkable": True,
                "checked": Nav.conf["window"]["statusbar"],
                "triggered": self.statusbar_toggle,
            }
        }

        for i in range(1, pane_count + 1):
            name = f"Pane {i}"
            items["window"]["sm"][name] = {
                "caption": f"Pane &{i}",
                "checkable": True,
                "checked": Nav.conf["panes"][name]["visible"],
                "triggered": (lambda a=0, ind=i, name1=name: self.pane_toggle(
                              ind, name1)),
            }

        self.expose_shortcuts(items)
        self.build_menu(items, self.menubar)
        del items

        for m in self.menubar.findChildren(QtWidgets.QMenu):
            if m.title() == "&User":
                self.create_user_menu(m)
                break

    def expose_shortcuts(self, d: dict):
        """Expose shortcuts for customising them."""
        for k, v in d.items():
            if isinstance(v, dict):
                if "shortcut" not in v:
                    self.expose_shortcuts(v)
                else:
                    try:
                        Nav.conf["shortcuts"][k] = v["shortcut"]
                    except KeyError:
                        pass

    def build_menu(self, d: dict, menu: QtWidgets.QMainWindow.menuBar):
        """Build up the menu recursively."""
        for k, v in d.items():
            if "sm" in v:
                m2 = menu.addMenu(v["caption"])
                self.build_menu(v["sm"], m2)
            else:
                cap = v.pop("caption")
                act = QtWidgets.QAction(cap, self, **v)
                if k in Nav.conf["shortcuts"]:
                    act.setShortcut(Nav.conf["shortcuts"][k])
                menu.addAction(act)

    def create_user_menu(self, user_menu: QtWidgets.QMainWindow.menuBar):
        """Builds up the user menu based on provided user commands."""
        for k, v in Nav.conf["user_commands"].items():
            user_act = QtWidgets.QAction(k, self)
            if "shortcut" in Nav.conf["user_commands"][k]:
                user_act.setShortcut(Nav.conf["user_commands"][k]["shortcut"])
            command = Nav.conf["user_commands"][k]["command"]
            try:
                args = Nav.conf["user_commands"][k]["args"]
            except (KeyError, TypeError):
                args = None
            user_act.triggered.connect(
                lambda a=0, command=command, args=args:
                self.invoke_user_command(command, args))
            user_menu.addAction(user_act)

    def invoke_user_command(self, command: str, args: str):
        """Invokes customised user commands."""
        if args == "%F":
            item = " ".join(self.active_pane.tabbar.currentWidget().tab.
                            get_selected_items())
        else:
            item = self.active_pane.location
        # logger.debug(f"Command: {command} Args:{item}")
        subprocess.Popen(f'{command} {item}', shell=True)

    def pane_toggle(self, ind: int, item: str):
        """Toggle pane visibility"""
        if Nav.conf["panes"][item]["visible"]:
            # Check if atleast one other visible pane
            for p in self.panes:
                if p != self.panes[ind-1] and p.isVisible():
                    # if hiding active pane, activate another pane
                    if self.panes[ind-1] is self.active_pane:
                        self.active_pane_changed(p)
                    self.panes[ind-1].hide()
                    self.panes[ind-1].set_visibility(False)
                    Nav.conf["panes"][item]["visible"] = False
                    return
            Nav.conf["panes"][item]["visible"] = True
            self.sender().setChecked(True)
            logger.warning(f"Can't hide last visible pane.")
            Pub.notify("App", f"{item}: Can't hide last visible pane.")
            return False
        else:
            self.panes[ind-1].show()
            self.panes[ind-1].set_visibility(True)
            Nav.conf["panes"][item]["visible"] = True

    def tree_toggle(self):
        """Toggle the main tree."""
        if Nav.conf["window"]["main_tree"]:
            self.tree.hide()
        else:
            self.tree.show()
        Nav.conf["window"]["main_tree"] = not Nav.conf["window"]["main_tree"]

    def statusbar_toggle(self):
        """Toggle the status bar."""
        if Nav.conf["window"]["statusbar"]:
            Pub.unsubscribe("App", self.update_status_bar)
            self.sb.hide()
        else:
            Pub.subscribe("App", self.update_status_bar)
            self.sb.show()
        Nav.conf["window"]["statusbar"] = not Nav.conf["window"]["statusbar"]

    def show_settings(self):
        """Displays the settings window."""
        setting = NavSettings(self)
        setting.show()

    def closeEvent(self, event):
        """Save and exit application."""
        self.save_settings()
        QtWidgets.QMainWindow.closeEvent(self, event)

    def save_settings(self):
        """Saves application settings to reload later on."""
        NavWatcher.stop()  # Stop watching folders
        # Remember window sizes
        wind = self.geometry()
        Nav.conf["dims"] = {
            "main": [wind.x(), wind.y(), wind.width(), wind.height()],
            "tp": self.splitter.sizes(),
            "p13": self.splitter1.sizes(),
            "p24": self.splitter2.sizes(),
        }
        # Save pane information
        for p in range(Nav.conf["panes"]["total"]):
            paneid = self.panes[p].pid
            Nav.conf["dims"][paneid] = self.panes[p].splitter.sizes()
            Nav.conf["panes"][paneid]["visible"] = self.panes[p].isVisible()
            Nav.conf["panes"][paneid]["tabs"] = {
                "total": self.panes[p].tabbar.count(),
                "active": self.panes[p].tabbar.currentIndex(), }
            for j in range(Nav.conf["panes"][paneid]["tabs"]["total"]):
                tab = self.panes[p].tabbar.widget(j).tab
                Nav.conf["panes"][paneid]["tabs"][j] = {
                        "location": tab.location,
                        "history": list(tab.history),
                        "future": list(tab.future),
                        "caption": tab.caption,
                        "sort_column": tab.sort_column,
                        "sort_order": tab.sort_order,
                }
            Nav.conf["panes"]["active"] = self.active_pane.pid
        with open(Nav.conf_file, "w") as json_file:
            json.dump(Nav.conf, json_file, indent=4)

    def load_settings(self, conf: str=Nav.conf_file):
        """Load a config file and merge it with defaults"""
        try:
            with open(conf, "r") as json_file:
                d2 = json.load(json_file)
                deep_merge(Nav.conf, d2)
        except (OSError, json.decoder.JSONDecodeError):
            logger.error("{self.title}: Error reading JSON.")

    def tree_navigate(self, index):
        """Navigate to the location selected in the main tree."""
        loc = self.tree.model.filePath(index)
        # logger.debug(f"{self.title}: Tree Navigation: {loc}")
        self.active_pane.navigate(loc)

    @QtCore.pyqtSlot(QtCore.QObject)
    def active_pane_changed(self, obj):
        """Handles pane change event."""
        if self.active_pane.pid != obj.pid:
            self.active_pane.tabbar.setStyleSheet(
                    '''QTabBar::tab:selected {background: green;}
                    NavBreadCrumbsBar{background-color: green;}
                    QTabWidget::pane {border: 0px;}
                    ''')
            self.active_pane = obj
            self.setWindowTitle(f"{self.title} - {obj.pid}")
            self.active_pane.tabbar.setStyleSheet(
                    '''QTabBar::tab:selected {background: blue;}
                    NavBreadCrumbsBar{background-color: blue;}
                    QTabWidget::pane {border: 0px;}
                    ''')

    def update_status_bar(self, msg: str, duration: int = 2000):
        """Signals to update main status bar."""
        # Need to emit as signal as this function is invoked from outside
        self.update_sb.emit(msg, duration)

    @QtCore.pyqtSlot(str, int)
    def status_bar_update(self, msg: str, duration: int = 2000):
        """Update main status bar with the provided status information."""
        self.sb.showMessage(msg, duration)

    def keyPressEvent(self, event):
        """Trap key presses to invoke custom methods."""
        # Clear filter on Escape key press
        if event.key() == QtCore.Qt.Key_Escape:
            if self.active_pane.filter_edit.text() != "":
                self.active_pane.filter_edit.setText("")
            else:
                super().keyPressEvent(event)
                event.ignore()
        else:
            super().keyPressEvent(event)
            event.ignore()


def exception_hook(exctype, val, trcbk):
    """Try capturing exceptions and print it to the console."""
    print(exctype, val, trcbk)
    sys._excepthook(exctype, val, trcbk)
    sys.exit(1)

def main(args=None):
    if args is None:
        args = sys.argv[1:]
        logger.debug(args)
    sys._excepthook = sys.excepthook
    app = NavApp(args)


if __name__ == '__main__':
    main()
