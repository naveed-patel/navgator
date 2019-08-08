import os
import pathlib
import sys
import time
import datetime
from PyQt5 import QtCore, QtWidgets, QtGui
from PIL import Image
from PIL.ImageQt import ImageQt
from .core import NavStates, NavView, Nav
from .helper import logger, humansize
from .pub import Pub
from .navtrash import NavTrash

NAME = 0
EXT = 1
SIZE = 2
MODIFIED = 3
PATH = 4
DELETED = 5
FULLNAME = 6
THUMBNAIL = 7
STATE = -1


class NavIcon:
    """Icon store for files."""
    icon_map = {}
    iconProvider = QtWidgets.QFileIconProvider()

    @classmethod
    def get_icon(cls, path, ext=None):
        """Return icon from cache or pull it into the cache and return."""
        if ext is None:
            ext = pathlib.Path(path).suffix
        if ext not in cls.icon_map:
            # logger.debug(f"Fresh Icon for {path} {ext}")
            file_info = QtCore.QFileInfo(path)
            icon = cls.iconProvider.icon(file_info)
            if ext is None:
                return icon
            cls.icon_map[ext] = icon
        return cls.icon_map[ext]


class NavItemModel(QtCore.QAbstractItemModel):
    """Custom File System Model for this application."""
    tw = th = 64

    def __init__(self, parent, header, *args, mylist=[]):
        super().__init__(parent, *args)
        self.parent = parent
        self.pid = self.parent.pid
        self.header = header
        # logger.debug(self.header)
        self.files = []
        self.fcount = self.dcount = self.total = 0
        self.last_read = 0
        self._loading = False
        self.location = None

    def model_size(self, width, height):
        """Set the size for icons and thumbnails."""
        logger.debug(f"Invoked by {sys._getframe().f_back.f_code.co_name}")
        self.tw = width
        self.th = height

    # def update_header(self, header):
    #     """Update the model header"""
    #     self.header = header

    def is_changed(self, loc, last_read):
        for d in loc.split(";"):
            try:
                if last_read < os.stat(d).st_mtime:
                    return True
            except FileNotFoundError:
                return True
        return False

    def load_tab(self, loc, forced=False):
        """Loads a tab if not already loaded or is stale."""
        # logger.debug(f"Invoked by {sys._getframe().f_back.f_code.co_name}")
        # logger.debug(f"Navigating to {loc} and current is {self.location}")
        if loc is None or loc != self.location:
            self.last_read = 0
        #     loc = self.location
        if (forced and self._loading is False) or loc != self.location \
                or self.is_changed(loc, self.last_read):
            logger.debug("Loading required")
            self.location = loc
            self._loading = True
            # if loc != "trash":
            self.list_dirs(loc)
            # else:
            #     self.list_trash()
            self._loading = False
            return True
        logger.debug("Loading Skipped")
        return False

    # def list_trash(self):
    #     self.files = []
    #     self.fcount = self.dcount = self.total = self.selsize = 0
    #     self.last_read = datetime.datetime.now().timestamp()
    #     for tf in NavTrash.get_trash_folders():
    #         self.list_dir(tf, 1)

    def list_dirs(self, ds):
        """Invokes list_dir for each dir in  the list"""
        logger.debug(f"Invoked by {sys._getframe().f_back.f_code.co_name}")
        self.files = []
        self.fcount = self.dcount = self.total = self.selsize = 0
        self.last_read = datetime.datetime.now().timestamp()
        for d in ds.split(";"):
            self.list_dir(d)

    def list_dir(self, d: str, kind=0):
        """Updates the model with directory listing."""
        logger.debug(f"Invoked by {sys._getframe().f_back.f_code.co_name}")
        if not os.path.exists(d):
            # self.files = []
            self.layoutAboutToBeChanged.emit()
            self.layoutChanged.emit()
            Pub.notify(f"App.{self.pid}.Tabs",
                       f"{self.pid}: {d} does not exist")
            return
        # try:
        #     os.chdir(d)
        # except PermissionError:
        #     self.status_info = f"Permission Denied for {d}"
        #     return False
        # except NotADirectoryError:
        #     logger.error(f"{d} is not a directory")
        #     return False
        self.layoutAboutToBeChanged.emit()
        if kind:
            mp = pathlib.Path(f"{d}{os.sep}").parent
            ti = pathlib.Path(f"{d}{os.sep}info{os.sep}")
            d = pathlib.Path(f"{d}{os.sep}files")
        # else:
        #     self.files = []

        with os.scandir(d) as it:
            for entry in it:
                if entry.is_file():
                    state = 0
                    ext = pathlib.Path(entry.name).suffix.lstrip('.')
                    self.fcount += 1
                    size = entry.stat().st_size
                else:
                    state = NavStates.IS_DIR
                    ext = None
                    self.dcount += 1
                    size = 0

                modified = str(time.strftime('%Y-%m-%d %H:%M',
                               time.localtime(entry.stat().st_mtime)))
                self.total += entry.stat().st_size

                if kind:
                    info = f"{ti}{os.sep}{entry.name}.trashinfo"
                    # current = f"{d}{os.sep}{entry.name}"
                    with open(info, "r") as fh:
                        contents = fh.readlines()
                        for line in contents:
                            line = line.strip()
                            if line.startswith('DeletionDate='):
                                deleted = datetime.datetime.strptime(
                                        line, "DeletionDate=%Y-%m-%dT%H:%M:%S")
                            elif line.startswith('Path='):
                                origin = line[len('Path='):]
                                if not origin.startswith("/"):
                                    origin = f"{mp}{os.sep}{origin}"
                    self.files.append([entry.name, ext, size, modified, d,
                                       deleted, origin, state])
                else:
                    self.files.append([entry.name, ext, size, modified, d,
                                       state])
        self.layoutChanged.emit()

    def insert_row(self, new_item: str):
        """Inserts a new item to the model."""
        path = os.path.dirname(new_item)
        name = os.path.basename(new_item)
        if name not in self.files:
            try:
                if os.path.isfile(new_item):
                    state = 0
                    ext = pathlib.Path(new_item).suffix.lstrip('.')
                    self.fcount += 1
                    stats = os.lstat(new_item)
                    size = stats.st_size
                    self.total += size
                else:
                    state = NavStates.IS_DIR
                    ext = None
                    self.dcount += 1
                    size = 0
                    stats = os.lstat(new_item)
                modified = str(time.strftime('%Y-%m-%d %H:%M',
                               time.localtime(stats.st_mtime)))
                new_pos = self.rowCount()
                self.beginInsertRows(QtCore.QModelIndex(), new_pos, new_pos)
                self.files.append([name, ext, size, modified, path, state])
                Pub.notify("App", f"{self.pid}: {new_item} was added.")
                self.endInsertRows()
                return True
            except FileNotFoundError:
                pass

    def update_row(self, upd_item: str):
        """Updates a row in the model."""
        # path = os.path.dirname(upd_item)
        name = os.path.basename(upd_item)
        for item in self.files:
            if item[NAME] == name:
                ind = self.files.index(item)
                if item[STATE] & ~NavStates.IS_DIR:
                    try:
                        self.total -= item[SIZE]
                    except Exception:
                        logger.debug(f"Error getting size for {upd_item}",
                                     exc_info=True)
                try:
                    stats = os.lstat(upd_item)
                except FileNotFoundError as e:
                    # Deletion invoked modify.
                    # Ignore as deletion event will handle it
                    return
                self.layoutAboutToBeChanged.emit()
                self.files[ind][SIZE] = stats.st_size
                self.total += self.files[ind][SIZE]
                self.files[ind][MODIFIED] = str(time.strftime(
                    '%Y-%m-%d %H:%M', time.localtime(stats.st_mtime)))
                self.layoutChanged.emit()
                # try:
                #     self.last_read = os.stat(self.parent.location).st_mtime
                # except Exception:
                #     self.last_read = datetime.datetime.now().timestamp()
                self.last_read = datetime.datetime.now().timestamp()
                Pub.notify("App", f"{self.pid}: {upd_item} was modified.")
                return

    def rename_row(self, old_name: str, new_name: str):
        """Renames a row in the model."""
        for item in self.files:
            if item[NAME] == old_name:
                ind = self.files.index(item)
                self.files[ind][NAME] = new_name
                self.dataChanged.emit(self.createIndex(0, 0),
                                      self.createIndex(self.rowCount(0),
                                      self.columnCount(0)))
                # self.last_read = os.stat(self.parent.location).st_mtime
                self.last_read = datetime.datetime.now().timestamp()
                Pub.notify("App", f"{self.pid}: {old_name} was renamed to "
                           f"{new_name}.")
                return

    def remove_row(self, rem_item: str):
        """ Remove a row from the model."""
        if os.sep in rem_item:
            rem_item = os.path.basename(rem_item)
        for item in self.files:
            if rem_item == item[NAME]:
                if item[STATE] & NavStates.IS_DIR:
                    self.dcount -= 1
                else:
                    try:
                        self.total -= item[SIZE]
                    except Exception:
                        logger.debug(f"Error getting size for {rem_item}",
                                     exc_info=True)
                    self.fcount -= 1
                if item[STATE] & NavStates.IS_SELECTED:
                    self.selcount -= 1
                    # try:
                    self.selsize -= item[SIZE]
                    # except UnboundLocalError:
                    #     pass
                index = self.files.index(item)
                self.beginRemoveRows(QtCore.QModelIndex(), index, index)
                self.files.pop(index)
                self.endRemoveRows()
                # logger.debug(f"{item} removed from {index}")
                Pub.notify("App", f"{self.pid}: {rem_item} was deleted.")
                break
        return True

    def rowCount(self, parent=None):
        """Returns the no. of rows in current model."""
        return len(self.files)

    def columnCount(self, parent=None):
        """Returns the no. of rows in current model."""
        return len(self.header.keys())

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
            h = self.headerData(column, QtCore.Qt.Horizontal,
                                role=QtCore.Qt.DisplayRole)
            # logger.debug(f"called for {index} {row} {column} {value}")
            # if column == NAME:
            #     logger.debug(f"{value} {self.files[row][STATE]}")
            # if self.files[row][STATE] & NavStates.IS_FILTERED:
            #     return QtCore.QVariant
            if role == QtCore.Qt.EditRole:
                return value
            elif role == QtCore.Qt.DecorationRole:
                if h == "Thumbnails" or \
                        self.parent.vtype == NavView.Thumbnails:
                    try:
                        if self.parent.location != "trash":
                            im = Image.open(f"{self.parent.location}{os.sep}"
                                            f"{self.files[row][NAME]}")
                        else:
                            im = Image.open(self.files[row][FULLNAME])
                        im.thumbnail((self.tw, self.th), Image.ANTIALIAS)
                        return QtGui.QImage(ImageQt(im))
                    except Exception:
                        # Icon if thumbnails can't be generated
                        return NavIcon.get_icon(self.files[row][NAME],
                                                ext=self.files[row][EXT])
                elif column == NAME:
                    return NavIcon.get_icon(self.files[row][NAME],
                                            ext=self.files[row][EXT])
                else:
                    return None
            elif role == QtCore.Qt.DisplayRole:
                if column == SIZE:
                    return humansize(value)
                # logger.debug(f"returning {value} for {row} {column}")
                return value if h != "Thumbnails" else ""
            elif role == QtCore.Qt.CheckStateRole and column == NAME:
                if self.files[row][STATE] & NavStates.IS_SELECTED:
                    return QtCore.Qt.Checked
                else:
                    return QtCore.Qt.Unchecked
            # elif role == QtCore.Qt.SizeHintRole:
            #     return (QtCore.QSize(self.tw, self.th))
        except IndexError:
            pass

    def headerData(self, column, orientation, role):
        """Return caption for the headers."""
        if orientation == QtCore.Qt.Horizontal \
                and role == QtCore.Qt.DisplayRole:
            try:
                return list(self.header.values())[column].caption
            except IndexError:
                return ""
        return None

    def parent(self, index):
        return QtCore.QModelIndex()

    def flags(self, index):
        """Re-implemented to allow checkbox on the name column and
        prevent selection on other columns."""
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled
        if index.column() == NAME:
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
                self.files[index.row()][STATE] |= NavStates.IS_SELECTED
                self.selsize += self.files[index.row()][SIZE]
            else:
                self.files[index.row()][STATE] &= ~NavStates.IS_SELECTED
                self.selsize -= self.files[index.row()][SIZE]
            # Emit signal to select row only if not invoked by it
            if sys._getframe().f_back.f_code.co_name == "__init__":
                self.dataChanged.emit(index, index)
            return True
        elif role == QtCore.Qt.EditRole:
            r = index.row()
            c = index.column()
            if c == NAME:
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
            if item[STATE] & NavStates.IS_SELECTED & ~NavStates.IS_DIR:
                self.selsize += item[SIZE]
                self.selcount += 1
        return self.selcount, self.selsize

    def get_full_name(self, index):
        try:
            return self.files[index][PATH] + os.sep + self.files[index][NAME]
        except IndexError:
            return None


class NavSortFilterProxyModel(QtCore.QSortFilterProxyModel):
    """Subclassed to provide row numbers and sorting folders to top."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.filterString = ''
        self.filterFunctions = {}

    def headerData(self, section, orientation, role):
        """Reimplemented to provide row numbers for vertical headers."""
        # if display role of vertical headers
        if orientation == QtCore.Qt.Vertical and \
                role == QtCore.Qt.DisplayRole:
            return section + 1  # return the actual row number
        # Rely on the base implementation
        return super().headerData(section, orientation, role)

    def lessThan(self, left, right):
        """Reimplemented to sort folders to top."""
        l_data = self.sourceModel().files[left.row()]
        r_data = self.sourceModel().files[right.row()]
        sort_order = self.sortOrder()
        if Nav.conf["sort_folders_first"]:
            l_dir = l_data[STATE] & NavStates.IS_DIR
            r_dir = r_data[STATE] & NavStates.IS_DIR
            try:
                if l_dir > r_dir:
                    return sort_order == QtCore.Qt.AscendingOrder
                elif l_dir < r_dir:
                    return sort_order != QtCore.Qt.AscendingOrder
            except TypeError:
                return True
        try:
            return True if (l_data[left.column()] <= r_data[right.column()]) \
                else False
        except TypeError:
            return True if l_data[left.column()] is None else False

    def previous_index(self, index, cyclic=True):
        if self.rowCount() == 0 or ((not cyclic) and index <= 0):
            return None
        if index <= 0:
            return self.rowCount()-1
        return index - 1

    def next_index(self, index, cyclic=True):
        logger.debug(self.rowCount())
        if self.rowCount() == 0 or ((not cyclic) and
                                    index >= self.rowCount()-1):
            return None
        if index >= self.rowCount()-1:
            return 0
        return index + 1

    def get_full_name_at_row(self, index):
        ind = self.index(index, 0)
        return self.sourceModel().get_full_name(self.mapToSource(ind).row())

    def get_full_name(self, index):
        return self.sourceModel().get_full_name(self.mapToSource(index).row())
