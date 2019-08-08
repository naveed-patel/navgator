import magic
from PyQt5 import QtCore, QtWidgets, QtGui
from PIL.ImageQt import ImageQt
from .core import Nav
from .helper import logger  # , humansize, to_bytes


class NavViewer(QtWidgets.QMainWindow):
    """Image Viewer"""
    def __init__(self, parent=None):
        super().__init__()
        self.setWindowIcon(Nav.icon)
        self._zoom = 0
        # self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        self.setGeometry(QtWidgets.QDesktopWidget().screenGeometry(-1))
        self.main_widget = QtWidgets.QWidget(self)
        self.stack = QtWidgets.QStackedLayout(self.main_widget)
        self.imgvwr = ImageViewer(self)
        self.imgvwr.setFocusPolicy(QtCore.Qt.NoFocus)
        self.gifvwr = QtWidgets.QLabel()
        self.gifvwr.setAlignment(QtCore.Qt.AlignCenter)
        self.gifvwr.setStyleSheet("background-color: black")
        self.gifvwr.setGeometry(self.geometry())
        self.gifvwr.setSizePolicy(QtWidgets.QSizePolicy.Ignored,
                                  QtWidgets.QSizePolicy.Ignored)
        # self.movie = QtGui.QMovie("a")
        self.stack.addWidget(self.gifvwr)
        self.stack.addWidget(self.imgvwr)
        self.setCentralWidget(self.main_widget)
        self.setFocus()
        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Reimplemented to handle active pane."""
        if event.type() == QtCore.QEvent.KeyPress:
            key = event.key()
            if key == QtCore.Qt.Key_Escape or key == QtCore.Qt.Key_Backspace:
                self.close()
                # self.destroy()
            elif key == QtCore.Qt.Key_Left:
                self.load_index(self.owner.proxy.previous_index(self.ind))
            elif key == QtCore.Qt.Key_Right or key == QtCore.Qt.Key_Space:
                self.load_index(self.owner.proxy.next_index(self.ind))
            elif key == QtCore.Qt.Key_Delete and self.cur_file is not None:
                logger.debug(f"Deleting {self.cur_file}")
                self.owner.trash([self.cur_file])
                self.load_index(self.ind) or \
                    (self.load_index(self.owner.proxy.previous_index(self.ind))
                        if self.ind > 0 else self.load_index(self.ind))
            else:
                super().keyPressEvent(event)
        return False

    def loadCurrentImage(self, owner):
        """Gets the index for currently selected item."""
        self.owner = owner
        self.ind = self.owner.view.currentIndex().row()
        if self.ind < 0:
            self.ind = 0
        self.load_index(self.ind)

    def load_index(self, index):
        """Loads the item at index in the viewer."""
        if index is None:
            logger.debug("Nothing to show")
            self.cur_file = None
            self.imgvwr.setPhoto(QtGui.QPixmap())
            return
        self.ind = index
        self.cur_file = self.owner.proxy.get_full_name_at_row(
            index)
        total = self.owner.proxy.rowCount()
        if self.cur_file is None:
            if total == 0:
                self.close()
            else:
                self.imgvwr.setPhoto(QtGui.QPixmap())
                self.setWindowTitle(f"Image Viewer")
            return False
        self.setWindowTitle(f"{self.ind+1}/{total}: {self.cur_file}")
        try:
            info = magic.detect_from_filename(self.cur_file)
        except ValueError as e:
            logger.debug(e)
            return False
        self._zoom = 0
        if info.mime_type == "image/gif":
            self.stack.setCurrentWidget(self.gifvwr)
            # self.movie.stop()
            # Instantiate again to remove scaling
            self.movie = QtGui.QMovie(self.cur_file)
            self.movie.setFileName(self.cur_file)
            if self.movie.isValid():
                self.movie.setSpeed(100)
                self.gifvwr.setMovie(self.movie)
                self.movie.start()
            else:
                self.stack.setCurrentWidget(self.imgvwr)
                self.imgvwr.setPhoto(self.cur_file)
        else:
            self.stack.setCurrentWidget(self.imgvwr)
            self.imgvwr.setPhoto(self.cur_file)

    def wheelEvent(self, event):
        """Handles wheel event for GIFs."""
        if magic.detect_from_filename(self.cur_file).mime_type == "image/gif":
            if event.angleDelta().y() > 0:
                factor = 1.2
                self._zoom += 1
            else:
                factor = 0.8
                self._zoom -= 1
            if self._zoom != 0:
                newsize = QtCore.QSize(
                    self.movie.currentImage().size().width() * factor,
                    self.movie.currentImage().size().height() * factor)
                self.movie.setScaledSize(newsize)
                self.gifvwr.setAlignment(QtCore.Qt.AlignCenter)
            else:
                self._zoom = 0


class ImageViewer(QtWidgets.QGraphicsView):
    """Customised class to display images"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QtWidgets.QGraphicsScene(self)
        self._photo = QtWidgets.QGraphicsPixmapItem()
        self._scene.addItem(self._photo)
        self.setScene(self._scene)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(30, 30, 30)))
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.ViewportAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)

    def fit_to_view(self, scale=True):
        """Resizes image and rectangle to fit in main window"""
        rect = QtCore.QRectF(self._photo.pixmap().rect())
        if not rect.isNull():
            self.setSceneRect(rect)
            unity = self.transform().mapRect(QtCore.QRectF(0, 0, 1, 1))
            self.scale(1 / unity.width(), 1 / unity.height())
            viewrect = self.viewport().rect()
            scenerect = self.transform().mapRect(rect)
            if viewrect.width() < scenerect.width() or \
                    viewrect.height() < scenerect.height():
                factor = min(viewrect.width() / scenerect.width(),
                             viewrect.height() / scenerect.height())
                self.scale(factor, factor)
            self._zoom = 0

    def setPhoto(self, pic=None):
        """Displays the images in the viewer."""
        # pixmap = QtGui.QPixmap(pic)
        # if pic is not None:
        try:
            qim = ImageQt(pic)
            pixmap = QtGui.QPixmap.fromImage(qim.copy())
        except Exception:
            pixmap = QtGui.QPixmap(pic)
        self._zoom = 0
        if pixmap and not pixmap.isNull():
            self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
            self._photo.setPixmap(pixmap)
        else:
            self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
            self._photo.setPixmap(QtGui.QPixmap())
        self.fit_to_view()

    def wheelEvent(self, event):
        """Handles wheel to zoom in and out"""
        if event.angleDelta().y() > 0:
            factor = 1.2
            self._zoom += 1
        else:
            factor = 0.8
            self._zoom -= 1
        if self._zoom != 0:
            self.scale(factor, factor)
        else:
            self.fit_to_view()
        event.accept()
