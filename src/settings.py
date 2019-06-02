from PyQt5 import QtWidgets, QtCore
from .helper import logger
from .core import Nav


class NavSettings(QtWidgets.QDialog):
    settings_changed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        preflist = QtWidgets.QListWidget()
        self.stack = QtWidgets.QStackedWidget()
        self.set_items = ["General", "Panes",  # Tabs", "Sorting", "Renaming",
                          # "Colors",
                          ]
        for item in self.set_items:
            preflist.addItem(item)
            self.set_ui(item)

        applyButton = QtWidgets.QPushButton('Apply')
        applyButton.clicked.connect(self.apply)
        okButton = QtWidgets.QPushButton('OK')
        okButton.clicked.connect(self.ok)
        cancelButton = QtWidgets.QPushButton('Cancel')
        cancelButton.clicked.connect(self.hide)

        mainLayout = QtWidgets.QGridLayout(self)
        mainLayout.addWidget(preflist, 0, 0, QtCore.Qt.AlignLeft)
        mainLayout.addWidget(self.stack, 0, 1, 1, 4, QtCore.Qt.AlignTop)
        mainLayout.addWidget(applyButton, 1, 4)
        mainLayout.addWidget(okButton, 1, 5)
        mainLayout.addWidget(cancelButton, 1, 6)
        self.setWindowTitle('Settings')
        self.setGeometry(300, 300, 800, 200)
        preflist.currentRowChanged.connect(self.display)
        self.sizeHint()

    def set_ui(self, item):
        layout = QtWidgets.QHBoxLayout()
        stacks = QtWidgets.QWidget()
        if item == "General":
            folders_first = QtWidgets.QCheckBox("Sort folders first")
            if Nav.conf["sort_folders_first"]:
                folders_first.setChecked(True)
            layout.addWidget(folders_first)
        elif item == "Panes":
            for i in range(1, 5):
                name = f"Pane {i}"
                pane_cb = QtWidgets.QCheckBox(name)
                if Nav.conf["panes"][name]["visible"]:
                    pane_cb.setChecked(True)
                layout.addWidget(pane_cb)
        stacks.setLayout(layout)
        self.stack.addWidget(stacks)

    def apply(self):
        for c in self.stack.children():
            for widget in c.children():
                if isinstance(widget, QtWidgets.QCheckBox):
                    logger.debug(f"CB: {widget.text()}-{widget.checkState()}")
                    if widget.text() == "Sort folder to top":
                        if widget.checkState():
                            Nav.conf["sort_folders_first"] = True
                        else:
                            Nav.conf["sort_folders_first"] = False
                        logger.debug(Nav.conf["sort_folders_first"])

                    if widget.text() in ["Pane 1", "Pane 2", "Pane 3",
                                         "Pane 4"]:
                        if widget.checkState():
                            Nav.conf["panes"][widget.text()]["visible"] = True
                        else:
                            Nav.conf["panes"][widget.text()]["visible"] = False
        self.settings_changed.emit()

    def ok(self):
        self.apply()
        self.hide()

    def display(self, i):
        self.stack.setCurrentIndex(i)
