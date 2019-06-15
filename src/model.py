import os
import pathlib
import sys
import time
from PyQt5 import QtCore, QtWidgets, QtGui
from PIL import Image
from PIL.ImageQt import ImageQt
from .core import NavStates
from .helper import logger, humansize, to_bytes
from .pub import Pub


class NavIcon:
    """Icon store for files."""
    icon_map = {}
    iconProvider = QtWidgets.QFileIconProvider()

    @classmethod
    def get_icon(cls, path, ext=None):
        """Return icon from cache or pull it into the cache and return."""
        if ext is None:
            if os.path.isfile(path):
                ext = pathlib.Path(path).suffix
        if ext not in cls.icon_map:
            file_info = QtCore.QFileInfo(path)
            icon = cls.iconProvider.icon(file_info)
            if ext is None:
                return icon
            cls.icon_map[ext] = icon
        return cls.icon_map[ext]


class NavItemModel(QtCore.QAbstractItemModel):
    """Custom File System Model for this application."""
    tw = th = 128

    def __init__(self, parent, header, *args, mylist=[]):
        super().__init__(parent, *args)
        self.parent = parent
        self.pid = self.parent.pid
        self.header = header
        self.files = []
        self.fcount = self.dcount = self.total = 0
        self.last_read = 0
        self.state = -1
        self.pixmap_cache = {}

    def list_dir(self, d: str):
        """Updates the model with director listing."""
        logger.debug(f"Invoked by {sys._getframe().f_back.f_code.co_name}")
        if not os.path.exists(d):
            self.files = []
            Pub.notify(f"App.{self.pid}.Tabs",
                       f"{self.pid}: {d} does not exist")
            return
        try:
            os.chdir(d)
        except PermissionError:
            self.status_info = f"Permission Denied for {d}"
            return False
        except NotADirectoryError:
            logger.error(f"{d} is not a directory")
            return False

        self.files = []
        self.fcount = self.dcount = self.total = self.selsize = 0
        cur_sel = []
        logger.debug(f"Listing {d} - {len(cur_sel)} selected")
        self.layoutAboutToBeChanged.emit()
        with os.scandir(d) as it:
            self.last_read = os.stat(d).st_mtime
            for entry in it:
                if entry.is_file():
                    state = 0
                    ext = pathlib.Path(entry.name).suffix.lstrip('.')
                    self.fcount += 1
                    size = humansize(entry.stat().st_size)
                else:
                    state = NavStates.IS_DIR
                    ext = None
                    self.dcount += 1
                    size = None
                modified = str(time.strftime('%Y-%m-%d %H:%M',
                               time.localtime(entry.stat().st_mtime)))
                self.total += entry.stat().st_size
                if entry.name in cur_sel:
                    state |= NavStates.IS_SELECTED
                self.files.append([entry.name,
                                   ext, size, modified, state, ])
        self.layoutChanged.emit()

    def insert_row(self, new_item: str):
        """Inserts a new item to the model."""
        if new_item not in self.files:
            try:
                if os.path.isfile(new_item):
                    state = 0
                    ext = pathlib.Path(new_item).suffix.lstrip('.')
                    self.fcount += 1
                    stats = os.lstat(new_item)
                    size = humansize(stats.st_size)
                    self.total += stats.st_size
                else:
                    state = NavStates.IS_DIR
                    ext = None
                    self.dcount += 1
                    size = ''
                    stats = os.lstat(new_item)
                modified = str(time.strftime('%Y-%m-%d %H:%M',
                               time.localtime(stats.st_mtime)))
                new_pos = self.rowCount()
                self.beginInsertRows(QtCore.QModelIndex(), new_pos, new_pos)
                self.files.append([new_item, ext, size, modified, state])
                Pub.notify("App", f"{self.pid}: {new_item} was added.")
                self.endInsertRows()
                return True
            except FileNotFoundError:
                pass

    def update_row(self, upd_item: str):
        """Updates a row in the model."""
        for item in self.files:
            if item[0] == upd_item:
                ind = self.files.index(item)
                if item[self.state] & ~NavStates.IS_DIR:
                    try:
                        size = to_bytes(item[2])
                        self.total -= size
                    except Exception:
                        logger.debug(f"Error getting size for {upd_item}",
                                     exc_info=True)
                stats = os.lstat(upd_item)
                size = humansize(stats.st_size)
                self.total += stats.st_size
                self.layoutAboutToBeChanged.emit()
                self.files[ind][2] = size
                self.files[ind][3] = str(time.strftime('%Y-%m-%d %H:%M',
                                         time.localtime(stats.st_mtime)))
                self.layoutChanged.emit()
                self.last_read = os.stat(self.parent.location).st_mtime

                Pub.notify("App", f"{self.pid}: {upd_item} was modified.")
                return

    def rename_row(self, old_name: str, new_name: str):
        """Renames a row in the model."""
        for item in self.files:
            if item[0] == old_name:
                ind = self.files.index(item)
                self.files[ind][0] = new_name
                self.dataChanged.emit(self.createIndex(0, 0),
                                      self.createIndex(self.rowCount(0),
                                      self.columnCount(0)))
                self.last_read = os.stat(self.parent.location).st_mtime
                Pub.notify("App", f"{self.pid}: {old_name} was renamed to "
                           f"{new_name}.")
                return

    def remove_row(self, rem_item: str):
        """ Remove a row from the model."""
        for item in self.files:
            if rem_item == item[0]:
                if item[self.state] & NavStates.IS_DIR:
                    self.dcount -= 1
                else:
                    try:
                        size = to_bytes(item[2])
                        self.total -= size
                    except Exception:
                        logger.debug(f"Error getting size for {rem_item}",
                                     exc_info=True)
                    self.fcount -= 1
                if item[self.state] & NavStates.IS_SELECTED:
                    self.selcount -= 1
                    try:
                        self.selsize -= size
                    except UnboundLocalError:
                        pass
                index = self.files.index(item)
                self.beginRemoveRows(QtCore.QModelIndex(), index, index)
                self.files.pop(index)
                self.endRemoveRows()
                Pub.notify("App", f"{self.pid}: {rem_item} was deleted.")
                break
        return True

    def rowCount(self, parent=None):
        """Returns the no. of rows in current model."""
        return len(self.files)

    def columnCount(self, parent=None):
        """Returns the no. of rows in current model."""
        return len(self.header)

    def index(self, row, column, parent=None):
        """Re-implemented to return index of a row."""
        return QtCore.QAbstractItemModel.createIndex(self, row, column, row)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        """Returns data to be displayed in the model."""
        if not index.isValid():
            return None
        try:
            row = index.row()
            column = index.column()
            value = self.files[row][column]
            if role == QtCore.Qt.EditRole:
                return value
            elif column == 4:
                if role == QtCore.Qt.DecorationRole:
                    try:
                        im = Image.open(f"{self.parent.location}{os.sep}"
                                        f"{self.files[row][0]}")
                        im.thumbnail((self.tw, self.th), Image.ANTIALIAS)
                        # self.parent.setRowHeight(row, self.th)
                        return QtGui.QImage(ImageQt(im))
                    except Exception:
                        pass  # Ignore if thumbnails can't be generated
                    # if self.files[row][0] not in self.pixmap_cache:
                    #     self.pixmap_cache[self.files[row][0]] = \
                    #         QtGui.QPixmap(self.files[row][0])
                    # return QtGui.QImage(
                    #     self.pixmap_cache[self.files[row][0]]). \
                    #     scaled(128, 128, QtCore.Qt.KeepAspectRatio)
                # elif role == QtCore.Qt.SizeHintRole:
                #     return QtCore.QSize(128, 128)
                else:
                    return None
            elif role == QtCore.Qt.DisplayRole:
                return value
            elif column == 0 \
                    and role == QtCore.Qt.DecorationRole:
                return NavIcon.get_icon(self.files[row][0])
            elif role == QtCore.Qt.CheckStateRole:
                if column == 0:
                    if self.files[row][self.state] & NavStates.IS_SELECTED:
                        return QtCore.Qt.Checked
                    else:
                        return QtCore.Qt.Unchecked
        except IndexError:
            pass

    def headerData(self, column, orientation, role):
        """Return caption for the headers."""
        if orientation == QtCore.Qt.Horizontal \
                and role == QtCore.Qt.DisplayRole:
            try:
                return self.header[column].caption
            except IndexError:
                return ""
        return None

    def flags(self, index):
        """Re-implemented to allow checkbox on the name column and
        prevent selection on other columns."""
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled
        if index.column() == 0:
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | \
                QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEditable | \
                QtCore.Qt.ItemIsDragEnabled | QtCore.Qt.ItemIsDropEnabled
        else:
            return QtCore.Qt.ItemIsEnabled

    def setData(self, index, value, role):
        """Handles item (de)selection."""
        if not index.isValid():
            return False
        if role == QtCore.Qt.CheckStateRole:
            if value == QtCore.Qt.Checked:
                self.files[index.row()][self.state] |= NavStates.IS_SELECTED
                self.selsize += to_bytes(self.files[index.row()][2])
            else:
                self.files[index.row()][self.state] &= ~NavStates.IS_SELECTED
                self.selsize -= to_bytes(self.files[index.row()][2])
            # Emit signal to select row only if not invoked by it
            if sys._getframe().f_back.f_code.co_name == "__init__":
                self.dataChanged.emit(index, index)
            return True
        elif role == QtCore.Qt.EditRole:
            r = index.row()
            c = index.column()
            if c == 0:
                old = self.files[r][c]
                logger.debug(f"Rename {old} to {value}")
                self.rename(old, value)
        # self.dataChanged.emit(index, index)
        return False

    def rename(self, old, new):
        if os.path.exists(f"{new}"):
            logger.error(f"{self.parent.location}: {new} - Exists")
            Pub.notify("App", f"{self.pid}: {new} - exists.")
        else:
            logger.info(f"{self.parent.location}: Rename {old} to {new}")
            try:
                os.rename(old, new)
                Pub.notify(f"App.{self.pid}.Tab.Files.Renamed",
                           f"{self.pid}: {old} renamed to {new}")
            except OSError:
                logger.error(f"{self.parent.location}: Error renaming "
                             f"from {old} to {new}", exc_info=True)
                Pub.notify("App", f"{self.pid}: Error renaming.")

    def get_selection_stats(self):
        """Get stats of selected items"""
        self.selsize = self.selcount = 0
        for item in self.files:
            if item[self.state] & NavStates.IS_SELECTED & ~NavStates.IS_DIR:
                self.selsize += to_bytes(item[2])
                self.selcount += 1
        return self.selcount, self.selsize
