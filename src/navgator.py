#!/bin/python3

import faulthandler
import json
import os
import pathlib
import psutil
import sys
import subprocess
from PyQt5 import QtGui, QtCore, QtWidgets
from .core import Nav, NavView, NavSize
from .custom import NavTree
from .helper import logger, deep_merge, humansize
from .navwatcher import NavWatcher
from .panes import NavPane
from .pub import Pub
from .settings import NavSettings
from .imageviewer import NavViewer
from .navtrash import NavTrash


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
        NavTrash.get_trash_folders()
        self.load_settings()
        Nav.icon = QtGui.QIcon(f"{Nav.app_dir}{os.sep}navgator.ico")
        self.setWindowIcon(Nav.icon)
        proc_id = os.getpid()
        self.res_info = psutil.Process(proc_id)
        self.img_vwr = None
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
        self.define_actions()
        self.sb = self.statusBar()
        self.res_label = QtWidgets.QLabel()
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
        Nav.pact = None
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
            p.pane_updated.connect(self.active_pane_changed)

            if i % 2 != 0:
                self.splitter1.addWidget(p)
            else:
                self.splitter2.addWidget(p)
            if not Nav.conf["panes"][name]["visible"]:
                p.hide()
            self.panes.append(p)

            self.stylesheet = ("QTabBar::tab:selected {{background: {bg};}}"
                               "NavBreadCrumbsBar{{background-color: {bg};}}"
                               "QTabWidget::pane {{border: 0px;}}")
            if Nav.conf["panes"]["active"] == name:
                Nav.pact = p
                p.tabbar.setStyleSheet(self.stylesheet.format(
                    bg=Nav.conf["colors"]["bcbar"]["active"]))
                self.setWindowTitle(f"{self.title} - {name}")
            else:
                p.tabbar.setStyleSheet(self.stylesheet.format(
                    bg=Nav.conf["colors"]["bcbar"]["inactive"]))
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
        # Focus active pane and tab
        Nav.pact.tabbar.currentWidget().view.setFocus()
        self.sb.addPermanentWidget(self.res_label)
        self.active_pane_changed(Nav.pact)
        Nav.conf["window"]["statusbar"] = not Nav.conf["window"]["statusbar"]
        self.statusbar_toggle()
        self.sb.showMessage("Ready", 2000)

    def update_resources(self):
        """Updates a label with memory usage"""
        # logger.debug(self.res_info.memory_full_info())
        mem = humansize(self.res_info.memory_full_info().uss)
        cpu = self.res_info.cpu_percent()
        self.res_label.setText(f"{mem} ({cpu}%)")

    def define_actions(self):
        self.actions = {
            "exit": {
                "caption": "E&xit",
                "icon": QtGui.QIcon.fromTheme('file-exit'),
                "shortcut": "Ctrl+Q",
                "triggered": self.close,
                "statusTip": "Exit application",
            },
            "back": {
                "caption": "Go &Back",
                "icon": self.style().standardIcon(
                    QtWidgets.QStyle.SP_ArrowBack),
                "shortcut": "Backspace",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              go_back()),
            },
            "forward": {
                "caption": "Go &Forward",
                "icon": self.style().standardIcon(
                    QtWidgets.QStyle.SP_ArrowForward),
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              go_forward()),
            },
            "up": {
                "caption": "Go &Up",
                "icon": self.style().standardIcon(
                    QtWidgets.QStyle.SP_ArrowUp),
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              go_up()),
            },
            "rename": {
                "caption": "&Rename",
                "shortcut": "F2",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              rename_file()),
            },
            "cut": {
                "caption": "C&ut",
                "shortcut": "Ctrl+X",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().copy(
                              cut=True)),
            },
            "copy": {
                "caption": "&Copy",
                "shortcut": "Ctrl+C",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().copy()),
            },
            "paste": {
                "caption": "&Paste",
                "shortcut": "Ctrl+V",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().paste())
            },
            "trash": {
                "caption": "&Trash",
                "shortcut": "del",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().trash())
            },
            "delete": {
                "caption": "&Delete",
                "shortcut": "Shift+del",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              delete()),
            },
            "del_dir_up": {
                "caption": "Delete Dir Up",
                "shortcut": "Ctrl+del",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              del_dir_up(0)),
            },
            "del_dir_random": {
                "caption": "Delete Dir Random",
                "shortcut": "Alt+del",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              del_dir_up(1)),
            },
            "parent_random": {
                "caption": "Delete Dir Random",
                "shortcut": "Ctrl+Backspace",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              del_dir_up(2)),
            },
            "new_file": {
                "caption": "&New File",
                "shortcut": "Ctrl+N",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              new_file("file")),
                "icon": self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
            },
            "new_folder": {
                "caption": "New &Folder",
                "shortcut": "Ctrl+Shift+N",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              new_file("folder")),
                "icon": self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon),
            },
            "select_all": {
                "caption": "&Select All",
                "shortcut": "Ctrl+A",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              updateModel(0, 1)),
            },
            "clear_all": {
                "caption": "&Clear All",
                "shortcut": "Ctrl+Shift+A",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              updateModel(0, 0)),
            },
            "invert": {
                "caption": "&Invert Select",
                "shortcut": "Ctrl+Shift+I",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              invert_selection()),
            },
            "new_tab": {
                "caption": "&New Tab",
                "shortcut": "Ctrl+T",
                "triggered": (lambda: Nav.pact.tabbar.new_tab()),
            },
            "close_tab": {
                "caption": "&Close Tab",
                "shortcut": "Ctrl+W",
                "triggered": (lambda: Nav.pact.tabbar.close_tab()),
            },
            "rename_tab": {
                "caption": "&Rename Tab",
                "shortcut": "Ctrl+E",
                "triggered": (lambda: Nav.pact.tabbar.set_caption(
                              rename=True)),
            },
            "next_tab": {
                "caption": "Ne&xt Tab",
                "shortcut": "Ctrl+Tab",
                "triggered": (lambda: Nav.pact.tabbar.select_tab("next")),
            },
            "prev_tab": {
                "caption": "Pre&vious Tab",
                "shortcut": "Ctrl+Shift+Tab",
                "triggered": (lambda: Nav.pact.tabbar.select_tab("prev")),
            },
            "close_other_tabs": {
                "caption": "Close &Other Tabs",
                "triggered": (lambda: Nav.pact.tabbar.close_other_tabs()),
            },
            "close_left_tabs": {
                "caption": "Close &Left Tabs",
                "triggered": (lambda: Nav.pact.tabbar.close_left_tabs()),
            },
            "close_right_tabs": {
                "caption": "Close &Right Tabs",
                "triggered": (lambda: Nav.pact.tabbar.close_right_tabs()),
            },
            "maintree": {
                "caption": "&Main Tree",
                "checkable": True,
                "checked": Nav.conf["window"]["main_tree"],
                "shortcut": "F8",
                "triggered": self.tree_toggle,
                "icon": self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
            },
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
            },
            "copy_path": {
                "caption": "&Copy Path",
                "shortcut": "Ctrl+Shift+P",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().bcbar.
                              copy_path()),
            },
            "paste_and_go": {
                "caption": "&Paste and Go",
                "shortcut": "Ctrl+Shift+G",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().bcbar.
                              paste_and_go()),
            },
            "details_view": {
                "caption": "&Details",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              switch_view(NavView.Details))
            },
            "list_view": {
                "caption": "&List",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              switch_view(NavView.List, NavSize.Tiny))
            },
            "small_icons_view": {
                "caption": "&Small Icons",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              switch_view(NavView.Icons, NavSize.Small))
            },
            "medium_icons_view": {
                "caption": "&Medium Icons",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              switch_view(NavView.Icons, NavSize.Medium))
            },
            "large_icons_view": {
                "caption": "&Large Icons",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              switch_view(NavView.Icons, NavSize.Large))
            },
            "xl_icons_view": {
                "caption": "E&xtra Large Icons",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              switch_view(NavView.Icons, NavSize.XL))
            },
            "SmallThumbs": {
                "caption": "Small &Thumbnails",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              switch_view(NavView.Thumbnails, NavSize.Small))
            },
            "MediumThumbs": {
                "caption": "Medium T&humbnails",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              switch_view(NavView.Thumbnails, NavSize.Medium))
            },
            "LargeThumbs": {
                "caption": "Large Th&umbnails",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              switch_view(NavView.Thumbnails, NavSize.Large))
            },
            "XLThumbs": {
                "caption": "Extra Large Thum&bnails",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              switch_view(NavView.Thumbnails, NavSize.XL))
            },
            "image-viewer": {
                "caption": "Image Viewer",
                "triggered": (lambda: self.image_viewer()),
                "shortcut": "F11",
            },
            "sort-random": {
                "caption": "Sort Randomly",
                "shortcut": "Ctrl+Shift+R",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              sort_random())
            },
            "refresh": {
                "caption": "Refresh",
                "shortcut": "F5",
                "triggered": (lambda: Nav.pact.tabbar.currentWidget().
                              load_tab(forced=True))
            },
        }

        pane_count = Nav.conf["panes"]["total"]
        if pane_count > 4:
            pane_count = 4
        # items2 = {f"Pane {i}": None for i in range(1, pane_count + 1)}
        for i in range(1, pane_count + 1):
            name = f"Pane {i}"
            self.actions[name] = {
                "caption": f"Pane &{i}",
                "checkable": True,
                "checked": Nav.conf["panes"][name]["visible"],
                "triggered": (lambda a=0, ind=i, name1=name: self.pane_toggle(
                              ind, name1)),
            }
        Nav.actions = {}
        for k, v in self.actions.items():
            cap = v.pop("caption")  # caption isn't valid keyword arg
            Nav.actions[k] = QtWidgets.QAction(cap, self, **v)
            if k in Nav.conf["shortcuts"]:
                Nav.actions[k].setShortcut(Nav.conf["shortcuts"][k])
            self.addAction(Nav.actions[k])

    def create_toolbar(self):
        """Creates a toolbar."""
        self.toolbar = self.addToolBar("Main")
        self.toolbar.setMovable(False)

        # Create back button and add it
        back_menu = QtWidgets.QMenu()
        back_menu.setStyleSheet("QMenu{menu-scrollable: 1; }")
        back_menu.aboutToShow.connect(lambda: self.back_drop_menu(back_menu))
        back_menu.triggered.connect(self.navigate_to)
        back = QtWidgets.QToolButton()
        back.setIcon(self.style().standardIcon(
                     QtWidgets.QStyle.SP_ArrowBack))
        back.setDefaultAction(Nav.actions["back"])
        back.setMenu(back_menu)
        back.setAutoRaise(True)
        back.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)
        self.toolbar.addWidget(back)

        # Create forward button and add it
        forward_menu = QtWidgets.QMenu()
        forward_menu.setStyleSheet("QMenu{menu-scrollable: 1; }")
        forward_menu.aboutToShow.connect(lambda: self.forward_drop_menu(
            forward_menu))
        forward_menu.triggered.connect(self.navigate_to)
        forward = QtWidgets.QToolButton()
        forward.setIcon(self.style().standardIcon(
                     QtWidgets.QStyle.SP_ArrowForward))
        forward.setDefaultAction(Nav.actions["forward"])
        forward.setMenu(forward_menu)
        forward.setAutoRaise(True)
        forward.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)
        self.toolbar.addWidget(forward)

        self.toolbar.addAction(Nav.actions["up"])
        for widget in self.toolbar.findChildren(QtWidgets.QWidget):
            widget.installEventFilter(self)

    def back_drop_menu(self, sender):
        """Presents a menu on drop down button press."""
        sender.clear()
        for item in reversed(Nav.pact.tabbar.currentWidget().history):
            sender.addAction(item)

    def forward_drop_menu(self, sender):
        """Presents a menu on drop down button press."""
        sender.clear()
        for item in reversed(Nav.pact.tabbar.currentWidget().future):
            sender.addAction(item)

    def navigate_to(self, sender):
        """Navigates to the location clicked on back or forward drop menu"""
        Nav.pact.tabbar.currentWidget().navigate(sender.text())

    def create_menu(self):
        """Creates menu recursively."""
        # Python 3.7 tracks insertion order
        items = {
            "file": {"caption": "&File"},
            "edit": {"caption": "&Edit"},
            "view": {"caption": "&View"},
            "tabs": {"caption": "&Tabs"},
            "user": {"caption": "&User", "sm": {}},
            "window": {"caption": "&Window", "sm": {}}
        }

        if "user_commands" not in Nav.conf:
            del items["user"]

        items["file"]["sm"] = [Nav.actions["exit"]]

        items["edit"]["sm"] = [
            Nav.actions["rename"], Nav.actions["cut"], Nav.actions["copy"],
            Nav.actions["paste"], Nav.actions["trash"], Nav.actions["delete"],
            Nav.actions["del_dir_up"], Nav.actions["new_file"],
            Nav.actions["new_folder"],
            {
                "caption": "&Selections",
                "sm": [
                    Nav.actions["select_all"], Nav.actions["clear_all"],
                    Nav.actions["invert"],
                ]
            }
        ]

        items["view"]["sm"] = [
            Nav.actions["details_view"], Nav.actions["list_view"],
            Nav.actions["small_icons_view"], Nav.actions["medium_icons_view"],
            Nav.actions["large_icons_view"], Nav.actions["xl_icons_view"],
            Nav.actions["SmallThumbs"], Nav.actions["MediumThumbs"],
            Nav.actions["LargeThumbs"], Nav.actions["XLThumbs"]
        ]

        items["tabs"]["sm"] = [
            Nav.actions["new_tab"], Nav.actions["close_tab"],
            Nav.actions["rename_tab"],
            Nav.actions["next_tab"], Nav.actions["prev_tab"],
            Nav.actions["close_other_tabs"],
            Nav.actions["close_left_tabs"], Nav.actions["close_right_tabs"],
        ]

        pane_count = Nav.conf["panes"]["total"]
        if pane_count > 4:
            pane_count = 4

        items["window"]["sm"] = [Nav.actions[f"Pane {i}"]
                                 for i in range(1, pane_count + 1)]

        items["window"]["sm"] += [
            Nav.actions["maintree"], Nav.actions["settings"],
            Nav.actions["statusbar"],
        ]

        self.expose_shortcuts(items)
        self.menubar.clear()
        Nav.build_menu(self, items, self.menubar)
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
            item = " ".join(Nav.pact.tabbar.currentWidget().
                            get_selected_items())
        else:
            item = Nav.pact.location
        # logger.debug(f"Command: {command} Args:{item}")
        subprocess.Popen(f'{command} {item}', shell=True)

    def pane_toggle(self, ind: int, item: str):
        """Toggle pane visibility"""
        if Nav.conf["panes"][item]["visible"]:
            # Check if atleast one other visible pane
            for p in self.panes:
                if p != self.panes[ind-1] and p.isVisible():
                    # if hiding active pane, activate another pane
                    if self.panes[ind-1] is Nav.pact:
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
            try:
                self.qtimer.stop()
            except AttributeError:
                pass  # QTimer wasn't created.
            self.sb.hide()
        else:
            Pub.subscribe("App", self.update_status_bar)
            self.qtimer = QtCore.QTimer()
            self.qtimer.timeout.connect(self.update_resources)
            self.qtimer.start(1000)
            self.sb.show()
        Nav.conf["window"]["statusbar"] = not Nav.conf["window"]["statusbar"]

    def show_settings(self):
        """Displays the settings window."""
        setting = NavSettings(self)
        setting.settings_changed.connect(self.settings_changed)
        setting.show()

    def settings_changed(self):
        logger.debug("Settings were changed")
        self.create_menu()
        # for k in Nav.conf:
        #    if k == "panes":

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.ToolTip:
            try:
                if obj.text() == "Go Back":
                    obj.setToolTip(Nav.pact.tabbar.currentWidget().history[-1])
                elif obj.text() == "Go Forward":
                    obj.setToolTip(Nav.pact.tabbar.currentWidget().future[0])
            except IndexError:
                obj.setToolTip("No more")
            except AttributeError as e:
                logger.debug(e)
            # logger.debug(f"Caught on {obj} {obj.text()}")
            # return True
        return QtCore.QObject.eventFilter(self, obj, event)

    def closeEvent(self, event):
        """Save and exit application."""
        self.save_settings()
        QtWidgets.QMainWindow.closeEvent(self, event)

    def contextMenuEvent(self, event):
        child = self.childAt(event.pos())
        logger.debug(f"Context menu requested on {child}")

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
                tab = self.panes[p].tabbar.widget(j)
                headers = []
                for k, v in tab.header.items():
                    if v.visible:
                        headers.append([v.caption, v.size, v.position])

                Nav.conf["panes"][paneid]["tabs"][j] = {
                        "location": tab.location,
                        "history": list(tab.history),
                        "future": list(tab.future),
                        "caption": self.panes[p].tabbar.tabBar().tabData(j),
                        "sort_column": tab.sort_column,
                        "sort_order": tab.sort_order,
                        "columns": headers,
                        "view": tab.vtype,
                        "itsize": tab.vsize,
                }
            Nav.conf["panes"]["active"] = Nav.pact.pid
        with open(Nav.conf_file, "w") as json_file:
            json.dump(Nav.conf, json_file, indent=4)
        logger.debug(f"Settings saved to {Nav.conf_file}")

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
        Nav.pact.navigate(loc)

    @QtCore.pyqtSlot(QtCore.QObject)
    def active_pane_changed(self, obj):
        """Handles pane change event."""
        if Nav.pact.pid != obj.pid:
            Nav.pact.tabbar.setStyleSheet(self.stylesheet.format(
                bg=Nav.conf["colors"]["bcbar"]["inactive"]))
            Nav.pact = obj
            self.setWindowTitle(f"{self.title} - {obj.pid}")
            Nav.pact.tabbar.setStyleSheet(self.stylesheet.format(
                bg=Nav.conf["colors"]["bcbar"]["active"]))
        Nav.actions["up"].setEnabled(Nav.pact.can_go_up)
        Nav.actions["back"].setEnabled(Nav.pact.can_go_back)
        Nav.actions["forward"].setEnabled(Nav.pact.can_go_forward)

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
            if Nav.pact.filter_edit.text() != "":
                Nav.pact.filter_edit.setText("")
            else:
                super().keyPressEvent(event)
                event.ignore()
        else:
            super().keyPressEvent(event)
            event.ignore()

    def image_viewer(self):
        if self.img_vwr is None:
            self.img_vwr = NavViewer()
        self.img_vwr.show()
        self.img_vwr.loadCurrentImage(Nav.pact.tabbar.currentWidget())


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
    NavApp(args)


def trace(frame, event, arg):
    print(f"{event}, {frame.f_code.co_filename}:{frame.f_lineno}")
    return trace


if __name__ == '__main__':
    faulthandler.enable()
    # sys.settrace(trace)
    main()
