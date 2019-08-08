from PyQt5 import QtWidgets, QtCore
from dataclasses import dataclass


@dataclass
class NavColumn:
    caption: str
    size: int
    position: int = -1
    visible: bool = True


class NavTree(QtWidgets.QTreeView):
    """Subclassed for easy instantiating trees across application."""
    def __init__(self):
        super().__init__()
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                           QtWidgets.QSizePolicy.Expanding)
        self.model = QtWidgets.QFileSystemModel(self)
        self.model.setRootPath("/")
        self.model.setResolveSymlinks(False)
        self.model.setFilter(QtCore.QDir.AllDirs | QtCore.QDir.NoDotAndDotDot)
        self.setModel(self.model)
        self.setRootIndex(self.model.index(None))
        self.hideColumn(1)
        self.hideColumn(2)
        self.hideColumn(3)
        self.setHeaderHidden(True)


class NavCheckBoxDelegate(QtWidgets.QStyledItemDelegate):
    """Delegate to handle checkbox toggle"""
    def __init__(self, parent, ind):
        self.parent = parent
        self.ind = ind
        super().__init__(parent)

    def editorEvent(self, event, model, option, index):
        """Check if checkbox was clicked and trigger the toggle."""
        if event.type() == QtCore.QEvent.MouseButtonPress \
                and event.button() == QtCore.Qt.LeftButton:
            offset = self.parent.hv.sectionPosition(self.ind)
            x = event.pos().x()
            if x > offset and x < offset + 20:
                self.parent.view.selectionModel().select(
                    index, QtCore.QItemSelectionModel.Toggle)
                return True
        return False


class NavItemSelectionModel(QtCore.QItemSelectionModel):
    """Subclassed to restrict selection to particular columns."""
    def __init__(self, model, selectable_columns=[0]):
        super().__init__(model)
        self.selectable_columns = selectable_columns

    def select(self, selection, selectionFlags):
        """Reimplemented to prevent selecting some columns."""
        if isinstance(selection, QtCore.QItemSelection):
            indexes = selection.indexes()
            for i in range(len(indexes)):
                index = indexes[i]
                if not index.column() in self.selectable_columns:
                    return
        elif not selection.column() in self.selectable_columns:
            return
        super().select(selection, selectionFlags)


class NavHeaderView(QtWidgets.QHeaderView):
    """Sub-classed to add a checkbox on header."""
    clicked = QtCore.pyqtSignal(int, bool)
    visibility_changed = QtCore.pyqtSignal(int, str, bool)
    # randomize = QtCore.pyqtSignal()

    def __init__(self, header, orientation=QtCore.Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.header = header
        self._x_offset = 3
        self._y_offset = 0
        self._width = self._height = 20
        self.cb_cols = 0
        self.isChecked = 0

    def resizeEvent(self, event):
        """Resize table as a whole, required to allow resizing."""
        super().resizeEvent(event)
        self.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        # column = 0
        # for column in range(0, self.count()):
        #     self.resizeSection(column, self.header[column].size)
        #     column += 1
        self.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.resizeSection(0, self.sectionSize(0))
        self.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        return

    def paintSection(self, painter, rect, index):
        """Draws a checkbox on the said column in the header."""
        painter.save()
        super().paintSection(painter, rect, index)
        painter.restore()
        self._y_offset = int((rect.height() - self._width) / 2.0)

        if index == self.cb_cols:
            option = QtWidgets.QStyleOptionButton()
            option.rect = QtCore.QRect(rect.x() + self._x_offset,
                                       rect.y() + self._y_offset,
                                       self._width, self._height)
            option.state = QtWidgets.QStyle.State_Enabled | \
                QtWidgets.QStyle.State_Active
            if self.isChecked == 2:
                option.state |= QtWidgets.QStyle.State_NoChange
            elif self.isChecked:
                option.state |= QtWidgets.QStyle.State_On
            else:
                option.state |= QtWidgets.QStyle.State_Off

            self.style().drawControl(QtWidgets.QStyle.CE_CheckBox, option,
                                     painter)

    def updateCheckState(self, state):
        """Updates the check state of the header checkbox."""
        self.isChecked = state
        self.viewport().update()

    def mousePressEvent(self, event):
        """Re-implemented to capture click on the header checkbox ."""
        index = self.logicalIndexAt(event.pos())
        if 0 <= index < self.count():
            x = self.sectionPosition(index) + self._x_offset
            if x < event.pos().x() < x + self._width and \
                    self._y_offset < event.pos().y() < \
                    self._y_offset + self._height:
                if self.isChecked == 1:
                    self.isChecked = 0
                else:
                    self.isChecked = 1
                self.clicked.emit(index, self.isChecked)
                self.viewport().update()
                return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        """Re-implemented to handle the context menu on header."""
        cMenu = QtWidgets.QMenu()
        for k, v in self.header.items():
            v2 = {"checkable": True, "checked": v.visible}
            act = QtWidgets.QAction(v.caption, self, **v2)
            cMenu.addAction(act)
        # v = {"checkable": True, "checked": False}
        # act = QtWidgets.QAction("Sort Randomly", self, **v)
        # cMenu.addAction(act)
        choice = cMenu.exec_(event.globalPos())
        if choice and choice.text() != self.header["Name"].caption:
            idx = 0
            for k, v in self.header.items():
                if v.caption == choice.text():
                    self.setSectionHidden(idx, v.visible)
                    self.header[k].visible = not v.visible
                    self.visibility_changed.emit(idx, v.caption, v.visible)
                    return
                idx += 1

    # def update_headers(self):
    #     idx = 0
    #     for k, v in self.header.items():
    #         if v.caption == self.header["Name"].caption or v.caption in header.keys():
    #             logger.debug(f"matched {v.caption}")
    #             if not self.header[k].visible:
    #                 logger.debug(f"showing {v.caption}")
    #                 self.header[k].visible = True
    #                 self.setSectionHidden(idx, True)
    #                 self.visibility_changed.emit(idx, v.caption, v.visible)
    #         else:
    #             if self.header[k].visible:
    #                 self.header[k].visible = False
    #                 self.setSectionHidden(idx, False)
    #                 self.visibility_changed.emit(idx, v.caption, v.visible)
    #         idx += 1
