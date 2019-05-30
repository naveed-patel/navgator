import collections
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import threading
from dataclasses import dataclass
from PyQt5 import QtWidgets, QtCore, QtGui
from send2trash import send2trash
from .breadcrumbs import NavBreadCrumbsBar
from .helper import logger, humansize
from .pub import Pub
from .model import NavItemModel
from .custom import NavCheckBoxDelegate, NavSortFilterProxyModel, NavHeaderView
from .core import Nav


@dataclass
class NavColumn:
    caption: str
    size: int
    visible: bool = True


class NavTab(QtWidgets.QFrame):
    """Class to handle base skeleton for tabs."""
    location_changed = QtCore.pyqtSignal(str)

    def __init__(self, tab_info, parent_id):
        super().__init__()
        self.bcbar = NavBreadCrumbsBar("/")
        self.tab = NavList(tab_info, parent_id)
        self.bcbar.clicked.connect(self.tab.navigate)
        lyt = QtWidgets.QVBoxLayout()
        lyt.setSpacing(0)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.addWidget(self.bcbar)
        lyt.addWidget(self.tab)
        self.setLayout(lyt)


class NavList(QtWidgets.QTableView):
    location_changed = QtCore.pyqtSignal(str)
    status_updated = QtCore.pyqtSignal(str)

    def __init__(self, tab_info, parent_id):
        self.mutex = QtCore.QMutex()
        super().__init__()
        self.pid = parent_id
        self.setWordWrap(False)
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
        self.selsize = 0
        self._loading = False
        self.rubberBand = QtWidgets.QRubberBand(
            QtWidgets.QRubberBand.Rectangle, self)
        try:
            self.sort_column = int(tab_info["sort_column"])
        except (KeyError, TypeError):
            self.sort_column = 0
        try:
            self.sort_order = int(tab_info["sort_order"])
        except (KeyError, TypeError):
            self.sort_order = 0
        self.setAlternatingRowColors(True)
        self.inline_rename = False
        self.setSelectionBehavior(self.SelectItems)
        self.setSortingEnabled(True)
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditKeyPressed)

        self.headers = [
            NavColumn("Name", 300),
            NavColumn("Ext", 50),
            NavColumn("Size", 100),
            NavColumn("Modified", 150)
        ]
        self.vmod = NavItemModel(self, self.headers)
        self.hv = NavHeaderView(self.headers)
        self.setItemDelegateForColumn(0, NavCheckBoxDelegate(self))
        self.hv.setSectionsClickable(True)
        self.hv.setHighlightSections(True)
        self.hv.clicked.connect(self.updateModel)
        self.setHorizontalHeader(self.hv)
        self.setSortingEnabled(True)
        self.model = NavSortFilterProxyModel(self)
        self.model.setSourceModel(self.vmod)
        self.model.setFilterKeyColumn(0)
        self.setModel(self.model)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.selectionModel().selectionChanged.connect(self.rows_selected)
        self.horizontalHeader().sortIndicatorChanged.connect(
                                                    self.sortIndicatorChanged)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDrop &
                             ~QtWidgets.QAbstractItemView.InternalMove)
        self.SelectionBehavior(1)
        self.SelectionMode(7)
        self.State(2)

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
        self.model.setFilterCaseSensitivity(False)
        self.model.setFilterRegExp(filter_text)
        for i in range(self.model.rowCount()):
            index = self.model.index(i, 0)
            if index not in self.selectionModel().selectedIndexes():
                self.model.setData(index, QtCore.Qt.Unchecked,
                                   QtCore.Qt.CheckStateRole)

    def mouseDoubleClickEvent(self, e):
        """Reimplemented to handle mouse double click event."""
        index = self.indexAt(e.pos())
        if index == self.currentIndex():
            item = self.model.itemData(index).get(0)
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
            self.history = self.history[-63:]
            self.future.clear()

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

    def rows_selected(self, sel, desel):
        """Handle row (de)selections."""
        # logger.debug(f"Caller: {sys._getframe().f_back.f_code.co_name}")
        # Workaround to prevent random deselection on file deletion
        if sys._getframe().f_back.f_code.co_name == "__init__":
            logger.debug(f"Ignoring row (de)selection. Workaround.")
            return
        for index in sel.indexes():
            self.model.setData(index, QtCore.Qt.Checked,
                               QtCore.Qt.CheckStateRole)
            try:
                stats = os.lstat(os.path.join(self.location,
                                 str(self.model.itemData(index).get(0))))
                self.selsize += stats.st_size
            except FileNotFoundError:
                logger.error(f"{self.model.itemData(index).get(0)} not found")
        for index in desel.indexes():
            if not self.model.itemData(index):
                continue
            # logger.debug(f"Deselected: {self.model.itemData(index).get(0)}")
            if self.filter_text == "":
                self.model.setData(index, QtCore.Qt.Unchecked,
                                   QtCore.Qt.CheckStateRole)
            try:
                stats = os.lstat(os.path.join(
                            self.location, self.model.itemData(index).get(0)))
                self.selsize -= stats.st_size
            except FileNotFoundError:
                logger.error(f"{self.model.itemData(index).get(0)} not found")
            except TypeError:
                logger.error(f"Type error for {self.model.itemData(index)}")

        if self.selectionModel().selectedIndexes():
            selstat = len(self.selectionModel().selectedIndexes())
            selinfo = f"Selected: {selstat} : {humansize(self.selsize)}"
            if (selstat >= self.model.rowCount()):
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
            self.selectColumn(index)
        else:
            self.clearSelection()

    def invert_selection(self):
        """Toggles (de)selection of items in current listing."""
        for i in range(self.model.rowCount()):
            ix = self.model.index(i, 0)
            self.selectionModel().select(ix, QtCore.QItemSelectionModel.Toggle)

    def mousePressEvent(self, event):
        """Reimplemented for custom handling."""
        self.origin = event.pos() + self._offset
        self._modifier = event.modifiers()
        if self.indexAt(self.origin).column() != 0:
            self._selection = self.selectionModel().selection()
            self.rubberBand.setGeometry(QtCore.QRect(self.origin,
                                                     QtCore.QSize()))
            self.rubberBand.show()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Reimplemented for custom handling."""
        if self.rubberBand.isVisible():
            pos = event.pos() + self._offset
            self.rubberBand.setGeometry(
                QtCore.QRect(self.origin, pos).normalized())
            rect = self.rubberBand.geometry()
            tl = rect.topLeft() - self._offset
            br = rect.bottomRight() - self._offset
            qis = QtCore.QItemSelection(self.indexAt(tl), self.indexAt(br))
            mode = QtCore.QItemSelectionModel.ClearAndSelect
            if self._modifier == QtCore.Qt.ControlModifier:
                mode = QtCore.QItemSelectionModel.Clear | \
                       QtCore.QItemSelectionModel.Toggle
                qis.merge(self._selection, mode)
            if self._modifier == QtCore.Qt.ShiftModifier:
                qis.merge(self._selection, mode)
            self.selectionModel().select(qis, mode)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Reimplement for custom handling."""
        # Unset selection if selection rectangle was drawn and hide rectangle
        if self.rubberBand.isVisible():
            self.rubberBand.hide()
            self._selection = None
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        """Reimplemented keyPressEvent for custom handling."""
        if event.key() == QtCore.Qt.Key_Return:
            index = self.currentIndex()
            item = self.model.itemData(index).get(0)
            if self.state() != QtWidgets.QAbstractItemView.EditingState:
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
        if (forced and self._loading is False) or loc != self.location \
                or self.vmod.last_read < os.stat(loc).st_mtime:
            if not forced:
                self.filter_text = ""
            self.hv.updateCheckState(0)  # Uncheck main checkbox
            self._loading = True
            self.vmod.list_dir(loc)
            self.status_info = f"Files: {self.vmod.fcount}, Dirs: " \
                               f"{self.vmod.dcount} Total: " \
                               f"{humansize(self.vmod.total)}"
            self.sortByColumn(self.sort_column, self.sort_order)
            self._loading = False
            if self.location != os.path.abspath(loc):
                self.location = os.path.abspath(loc)
                self.location_changed.emit(self.location)

    def change_detected(self, evt):
        """Invokes appropriate methods to add/update/remove listed files."""
        logger.debug(f"Invoked by {sys._getframe().f_back.f_code.co_name}")
        name = os.path.basename(evt.src_path)
        logger.debug(f"{name} {evt.event_type}")
        if evt.event_type == "deleted":
            logger.debug(f"{evt.src_path} deleted in {self.location}")
            self.vmod.remove_row(name)
        elif evt.event_type == "created":
            logger.debug(f"{evt.src_path} created in {self.location}")
            self.vmod.insert_row(name)
        elif evt.event_type == "moved":
            logger.debug(f"{self.location}: Moved {evt.src_path} to "
                         f"{evt.dest_path}")
            new_name = os.path.basename(evt.dest_path)
            self.vmod.rename_row(name, new_name)
        elif evt.event_type == "modified":
            logger.debug(f"{self.location}: {evt.src_path} Modified")
            self.vmod.update_row(name)
        self.status_info = f"Files: {self.vmod.fcount}, Dirs: " \
            f"{self.vmod.dcount} Total: {humansize(self.vmod.total)}"

    def sortIndicatorChanged(self, logicalIndex, sortOrder):
        """Remembers the sorted column and order."""
        self.sort_column = logicalIndex
        self.sort_order = sortOrder

    def rename_file(self):
        """Invokes inline renaming of the current file."""
        index = self.currentIndex()
        if not index:
            return
        item = self.model.itemData(index).get(0)
        logger.debug(f"Rename {item} at {index.row()} {index}")
        self.edit(index)
        self.inline_rename = item

    def closeEditor(self, editor, hint):
        """Re-implemented closeEditor to wrap up inline rename."""
        if hint == QtWidgets.QAbstractItemDelegate.NoHint:
            QtWidgets.QTableView.closeEditor(
                self, editor, QtWidgets.QAbstractItemDelegate.SubmitModelCache)
        else:
            QtWidgets.QTableView.closeEditor(self, editor, hint)
            new_name = editor.text()
            logger.debug(f"Rename {self.inline_rename} to {new_name}")
            if os.path.exists(f"{new_name}"):
                logger.error(f"{self.location}: {new_name} - Already exists")
                Pub.notify("App", f"{self.pid}: {new_name} - Already exists.")
            else:
                logger.info(f"{self.location}: Rename {self.inline_rename} to "
                            f"{new_name}")
                try:
                    os.rename(self.inline_rename, new_name)
                    Pub.notify(f"App.{self.pid}.Tab.Files.Renamed",
                               f"{self.pid}: {self.inline_rename} "
                               f"renamed to {new_name}")
                except OSError:
                    logger.error(f"{self.location}: Error renaming from "
                                 f"{self.inline_rename} to {new_name}",
                                 exc_info=True)
                    Pub.notify("App", f"{self.pid}: Error renaming.")
                    self.vmod.rename_row(new_name, self.inline_rename)

    def trash(self):
        """Delete the current list of selected files to trash."""
        files = [os.path.join(self.location, self.model.itemData(index).get(0))
                 for index in self.selectionModel().selectedIndexes()]
        for f in files:
            send2trash(f)

    def delete(self):
        """Permanently delete the currently selected files."""
        files = [os.path.join(self.location, self.model.itemData(index).get(0))
                 for index in self.selectionModel().selectedIndexes()]
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
            os.path.join(self.location, self.model.itemData(index).get(0)))
                 for index in self.selectionModel().selectedIndexes()]
        mime_data = self.model.mimeData(self.selectedIndexes())
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
                f"{self.location}{os.sep}{self.model.itemData(index).get(0)}")
             for index in self.selectionModel().selectedIndexes()]
        mime_data = self.model.mimeData(self.selectedIndexes())
        mime_data.setUrls(t)
        logger.debug(f"Dragging: {mime_data.urls()}")
        drag.setMimeData(mime_data)
        drag.exec_()

    def dragEnterEvent(self, event):
        """Reimplemented to handle drag"""
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
            drop_loc = self.model.data(self.indexAt(event.pos()))
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
        files = [os.path.join(self.location, self.model.itemData(index).get(0))
                 for index in self.selectionModel().selectedIndexes()]
        return files
