import os
import pathlib
from PyQt5 import QtGui, QtCore, QtWidgets
from .core import Nav
from .helper import logger


class NavBreadCrumbMenu(QtWidgets.QLabel):
    """A class to present drop down menu on crumbs down arrow click."""
    open_location = QtCore.pyqtSignal("QString")
    arrow_right_icon = arrow_down_icon = folder_icon = None

    def __init__(self, path):
        super().__init__()
        self.cwd = QtCore.QDir(path)
        if self.arrow_right_icon is None:
            self.__class__.arrow_right_icon = QtGui.QIcon.fromTheme(
                "arrow-right").pixmap(QtCore.QSize(16, 16))
            self.__class__.arrow_down_icon = QtGui.QIcon.fromTheme(
                "arrow-down").pixmap(QtCore.QSize(16, 16))
            self.__class__.folder_icon = QtGui.QIcon.fromTheme("folder")
        self.setPixmap(self.arrow_right_icon)
        self.menu = QtWidgets.QMenu()
        self.menu.setStyleSheet("menu-scrollable: 1;")
        self.menu.aboutToHide.connect(self.onMenuHidden)

    def mousePressEvent(self, event):
        """Populates the drop down menu on arrow button click."""
        self.menu.clear()
        self.cwd.setFilter(QtCore.QDir.NoDotAndDotDot | QtCore.QDir.Dirs)
        if self.cwd.entryList():
            for d in self.cwd.entryList():
                action = self.menu.addAction(self.folder_icon, d)
                action.triggered.connect(self.onMenuItemClicked)
        else:
            action = self.menu.addAction("No folders")
            action.setDisabled(True)

        self.setPixmap(self.arrow_down_icon)
        self.menu.popup(self.mapToGlobal(self.frameRect().bottomLeft()))
        event.accept()

    def onMenuHidden(self):
        """Reverts back the down arrow to right arrow."""
        self.setPixmap(self.arrow_right_icon)

    def onMenuItemClicked(self):
        """Emits a clicked event with location to navigate to."""
        self.open_location.emit(self.cwd.filePath(self.sender().text()))


class NavBreadCrumb(QtWidgets.QLabel):
    """A class to present crumbs on the breadcrumbs bar."""
    open_location = QtCore.pyqtSignal("QString")
    root_icon = None

    def __init__(self, path, current=False):
        super().__init__()
        self.cwd = QtCore.QDir(path)
        if self.root_icon is None:
            self.__class__.root_icon = QtGui.QIcon.fromTheme(
                "drive-harddisk").pixmap(QtCore.QSize(16, 16))

        if self.cwd.isRoot():
            self.setPixmap(self.root_icon)
        else:
            self.setText(self.cwd.dirName())

        if current:
            self.setStyleSheet("QtWidgets.QLabel { font-weight: bold; }")

    def mousePressEvent(self, event):
        """Emits a clicked event with location to navigate to."""
        self.open_location.emit(self.cwd.absolutePath())
        event.accept()


class NavBreadCrumbsBar(QtWidgets.QFrame):
    """A simple class to serve a breadcrumbs bar"""
    clicked = QtCore.pyqtSignal("QString")
    cMenu = None  # common contextMenu across class

    def __init__(self, loc=None):
        super().__init__()
        self.cwd = ""
        lyt = QtWidgets.QHBoxLayout(self)
        lyt.setSizeConstraint(QtWidgets.QLayout.SetMaximumSize)
        self.setLayout(lyt)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored,
                           QtWidgets.QSizePolicy.Fixed)
        if self.cMenu is None:
            self.__class__.cMenu = QtWidgets.QMenu()
            items = [
                Nav.actions["copy_path"],
                Nav.actions["paste_and_go"],
            ]
            Nav.build_menu(self, items, self.cMenu)
        if loc:
            self.create_crumbs(loc)

    def create_crumbs(self, path):
        """Breaks the path into crumbs alongwith dropdown."""
        if not path:
            return
        # Identify common path
        if self.cwd:
            # logger.debug(self.layout().count())
            common = os.path.commonpath([self.cwd, path])
            if common.endswith(os.sep):
                common = common[:-1]
        else:
            common = None
        self.cwd = path
        # logger.debug(f"common: {common}")

        # Remove crumbs which are now invalid. Preserve common ones
        if self.layout().count():
            for i in reversed(range(self.layout().count())):
                try:
                    wid = self.layout().itemAt(i).widget()
                    logger.debug(wid)
                    if common == wid.cwd.absolutePath():
                        break
                    wid.close()
                    wid.deleteLater()
                except AttributeError:
                    self.layout().removeItem(self.layout().itemAt(i))

        if not common:
            count = 0
        else:
            count = len(pathlib.PurePath(common).parts)

        comps = pathlib.PurePath(path).parts
        # Add the uncommon crumbs to serve the breadcrumb bar
        for c in range(count, len(comps)):
            try:
                if not common.endswith(os.sep):
                    common += os.sep
                if comps[c] != os.sep:
                    common += comps[c]
            except Exception:
                continue
            crumb = NavBreadCrumb(common)
            crumb.open_location.connect(self.crumb_clicked)
            menu = NavBreadCrumbMenu(common)
            menu.open_location.connect(self.crumb_clicked)
            self.layout().addWidget(crumb)
            self.layout().addWidget(menu)
        self.layout().addStretch()

    def crumb_clicked(self, loc):
        """Emits a clicked event with location to navigate to."""
        self.clicked.emit(loc)

    def copy_path(self):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self.cwd)

    def paste_and_go(self):
        clip = QtWidgets.QApplication.clipboard().text()
        # if os.path.isdir(clip):
        self.clicked.emit(clip)

    def contextMenuEvent(self, event):
        # child = self.childAt(event.pos())
        self.cMenu.exec_(event.globalPos())
