import collections
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import threading
from PyQt5 import QtWidgets, QtCore, QtGui
from send2trash import send2trash
from .breadcrumbs import NavBreadCrumbsBar
from .helper import logger, humansize
from .pub import Pub
from .model import NavItemModel
from .custom import (NavSortFilterProxyModel, NavHeaderView, NavColumn)
from .core import Nav, NavView


class NavTabWidget(QtWidgets.QTabWidget):
    """Re-implemented to present tab menu"""
    cMenu = None  # common contextMenu across class
    tab_created = QtCore.pyqtSignal()

    def __init__(self, parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = parent
        self.pid = self.parent.pid
        if self.cMenu is None:
            # logger.debug("Creating context menu for tabbar")
            self.__class__.cMenu = QtWidgets.QMenu()
            items = [
                Nav.actions["new_tab"], Nav.actions["close_tab"],
                Nav.actions["rename_tab"],
                Nav.actions["close_other_tabs"],
                Nav.actions["close_left_tabs"],
                Nav.actions["close_right_tabs"],
            ]
            Nav.build_menu(self, items, self.cMenu)

    def new_tab(self, tab_info={}):
        """Creates a new tab with default/provided values."""
        t = NavTab(tab_info, parent_id=self.pid)
        t.location_changed.connect(self.update_gui_with_tab)
        i = self.addTab(t, tab_info["location"])
        self.set_caption(i, caption=t.caption, loc=t.location)
        self.tab_created.emit()  # install filter for new tabs

    def update_gui_with_tab(self, loc):
        """Updates GUI and sets tab caption to sync with navigations."""
        cur_tab = self.currentIndex()
        self.set_caption(cur_tab, loc=loc)
        # self.currentWidget().bcbar.create_crumbs(loc)
        self.currentChanged.emit(cur_tab)

    def set_caption(self, index: int=None, caption: str=None,
                    loc: str=None, rename: bool=False):
        """Renames a tab with provided/prompted caption."""
        if index is None:
            index = self.get_index()
        # logger.debug(f"Tab data: {self.tabBar().tabData(index)}")
        if not caption:
            if rename:
                current_caption = self.tabText(index)
                caption, ok = QtWidgets.QInputDialog.getText(
                                self, 'Rename Tab', 'Enter new caption:',
                                QtWidgets.QLineEdit.Normal, current_caption)
                if not ok:
                    return
                self.tabBar().setTabData(index, caption)
            if not caption:
                if loc is None:
                    loc = self.tabToolTip(index)
                if self.tabBar().tabData(index):
                    self.setTabToolTip(index, loc)
                    return
                caption = os.path.basename(loc)
                if caption == "":
                    caption = "/"
        else:
            self.tabBar().setTabData(index, caption)
        self.setTabText(index, caption)
        if loc is not None:
            self.setTabToolTip(index, loc)

    def contextMenuEvent(self, event):
        """Presents a context menu at mouse position."""
        tab = self.tabBar().tabAt(event.pos())
        if tab < 0:
            return
        self.cMenu.exec_(event.globalPos())
        logger.debug(f"Mouse is on tab# {self.tabBar().tabAt(event.pos())}")

    def get_index(self, depth=3):
        """Gets index for actioning tab."""
        if sys._getframe(depth).f_back.f_code.co_name == "__init__":
            return self.rc_on
        else:
            return self.currentIndex()

    def select_tab(self, index):
        """Select next/previous or the mentioned tab."""
        if index == "next":
            index = self.currentIndex() + 1
        elif index == "prev":
            index = self.currentIndex() - 1
        index = index % self.count()
        self.setCurrentIndex(index)

    def close_tab(self, index=None):
        """Close current/provided tab."""
        if self.count() == 1:
            self.setTabsClosable(False)
            Pub.notify(f"App.{self.pid}.Tabs",
                       f"{self.pid}: Can't close last tab.")
            return
        else:
            self.setTabsClosable(True)
        if index is None:
            index = self.get_index()
        widget = self.widget(index)
        if widget is not None:
            widget.deleteLater()
        self.removeTab(index)
        logger.debug(f"Removed tab {index}")

    def close_other_tabs(self, index=None):
        """Closes all tabs except this."""
        if index is None:
            index = self.get_index()
        for ind in range(self.count(), -1, -1):
            if ind != index:
                self.close_tab(ind)
        Pub.notify(f"App.{self.pid}.Tabs",
                   f"{self.pid}: All other tabs closed")

    def close_left_tabs(self, index=None):
        """Close tabs to the left."""
        if index is None:
            index = self.get_index()
        for ind in range(index-1, -1, -1):
            self.close_tab(ind)
        Pub.notify(f"App.{self.pid}.Tabs", f"{self.pid}: Left tabs closed")

    def close_right_tabs(self, index=None):
        """Close tabs to the right."""
        if index is None:
            index = self.get_index()
        for ind in range(self.count(), index, -1):
            self.close_tab(ind)
        Pub.notify(f"App.{self.pid}.Tabs", f"{self.pid}: Right tabs closed")

    def mousePressEvent(self, event):
        """Re-implement to capture the index at mouse position."""
        if event.button() == QtCore.Qt.RightButton:
            index = self.tabBar().tabAt(event.pos())
            self.rc_on = index
        else:
            super().mousePressEvent(event)


class NavTab(QtWidgets.QFrame):
    """Class to handle base skeleton for tabs."""
    location_changed = QtCore.pyqtSignal(str)
    status_updated = QtCore.pyqtSignal(str)

    def __init__(self, tab_info, parent_id):
        self.mutex = QtCore.QMutex()
        super().__init__()
        self.pid = parent_id
        self.bcbar = NavBreadCrumbsBar("/")
        self.bcbar.clicked.connect(self.navigate)
        self._offset = QtCore.QPoint(30, 30)
        self.history = collections.deque(maxlen=64)
        self.future = collections.deque(maxlen=64)
        try:
            self.history = tab_info["history"]
        except (KeyError, TypeError):
            pass
        try:
            self.future = tab_info["future"]
        except (KeyError, TypeError):
            pass
        try:
            self.location = tab_info["location"]
        except (KeyError, TypeError):
            self.location = str(pathlib.Path.home())
            tab_info["location"] = self.location
        try:
            self.caption = tab_info["caption"]
        except (KeyError, TypeError):
            self.caption = None
        self.status_info = ''
        self.filter_text = ''
        self._loading = False
        try:
            self.sort_column = int(tab_info["sort_column"])
        except (KeyError, TypeError):
            self.sort_column = 0
        try:
            self.sort_order = int(tab_info["sort_order"])
        except (KeyError, TypeError):
            self.sort_order = 0

        self.header = [
            NavColumn("Name", 300),
            NavColumn("Ext", 50),
            NavColumn("Size", 100),
            NavColumn("Modified", 150),
            NavColumn("Thumbnails", 128)
        ]
        self.model = NavItemModel(self, self.header)
        self.proxy = NavSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterKeyColumn(0)
        self.lv = self.tv = None
        self.init_table_view()
        self.init_list_view()
        self.view = self.tv
        self.vtype = NavView.Details
        self.rubberBand = QtWidgets.QRubberBand(
            QtWidgets.QRubberBand.Rectangle, self.view.viewport())

        # Show columns for tab
        if "columns" in tab_info:
            for idx, h in enumerate(self.header):
                flag = 0
                for col in tab_info["columns"]:
                    if h.caption == col[0]:
                        flag = 1
                        break
                if not flag and idx != 0:
                    self.hv.hideSection(idx)
                    h.visible = False
                elif col[2] != -1:
                    vis_ind = self.hv.visualIndex(idx)
                    self.hv.moveSection(vis_ind, col[2])
            # Capture movements made before connecting the signal
            self.columns_visibility_changed(4, "Thumbnails",
                                            self.header[4].visible)
            self.columns_moved(0, 0, 0)
        # Connect to save column movements
        self.hv.sectionMoved.connect(self.columns_moved)
        self.hv.visibility_changed.connect(self.columns_visibility_changed)
        self.lyt = QtWidgets.QVBoxLayout()
        self.lyt.setSpacing(0)
        self.lyt.setContentsMargins(0, 0, 0, 0)
        self.lyt.addWidget(self.bcbar)
        self.lyt.addWidget(self.view)
        self.setLayout(self.lyt)
        self.install_filters()
        self.proxy.dataChanged.connect(self.row_sel)

    def init_header(self):
        """Initializes a header with checkbox selection."""
        self.hv = NavHeaderView(self.header)
        self.hv.setSectionsMovable(True)
        self.hv.setSectionsClickable(True)
        self.hv.setHighlightSections(True)
        self.hv.clicked.connect(self.updateModel)
        self.hv.setModel(self.model)

    def init_table_view(self):
        """Initialize Details View."""
        self.tv = QtWidgets.QTableView()
        self.init_header()
        self.tv.setWordWrap(False)
        self.tv.setSelectionBehavior(self.tv.SelectItems)
        self.tv.setEditTriggers(QtWidgets.QAbstractItemView.EditKeyPressed)
        self.tv.setHorizontalHeader(self.hv)
        self.tv.setSortingEnabled(True)
        self.tv.setAlternatingRowColors(True)
        self.tv.setModel(self.proxy)
        self.tv.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tv.horizontalHeader().sortIndicatorChanged.connect(
                                                    self.sortIndicatorChanged)
        self.tv.SelectionBehavior(1)
        self.tv.SelectionMode(7)
        self.tv.selectionModel().selectionChanged.connect(self.rows_selected)
        self.tv.doubleClicked.connect(self.double_clicked)
        self.tv.setDragDropMode(
                QtWidgets.QAbstractItemView.DragDrop &
                ~QtWidgets.QAbstractItemView.InternalMove)

    def init_list_view(self):
        """Initialize List View."""
        self.lv = QtWidgets.QListView()
        self.lv.setWordWrap(True)
        self.lv.setMovement(QtWidgets.QListView.Snap)
        self.lv.setResizeMode(QtWidgets.QListView.Adjust)
        self.lv.setDragEnabled(True)
        self.lv.setDragDropMode(QtWidgets.QAbstractItemView.DragDrop &
                                ~QtWidgets.QAbstractItemView.InternalMove)
        self.lv.setSelectionBehavior(self.lv.SelectItems)
        self.lv.setEditTriggers(QtWidgets.QAbstractItemView.EditKeyPressed)
        self.lv.setAlternatingRowColors(True)
        self.lv.setModel(self.proxy)
        self.lv.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.lv.setUniformItemSizes(True)
        self.lv.SelectionBehavior(1)
        self.lv.SelectionMode(7)
        self.lv.selectionModel().selectionChanged.connect(self.rows_selected)
        self.lv.doubleClicked.connect(self.double_clicked)

    def switch_view(self, new_view, width=32, height=32):
        """Switch between views"""
        if new_view == NavView.Details:
            if self.tv is not self.view:
                selections = self.view.selectionModel().selection()
                self.lyt.removeWidget(self.view)
                self.view.setGeometry(0, 0, 0, 0)
                self.view = self.tv
                self.lyt.addWidget(self.view)
                self.view.selectionModel().select(
                    selections, QtCore.QItemSelectionModel.ClearAndSelect)
                self.vtype = NavView.Details
            return
        elif self.lv is not self.view:
            selections = self.view.selectionModel().selection()
            self.lyt.removeWidget(self.view)
            self.view.setGeometry(0, 0, 0, 0)
            self.view = self.lv
            self.lyt.addWidget(self.view)
            self.view.selectionModel().select(
                selections, QtCore.QItemSelectionModel.ClearAndSelect)
            self.vtype = NavView.List

        if new_view == NavView.List:
            self.view.setViewMode(QtWidgets.QListView.ListMode)
            self.lv.setIconSize(QtCore.QSize(width, height))
        elif new_view == NavView.Icons:
            self.view.setViewMode(QtWidgets.QListView.IconMode)
            self.lv.setIconSize(QtCore.QSize(width, height))

    def install_filters(self):
        """Install event filter in all children of the panel."""
        for widget in self.findChildren(QtWidgets.QWidget):
            widget.installEventFilter(self)

    @property
    def location(self):
        return self._location

    @location.setter
    def location(self, value):
        if value == "":
            return
        self._location = value

    def set_filter(self, filter_text):
        """Apply the filter provided in filter box."""
        self.filter_text = filter_text
        self.proxy.setFilterCaseSensitivity(False)
        self.proxy.setFilterRegExp(filter_text)
        for i in range(self.proxy.rowCount()):
            index = self.proxy.index(i, 0)
            if index not in self.view.selectionModel().selectedIndexes():
                self.proxy.setData(index, QtCore.Qt.Unchecked,
                                   QtCore.Qt.CheckStateRole)

    def eventFilter(self, obj, event):
        """Reimplemented to handle active pane."""
        if self.vtype == NavView.Details:
            if event.type() == QtCore.QEvent.MouseButtonRelease:
                self.tv_mouseReleaseEvent(event)
            elif event.type() == QtCore.QEvent.MouseButtonPress:
                self.tv_mousePressEvent(event)
            elif event.type() == QtCore.QEvent.MouseMove:
                self.tv_mouseMoveEvent(event)
        return False

    def tv_mousePressEvent(self, event):
        """Reimplemented for custom handling."""
        self.origin = event.pos()
        self._modifier = event.modifiers()
        if self.view.indexAt(self.origin).column() != 0:
            self.view.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
            self._selection = self.view.selectionModel().selection()
            self.rubberBand.setGeometry(QtCore.QRect(self.origin,
                                                     QtCore.QSize()))
            self.rubberBand.show()
        else:
            self.view.setDragDropMode(
                QtWidgets.QAbstractItemView.DragDrop &
                ~QtWidgets.QAbstractItemView.InternalMove)
        # super().mousePressEvent(event)

    def tv_mouseMoveEvent(self, event):
        """Reimplemented for custom handling."""
        if self.rubberBand.isVisible():
            pos = event.pos()
            self.rubberBand.setGeometry(
                QtCore.QRect(self.origin, pos).normalized())
            rect = self.rubberBand.geometry()
            tl = rect.topLeft()
            br = rect.bottomRight()
            qis = QtCore.QItemSelection(self.view.indexAt(tl),
                                        self.view.indexAt(br))
            mode = QtCore.QItemSelectionModel.ClearAndSelect
            if self._modifier == QtCore.Qt.ControlModifier:
                mode = QtCore.QItemSelectionModel.Clear | \
                       QtCore.QItemSelectionModel.Toggle
                qis.merge(self._selection, mode)
            if self._modifier == QtCore.Qt.ShiftModifier:
                qis.merge(self._selection, mode)
            self.view.selectionModel().select(qis, mode)
            event.accept()

    def tv_mouseReleaseEvent(self, event):
        """Reimplement for custom handling."""
        # Unset selection if selection rectangle was drawn and hide rectangle
        if self.rubberBand.isVisible():
            self.rubberBand.hide()
            self._selection = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def double_clicked(self, index):
        """Get details to open the double clicked item."""
        if index == self.view.currentIndex():
            item = self.proxy.itemData(index).get(0)
        else:
            item = None
        if item:
            loc = os.path.join(self.location, item)
        else:
            loc = os.path.dirname(self.location)
        self.opener(loc)

    def opener(self, loc):
        """Launches the file or navigates to the said location."""
        if os.path.isdir(loc):
            self.navigate(loc)
        else:
            if os.name == 'posix':  # For Linux, Mac, etc.
                subprocess.call(('xdg-open', loc))
            elif sys.platform.startswith('darwin'):
                subprocess.call(('open', loc))
            elif os.name == 'nt':  # For Windows
                os.startfile(loc)

    def navigate(self, d):
        """Navigates to the provided location."""
        logger.debug(f"Invoked by {sys._getframe().f_back.f_code.co_name}")
        logger.debug(f"Navigating to {d}")
        if d != self.location:
            if Nav.conf["history_without_dupes"] and \
                    self.location in self.history:
                self.history.remove(self.location)
            self.history.append(self.location)
            self.load_tab(d)
            self.future.clear()

    def go_up(self):
        """Go up the tree."""
        try:
            loc = os.path.dirname(self.location)
            self.opener(loc)
        except OSError:
            logger.error(exc_info=True)

    def go_back(self):
        """Go back in history."""
        try:
            d = self.history.pop()
            if d != self.location:
                if self.location in self.future:
                    self.future.remove(self.location)
                self.future.append(self.location)
                self.load_tab(d)
                logger.debug(f"Future: {self.future}")
        except IndexError:
            logger.error(f"No more back")

    def go_forward(self):
        """Go forward in future."""
        try:
            d = self.future.pop()
            if d != self.location:
                if self.location in self.history:
                    self.history.remove(self.location)
                self.history.append(self.location)
                self.load_tab(d)
                logger.debug(f"History: {self.history}")
        except IndexError:
            logger.error(f"No more forward")

    def latest_history(self):
        return self.history[0]

    def row_sel(self, a, b):
        """Toggle row selection on checkbox click."""
        self.view.selectionModel().select(a, QtCore.QItemSelectionModel.Toggle)

    def model_changed(self, a, b):
        logger.debug(f"called {a} {b}")

    def rows_selected(self, sel, desel):
        """Handle row (de)selections."""
        for index in sel.indexes():
            self.proxy.setData(index, QtCore.Qt.Checked,
                               QtCore.Qt.CheckStateRole)
        for index in desel.indexes():
            if not self.proxy.itemData(index):
                continue

            if self.filter_text == "":
                self.proxy.setData(index, QtCore.Qt.Unchecked,
                                   QtCore.Qt.CheckStateRole)

        selstat = len(self.view.selectionModel().selectedIndexes())
        if selstat:
            selcount, selsize = self.model.get_selection_stats()
            selinfo = f" Selected: {selcount} : " \
                      f"{humansize(selsize)}"
            if (selstat >= self.proxy.rowCount()):
                self.hv.updateCheckState(1)
            else:
                self.hv.updateCheckState(2)
        else:
            selinfo = ""
            self.hv.updateCheckState(0)
        Pub.notify(f"Panes.{self.pid}.Tabs", f"{self.status_info} {selinfo}")

    def updateModel(self, index, state):
        if index != 0:
            return
        if state:
            if self.vtype == NavView.Details:
                self.view.selectColumn(index)
            else:
                self.view.selectAll()
        else:
                self.view.clearSelection()

    def invert_selection(self):
        """Toggles (de)selection of items in current listing."""
        for i in range(self.proxy.rowCount()):
            ix = self.proxy.index(i, 0)
            self.view.selectionModel().select(
                ix, QtCore.QItemSelectionModel.Toggle)

    def keyPressEvent(self, event):
        """Reimplemented keyPressEvent for custom handling."""
        if event.key() == QtCore.Qt.Key_Return:
            index = self.view.currentIndex()
            item = self.proxy.itemData(index).get(0)
            if self.view.state() != QtWidgets.QAbstractItemView.EditingState:
                loc = os.path.join(self.location, item)
                self.opener(loc)
        elif event.key() == QtCore.Qt.Key_Backspace:
            loc = os.path.dirname(self.location)
            self.navigate(loc)
        else:
            super().keyPressEvent(event)
            event.ignore()

    def load_tab(self, loc=None, forced=False):
        """Loads a tab if not already loaded or is stale."""
        logger.debug(f"Invoked by {sys._getframe().f_back.f_code.co_name}")
        if loc is None:
            loc = self.location
        if not os.path.isdir(loc):
            logger.debug(f"{loc} isn't a directory")
            Pub.notify("App", f"{loc} isn't a directory.")
            return
        if (forced and self._loading is False) or loc != self.location \
                or self.model.last_read < os.stat(loc).st_mtime:
            if not forced:
                self.filter_text = ""
            self.hv.updateCheckState(0)  # Uncheck main checkbox
            self._loading = True
            self.model.list_dir(loc)
            try:
                free_disk = humansize(shutil.disk_usage(loc)[2])
            except OSError:
                free_disk = ""
            self.status_info = f"Files: {self.model.fcount}, Dirs: " \
                f"{self.model.dcount} Total: {humansize(self.model.total)} " \
                f"Free: {free_disk}"
            if self.vtype == NavView.Details:
                self.tv.sortByColumn(self.sort_column, self.sort_order)
            self._loading = False
            if self.location != os.path.abspath(loc):
                self.view.clearSelection()
                self.location = os.path.abspath(loc)
                self.location_changed.emit(self.location)

    def change_detected(self, evt):
        """Invokes appropriate methods to add/update/remove listed files."""
        logger.debug(f"Invoked by {sys._getframe().f_back.f_code.co_name}")
        name = os.path.basename(evt.src_path)
        logger.debug(f"{name} {evt.event_type}")
        if evt.event_type == "deleted":
            logger.debug(f"{evt.src_path} deleted in {self.location}")
            self.model.remove_row(name)
        elif evt.event_type == "created":
            logger.debug(f"{evt.src_path} created in {self.location}")
            self.model.insert_row(name)
        elif evt.event_type == "moved":
            logger.debug(f"{self.location}: Moved {evt.src_path} to "
                         f"{evt.dest_path}")
            new_name = os.path.basename(evt.dest_path)
            self.model.rename_row(name, new_name)
        elif evt.event_type == "modified":
            logger.debug(f"{self.location}: {evt.src_path} Modified")
            self.model.update_row(name)
        # selstat = len(self.view.selectionModel().selectedIndexes())
        selstat = len(self.view.selectionModel().selectedIndexes())
        if selstat:
            selcount, selsize = self.model.get_selection_stats()
            selinfo = f" Selected: {selcount} : " \
                      f"{humansize(selsize)}"
        else:
            selinfo = ""
        self.status_info = f"Files: {self.model.fcount}, Dirs: " \
            f"{self.model.dcount} Total: {humansize(self.model.total)} " \
            f"Free: {humansize(shutil.disk_usage(self.location)[2])} {selinfo}"

    def sortIndicatorChanged(self, logicalIndex, sortOrder):
        """Remembers the sorted column and order."""
        self.sort_column = logicalIndex
        self.sort_order = sortOrder

    def rename_file(self):
        """Invokes inline renaming of the current file."""
        index = self.view.currentIndex()
        if not index:
            return
        self.view.edit(index)

    def trash(self):
        """Delete the current list of selected files to trash."""
        files = [self.proxy.itemData(index).get(0)
                 for index in self.view.selectionModel().selectedIndexes()]
        for f in files:
            fullname = os.path.join(self.location, f)
            try:
                send2trash(fullname)
                self.model.remove_row(f)
            except OSError:
                logger.error(f"Error deleting file", exc_info=True)
                Pub.notify("App", f"{self.pid}: Error deleting file",
                           exc_info=True)

    def delete(self):
        """Permanently delete the currently selected files."""
        files = [os.path.join(self.location, self.proxy.itemData(index).get(0))
                 for index in self.view.selectionModel().selectedIndexes()]
        for f in files:
            try:
                if os.path.isdir(f):
                    shutil.rmtree(f, onerror=self.remove_readonly)
                else:
                    os.unlink(f)
            except FileNotFoundError:
                logger.error(f"{f} not found")
                Pub.notify(f"App", f"{self.pid}: {f} not found.")

    def del_dir_up(self):
        """Deletes the current directory and goes up one directory."""
        d = self.location
        new_location = str(pathlib.PurePath(d).parent)
        try:
            send2trash(d)
            self.navigate(new_location)
        except FileNotFoundError:
            logger.error(f"{d} not found")
            Pub.notify("App.{self.pid}.Tab", f"{self.pid}: {d} not found.")

    def remove_readonly(self, func, path, _):
        "Clear the readonly bit and reattempts the removal."
        os.chmod(path, stat.S_IWRITE)
        func(path)

    def new_file(self, kind):
        """Creates new file or folder."""
        kind = kind.title()
        if kind == "Folder":
            filename = "new_folder"
        else:
            filename = "new_file"
        inc = ''
        while os.path.exists(filename + str(inc)):
            if inc:
                inc = f"({int(inc[1:-1])+1})"
            else:
                inc = "(1)"
        filename = f"{filename}{inc}"
        try:
            if kind == "Folder":
                os.makedirs(filename)
            else:
                os.mknod(filename)
            Pub.notify("App", f"{self.pid}: {kind} - {filename} created")
        except OSError:
            logger.error(f"Error creating {filename}", exc_info=True)
            Pub.notify("App", f"{self.pid}: Error creating {filename}")

    def copy(self, cut=False):
        """Cut/Copy files to clipboard."""
        files = [QtCore.QUrl.fromLocalFile(
            os.path.join(self.location, self.proxy.itemData(index).get(0)))
                 for index in self.view.selectionModel().selectedIndexes()]
        mime_data = self.proxy.mimeData(self.selectedIndexes())
        if cut:
            data = b'1'  # same as QtCore.QByteArray(0, '1')
            mime_data.setData("application/x-kde-cutselection", data)
            data = b'cut'
            mime_data.setData("x-special/gnome-copied-files", data)
        mime_data.setUrls(files)
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setMimeData(mime_data)

    def paste(self):
        """Pastes files from clipboard."""
        clipboard = QtWidgets.QApplication.clipboard()
        # check if cut or copy
        # x-kde-cutselection: is 1 if cut else 0
        # x-special/gnome-copied-files: has cut or copy mentioned
        logger.debug(clipboard.mimeData().formats())
        gnome_op = clipboard.mimeData().data(
            'x-special/gnome-copied-files').split(b'\n')[0]
        gnome_cut = True if gnome_op == b'cut'else False
        kde_op = clipboard.mimeData().data('application/x-kde-cutselection')
        kde_cut = True if kde_op == b'1' else False
        cut = True if kde_cut or gnome_cut else False
        logger.debug(f"Files were cut: {cut}")
        urls = [QtCore.QUrl.toLocalFile(url)
                for url in clipboard.mimeData().urls()]
        logger.debug(f"Paste {urls}")
        if not urls:
            return

        if cut:
            act = "move"
        else:
            act = "copy"
        self.t = threading.Thread(target=self.copier,
                                  args=(act, urls, self.location))
        self.t.start()

    def copier(self, act, sources, dest):
        """Invokes the copier in separate process."""
        Nav.copy_jobs += 1
        process = subprocess.Popen(
                    ['python3', Nav.copier, act] + sources + [dest])
        process.wait()
        Nav.copy_jobs -= 1
        logger.info(f"{act} {sources} {dest} -> completed")

    def startDrag(self, supported_actions):
        """Reimplemented to handle drag."""
        drag = QtGui.QDrag(self)
        t = [QtCore.QUrl.fromLocalFile(
                f"{self.location}{os.sep}{self.proxy.itemData(index).get(0)}")
             for index in self.view.selectionModel().selectedIndexes()]
        mime_data = self.proxy.mimeData(self.selectedIndexes())
        mime_data.setUrls(t)
        logger.debug(f"Dragging: {mime_data.urls()}")
        drag.setMimeData(mime_data)
        drag.exec_()

    def dragEnterEvent(self, event):
        """Reimplemented to handle drag"""
        logger.debug("startDrag")
        if self.rubberBand.isVisible:
            logger.debug("return")
            event.accept()
            return
        m = event.mimeData()
        if m.hasUrls():
            logger.debug(f"{event.mimeData().urls()}")
            event.accept()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        """Reimplemented to handle drag"""
        # event.setDragDropMode(QtGui.QAbstractItemView.InternalMove)
        event.setDropAction(QtCore.Qt.CopyAction)
        event.accept()

    def dropEvent(self, event):
        """Reimplemented to handle drop"""
        m = event.mimeData()
        if m.hasUrls():
            logger.debug(f"Dropping urls: {m.urls()}")
            links = []
            drop_loc = self.proxy.data(self.view.indexAt(event.pos()))
            if drop_loc is None:
                drop_loc = self.location
            else:
                drop_loc = os.path.join(self.location, drop_loc)
                # if dropped on file, go back to parent folder
                if not os.path.isdir(drop_loc):
                    drop_loc = self.location
            logger.debug(f"Drop Location: {drop_loc}")
            copylist = []
            for url in m.urls():
                links.append(str(url.toLocalFile()))

            for link in links:
                logger.debug(f"Copying {link} to {drop_loc}")
                try:
                    basename = os.path.basename(link)
                    os.rename(link, f"{drop_loc}{os.sep}{basename}")
                except OSError:
                    logger.error(f"{self.location}: It's on different mount. "
                                 "Copying", exc_info=True)
                    copylist.append(link)

            if copylist:
                self.t = threading.Thread(target=self.copier,
                                          args=("copy", copylist, drop_loc))
                self.t.start()

    def handledrop(self, links):
        """Reimplemented to handle drop"""
        for url in links:
            if os.path.exists(url):
                logger.debug(url)

    def get_selected_items(self):
        """Returns list of selected item."""
        files = [os.path.join(self.location, self.proxy.itemData(index).get(0))
                 for index in self.view.selectionModel().selectedIndexes()]
        return files

    def columns_moved(self, ind, old, new):
        """Capture the new visual indices for each of the columns."""
        for idx, h in enumerate(self.header):
            h.position = self.hv.visualIndex(idx)

    def columns_visibility_changed(self, idx, cap, visible):
        """Update row height if Thumnails column visibility is changed."""
        if cap == "Thumbnails":
            if visible:
                self.tv.verticalHeader().setDefaultSectionSize(128)
            else:
                self.tv.verticalHeader().setDefaultSectionSize(20)
