import os
import pathlib
from PyQt5 import QtWidgets, QtCore
from .core import Nav
from .custom import NavTree
from .helper import logger
from .navwatcher import NavWatcher
from .pub import Pub
from .tabs import NavTab


class NavPane(QtWidgets.QFrame):
    activated = QtCore.pyqtSignal(QtCore.QObject)

    def __init__(self, pid, pane_info):
        super().__init__()
        x = self.size().width()
        self.pid = pid
        self.location = str(pathlib.Path.home())
        self.setStyleSheet("border: 1px solid red;")
        self.setStyleSheet(
                    "NavPane {border: 1px solid ;}")
        grid = QtWidgets.QGridLayout(self)
        self.abar = QtWidgets.QLineEdit()
        self.sb = QtWidgets.QStatusBar()
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.tree = NavTree()
        self.tree.clicked[QtCore.QModelIndex].connect(self.tree_navigate)
        self.abar.returnPressed.connect(self.go_to)
        self.tabbar = QtWidgets.QTabWidget()
        # Create button that must be placed in tabs row
        new_tab = QtWidgets.QToolButton()
        new_tab.setText("+")
        self.tabbar.setCornerWidget(new_tab, QtCore.Qt.TopRightCorner)
        new_tab.clicked.connect(lambda: self.new_tab())
        try:
            logger.debug(f"{self.pid}: Restoring tabs")
            for i in range(pane_info["tabs"]["total"]):
                tab_info = pane_info["tabs"][str(i)]
                self.new_tab(tab_info)
        except KeyError:
            logger.error(f"{self.pid}: Error restoring tabs")
            self.new_tab()
        try:
            logger.debug(f"Selecting active tab")
            self.tabbar.setCurrentIndex(int(pane_info["tabs"]["active"]))
        except KeyError:
            logger.error(f"Error Selecting active tab", exc_info=True)

        # line edit for filtering
        self.filter_edit = QtWidgets.QLineEdit()
        self.filter_edit.textChanged.connect(
            lambda: self.tabbar.currentWidget().tab.set_filter(
                    self.filter_edit.text()))
        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(self.tabbar)
        self.splitter.setSizes(Nav.getsizes(self.pid, [20, 80],
                                            [x*0.2, x*0.8]))
        grid.addWidget(self.abar, 0, 0, 1, 2)
        grid.addWidget(self.splitter, 1, 0, 1, 2)
        grid.addWidget(self.filter_edit, 2, 0, 1, 1)
        grid.addWidget(self.sb, 2, 1, 1, 1)
        self.tabbar.currentChanged.connect(self.tab_changed)
        self.setLayout(grid)
        if pane_info["visible"]:
            Pub.subscribe(f"Panes.{self.pid}", self.update_status_bar)
            self.update_gui_with_tab(self.tabbar.currentWidget().tab.location)
            # start monitoring active tab for refreshing
            NavWatcher.add_path(self.location, self.change_detected)
            NavWatcher.start()
        self.installEventFilter(self)  # this will catch focus events

    def set_visibility(self, visibility):
        """Toggle pane visibility."""
        if visibility:
            self.location = self.tabbar.currentWidget().tab.location
            self.update_gui_with_tab(self.location)
            Pub.subscribe(f"Panes.{self.pid}", self.update_status_bar)
            NavWatcher.add_path(self.location, self.change_detected)
            self.tabbar.currentWidget().tab.load_tab()
        else:
            NavWatcher.remove_path(self.location, self.change_detected)
            Pub.unsubscribe(f"Panes.{self.pid}", self.update_status_bar)

    def change_detected(self, evt, loc: str):
        """Informs current tab if its current directory was changed."""
        if loc == self.location:
            self.tabbar.currentWidget().tab.change_detected(evt)
            self.sb.showMessage(self.tabbar.currentWidget().tab.status_info)

    def eventFilter(self, obj, event):
        """Reimplemented to handle active pane."""
        if event.type() == QtCore.QEvent.MouseButtonPress \
                or event.type() == QtCore.QEvent.FocusIn:
            # logger.debug(f"{self.pid}: {event} {event.type()} for {obj}")
            self.location = self.tabbar.currentWidget().tab.location
            try:
                if os.getcwd() != self.location:
                    os.chdir(self.location)
            except FileNotFoundError:
                pass
            except NotADirectoryError:
                logger.error(f"{self.location} is not a directory")
            self.activated.emit(self)
            return QtCore.QObject.eventFilter(self, obj, event)
        else:
            return False

    def showEvent(self, event):
        """Installs event filters in all children of panel."""
        super().showEvent(event)
        # this will install event filter in all children of the panel
        for widget in self.findChildren(QtWidgets.QWidget):
            widget.installEventFilter(self)

    def tree_navigate(self, index):
        """Handles tree navigation."""
        loc = self.tree.model.filePath(index)
        logger.debug(f"{self.pid}: Tree Navigation: {loc}")
        ret = self.tabbar.currentWidget().tab.navigate(loc)
        self.sb.showMessage(self.tabbar.currentWidget().tab.status_info)
        if ret:
            self.abar.setText(loc)
            self.location = loc

    def go_to(self):
        """Handles address bar navigation."""
        loc = self.abar.text().replace('\\', '/')
        loc = loc.strip()
        if loc.startswith("@"):
            if "=" in loc:  # alias is being set
                alias, actual = loc.split("=", maxsplit=1)
                alias = alias.strip()
                actual = actual.strip()
                if actual == "":
                    try:
                        del Nav.conf["aliases"][alias]
                        logger.debug(f"Alias: {alias} unset")
                        Pub.notify("App", f"{self.pid}: Alias {alias} unset.",
                                   5000)
                    except KeyError:
                        pass
                else:
                    try:
                        Nav.conf["aliases"][alias] = actual
                    except KeyError:
                        Nav.conf["aliases"] = {alias: actual}
                    logger.debug(f"Alias: {alias} = {actual}")
                    Pub.notify("App", f"{self.pid}: Alias {alias} set to " \
                               f"{actual}.", 5000)
                self.abar.setText(self.location)
                return
            else:  # resolve alias
                try:
                    loc = Nav.conf["aliases"][loc]
                except KeyError:
                    logger.error(f"Alias {loc} not set")
                    Pub.notify("App", f"{self.pid}: Alias {loc} not set.")
                    self.abar.setText(self.location)
                    return
        ret = self.tabbar.currentWidget().tab.navigate(loc)
        self.sb.showMessage(self.tabbar.currentWidget().tab.status_info)
        if ret:
            self.location = loc
        else:
            self.abar.setText(self.location)

    def select_tab(self, index):
        """Select next/previous or the mentioned tab."""
        if index == "next":
            index = self.tabbar.currentIndex() + 1
        elif index == "prev":
            index = self.tabbar.currentIndex() - 1
        index = index % self.tabbar.count()
        self.tabbar.setCurrentIndex(index)

    def tab_changed(self):
        """Update GUI elements to reflect the tab change."""
        self.update_gui(self.tabbar.currentWidget().tab.location)

    def set_tab_caption(self, index=None, caption=None, loc=None):
        """Handles setting of tab caption"""
        if index is None:
            index = self.tabbar.currentIndex()  # current tab if not provided
        if caption is None:
            widget = self.tabbar.widget(index).tab
            if loc is None:
                loc = self.location
            if widget.caption is not None:
                self.tabbar.setTabToolTip(index, loc)
                return
            caption = os.path.basename(loc)
            if caption == "":
                caption = "/"
        self.tabbar.setTabText(index, caption)
        self.tabbar.setTabToolTip(index, loc)

    def new_tab(self, tab_info={}):
        """Creates a new tab with default/provided values."""
        t = NavTab(tab_info, parent_id=self.pid)
        t.tab.location_changed.connect(self.update_gui_with_tab)
        i = self.tabbar.addTab(t, tab_info["location"])
        self.set_tab_caption(i, caption=t.tab.caption, loc=t.tab.location)
        t.installEventFilter(self)  # install filter for new tabs

    def rename_tab(self, index: int=None, caption: str=None):
        """Renames a tab with provided/prompted caption."""
        if index is None:
            index = self.tabbar.currentIndex()
        if caption is None:
            current_caption = self.tabbar.widget(index).tab.caption
            caption, ok = QtWidgets.QInputDialog.getText(
                             self, 'Rename Tab', 'Enter new caption:',
                             QtWidgets.QLineEdit.Normal, current_caption)
            if ok:
                set_caption = True
        else:
            set_caption = True
        if set_caption:
            widget = self.tabbar.widget(index).tab
            if caption != "":
                widget.caption = caption
                self.set_tab_caption(index, caption=caption)
            else:
                widget.caption = None
                self.set_tab_caption(index, caption=None)

    def close_tab(self, index=None):
        """Close current/provided tab."""
        if self.tabbar.count() == 1:
            self.tabbar.setTabsClosable(False)
            Pub.notify(f"App.{self.pid}.Tabs",
                       f"{self.pid}: Can't close last tab.")
            return
        else:
            self.tabbar.setTabsClosable(True)
        if index is None:
            index = self.tabbar.currentIndex()
            logger.debug(f"About to remove current tab: {index}")
        else:
            logger.debug(f"About to remove {index}")
        widget = self.tabbar.widget(index)
        if widget is not None:
            logger.debug(f"Delete later {index}")
            widget.deleteLater()
        self.tabbar.removeTab(index)
        logger.debug(f"Removed tab {index}")

    def close_other_tabs(self):
        """Closes all tabs except the current tab."""
        for index in range(self.tabbar.count(), -1, -1):
            if index != self.tabbar.currentIndex():
                self.close_tab(index)
        Pub.notify(f"App.{self.pid}.Tabs",
                   f"{self.pid}: All other tabs closed")

    def close_left_tabs(self):
        """Close tabs to the left of the current tab."""
        for index in range(self.tabbar.currentIndex()-1, -1, -1):
            self.close_tab(index)
        Pub.notify(f"App.{self.pid}.Tabs", f"{self.pid}: Left tabs closed")

    def close_right_tabs(self):
        """Close tabs to the right of the current tab."""
        for index in range(self.tabbar.count(),
                           self.tabbar.currentIndex(), -1):
            self.close_tab(index)
        Pub.notify(f"App.{self.pid}.Tabs", f"{self.pid}: Right tabs closed")

    def position_tree(self, loc: str):
        """Repositions tree based on the currently navigated folder."""
        index = self.tree.model.index(loc, 0)
        self.tree.setCurrentIndex(index)
        self.tree.scrollTo(index)

    def update_gui_with_tab(self, loc):
        """Updates GUI and sets tab caption to sync with navigations."""
        cur_tab = self.tabbar.currentIndex()
        self.set_tab_caption(cur_tab, loc=loc)
        self.tabbar.currentWidget().bcbar.create_crumbs(loc)
        self.update_gui(loc)

    def update_gui(self, loc):
        """Updates GUI to sync with navigations."""
        if loc != self.location:
            try:
                NavWatcher.remove_path(self.location, self.change_detected)
                NavWatcher.add_path(loc, self.change_detected)
                os.chdir(loc)
                self.location = loc
                self.abar.setText(self.location)
                self.position_tree(self.location)
            except (FileNotFoundError, NotADirectoryError):
                logger.error(f"{loc} not found")
        else:
            self.abar.setText(loc)
        # load tab if not already loaded
        self.tabbar.currentWidget().tab.load_tab()
        self.tabbar.currentWidget().bcbar.create_crumbs(loc)
        self.filter_edit.setText(self.tabbar.currentWidget().tab.filter_text)
        self.sb.showMessage(self.tabbar.currentWidget().tab.status_info)

    def update_status_bar(self, msg):
        """Updates status bar for pane with provided message."""
        self.sb.showMessage(msg)
