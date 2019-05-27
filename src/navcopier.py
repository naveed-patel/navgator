import os
import shutil
import sys
import stat
import time
from PyQt5 import QtWidgets, QtCore
from helper import logger, humansize


class NavCopier(QtWidgets.QWidget):
    """Copy/Move files/directories with a progress window."""
    def __init__(self, arg):
        super().__init__()
        self.act = arg[0]
        self.sources = arg[1: -1]
        self.destination = arg[-1]
        self.copied = 0
        self.total = 0
        self.rate = "0"
        self.total_time = "0 s"
        self.time_elapsed = "0 s"
        self.time_remaining = "0 s"
        self.last_time = 0
        self.build_ui()
        self.copier(self.act)
        sys.exit()

    def build_ui(self):
        """Builds the copy progress window"""
        hbox = QtWidgets.QVBoxLayout()
        self.lbl_action = QtWidgets.QLabel("Checking...")
        self.lbl_src = QtWidgets.QLabel('Source: ' + self.sources[0])
        self.lbl_dest = QtWidgets.QLabel('Destination: ' + self.destination)
        self.pb = QtWidgets.QProgressBar()
        self.lbl_copied = QtWidgets.QLabel(f"Copied Bytes: {self.copied}")
        self.lbl_total = QtWidgets.QLabel(f"Total Bytes: {self.total}")
        self.lbl_remaining = QtWidgets.QLabel(f"Remaining Bytes: {self.total}")
        self.lbl_rate = QtWidgets.QLabel(f"Transfer Rate: {self.rate}")
        self.lbl_time_elapsed = QtWidgets.QLabel(
            f"Time Elapsed: {self.time_elapsed}")
        self.lbl_time_remaining = QtWidgets.QLabel(
            f"Time Remaining: {self.time_remaining}")
        self.pb.setMinimum(0)
        self.pb.setMaximum(100)
        self.pb.setValue(0)
        hbox.addWidget(self.lbl_src)
        hbox.addWidget(self.lbl_dest)
        hbox.addWidget(self.pb)
        hbox.addWidget(self.lbl_copied)
        hbox.addWidget(self.lbl_remaining)
        hbox.addWidget(self.lbl_total)
        hbox.addWidget(self.lbl_rate)
        hbox.addWidget(self.lbl_time_elapsed)
        hbox.addWidget(self.lbl_time_remaining)
        self.setLayout(hbox)
        self.show()

    @QtCore.pyqtSlot()
    def update_progress(self, optional=True):
        """Updates the progress bar."""
        try:
            self.time_elapsed = time.process_time() - self.start_time
            # if optional and self.time_elapsed - self.last_time < 0.1:
            #    return
            self.last_time = time.process_time()
            completed = self.copied / self.total * 100
            self.pb.setValue(completed)
            self.lbl_copied.setText(f"Copied: {humansize(self.copied)}")
            remaining_bytes = self.total - self.copied
            self.lbl_remaining.setText(
                f"Remaining Bytes: {humansize(remaining_bytes)}")
            self.lbl_time_elapsed.setText(
                f"Time Elapsed: {self.time_elapsed}s")
            rate_raw = (self.copied/self.time_elapsed)
            self.rate = '{:.2f} bytes/s'.format(rate_raw)
            self.lbl_rate.setText(f"Transfer rate: {self.rate}")

            time_remaining_raw = remaining_bytes / rate_raw
            self.time_remaining = '{:.2f} s'.format(time_remaining_raw)
            self.lbl_time_remaining.setText(
                f"Time Remaining: {self.time_remaining}")
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass

    def get_size(self, loc, recurse=True):
        """Calculates number of bytes to copied."""
        paste_size = 0
        if os.path.isdir(loc):
            for item in os.scandir(loc):
                paste_size += self.get_size(item, recurse=True)
        else:
            paste_size += os.stat(loc).st_size
        return paste_size

    def copier(self, act):
        """Copy/Move files"""
        self.start_time = time.process_time()
        self.lbl_action.setText("Calculating size...")
        for source in self.sources:
            self.total += self.get_size(source)
        self.lbl_total.setText(f"Total Bytes: {humansize(self.total)}")
        if self.act == "copy":
            for src in self.sources:
                logger.debug(f"Now copying {src}")
                if os.path.isdir(src):
                    self.copytree(src, os.path.join(self.destination,
                                  os.path.basename(src)))
                else:
                    self.lbl_src.setText(f"Source: {src}")
                    self.copy(src, self.destination)
        elif self.act == "move":
            for src in self.sources:
                logger.debug(f"Now moving {src}")
                self.lbl_src.setText(f"Source: {src}")
                self.move(src, self.destination)
        # self.thread_instance.stop()

    def copy(self, src, dst):
        """Reimplemented to report copy progress"""
        if os.path.isdir(dst):
            dst = os.path.join(dst, os.path.basename(src))
        logger.debug(f"{self.act} {src} to {dst}")
        if os.path.exists(dst):
            choice = QtWidgets.QMessageBox.question(
                     None, "File exists",
                     f"{dst} is already present. Overwrite?",
                     QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            if choice == QtWidgets.QMessageBox.No:
                return

        self.copyfile(src, dst, follow_symlinks=True)
        shutil.copystat(src, dst, follow_symlinks=True)
        shutil.copymode(src, dst)

    def copyfile(self, src, dst, *, follow_symlinks=True):
        """Reimplemented to report copy progress"""
        if shutil._samefile(src, dst):
            raise shutil.SameFileError("{!r} and {!r} are the same file"
                                       .format(src, dst))

        for fn in [src, dst]:
            try:
                st = os.stat(fn)
            except OSError:
                # File most likely does not exist
                pass
            else:
                # XXX What about other special files? (sockets, devices...)
                if stat.S_ISFIFO(st.st_mode):
                    raise shutil.SpecialFileError("`%s` is a named pipe" % fn)

        if not follow_symlinks and os.path.islink(src):
            os.symlink(os.readlink(src), dst)
        else:
            with open(src, 'rb') as fsrc:
                with open(dst, 'wb') as fdst:
                    self.copyfileobj(fsrc, fdst)
        return dst

    def copyfileobj(self, fsrc, fdst, length=16*1024):
        """Reimplemented to report copy progress"""
        while 1:
            buf = fsrc.read(length)
            if not buf:
                break
            fdst.write(buf)
            self.copied += len(buf)
            self.update_progress()
        self.update_progress(optional=False)

    def copytree(self, src, dst, symlinks=False, ignore=None,
                 copy_function=None, ignore_dangling_symlinks=False):
        """Reimplemented to report copy progress"""
        copy_function = self.copy

        names = os.listdir(src)
        if ignore is not None:
            ignored_names = ignore(src, names)
        else:
            ignored_names = set()

        try:
            os.makedirs(dst)
            logger.debug(f"Directory created: {dst}")
        except FileExistsError:
            choice = QtWidgets.QMessageBox.question(
                        None, "Folder exists",
                        f"{dst} is already present. Merge?",
                        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            if choice == QtWidgets.QMessageBox.No:
                return
        errors = []
        for name in names:
            if name in ignored_names:
                continue
            srcname = os.path.join(src, name)
            dstname = os.path.join(dst, name)
            try:
                if os.path.islink(srcname):
                    linkto = os.readlink(srcname)
                    if symlinks:
                        # We can't just leave it to `copy_function` because
                        # legacy code with a custom `copy_function` may rely on
                        # copytree doing the right thing.
                        os.symlink(linkto, dstname)
                        shutil.copystat(srcname, dstname,
                                        follow_symlinks=not symlinks)
                    else:
                        # ignore dangling symlink if the flag is on
                        if not os.path.exists(linkto) and \
                                ignore_dangling_symlinks:
                            continue
                        # otherwise let the copy occurs. copy2 will raise error
                        if os.path.isdir(srcname):
                            self.copytree(srcname, dstname, symlinks, ignore)
                        else:
                            copy_function(srcname, dstname)
                elif os.path.isdir(srcname):
                    self.copytree(srcname, dstname, symlinks, ignore,
                                  copy_function)
                else:
                    # Will raise a SpecialFileError for unsupported file types
                    copy_function(srcname, dstname)
            # catch the Error from the recursive copytree so that we can
            # continue with other files
            except shutil.Error as err:
                errors.extend(err.args[0])
            except OSError as why:
                errors.append((srcname, dstname, str(why)))
        try:
            shutil.copystat(src, dst)
        except OSError as why:
            # Copying file access times may fail on Windows
            if getattr(why, 'winerror', None) is None:
                errors.append((src, dst, str(why)))
        if errors:
            raise shutil.Error(errors)
            # logger.debug(errors)
        return dst

    def move(self, src, dst, copy_function=None):
        """Reimplemented to report move progress"""
        copy_function = self.copy
        real_dst = dst
        if os.path.isdir(dst):
            if shutil._samefile(src, dst):
                # We might be on a case insensitive filesystem,
                # perform the rename anyway.
                os.rename(src, dst)
                return

            real_dst = os.path.join(dst, shutil._basename(src))
            if os.path.exists(real_dst):
                if os.path.isdir(real_dst):
                    title = "Folder exists"
                    msg = f"{real_dst} is already present.Merge?"
                else:
                    title = "File exists"
                    msg = f"{real_dst} is already present. Overwrite?"
                choice = QtWidgets.QMessageBox.question(
                        None, title, msg,
                        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
                if choice == QtWidgets.QMessageBox.No:
                    return
                if os.path.isdir(src):
                    logger.debug(f"now doing a folder move for {src}")
                    for d in os.listdir(src):
                        d2 = os.path.join(src, d)
                        self.move(d2, real_dst)
                else:
                    logger.debug(f"now doing a file move for {src}")
                    # self.move(src, real_dst)
            # raise Error("Destination path '%s' already exists" % real_dst)
        try:
            # if os.path.isdir(real_dst):
            #    raise OSError
            logger.debug(f"Trying rename from {src} to {real_dst}")
            size = self.get_size(src)
            os.rename(src, real_dst)
            self.copied += size
            self.update_progress()  # self.copied)
        except OSError:
            logger.debug(
                f"Rename from {src} to {real_dst} failed. Trying alternatives")
            if os.path.islink(src):
                linkto = os.readlink(src)
                os.symlink(linkto, real_dst)
                os.unlink(src)
            elif os.path.isdir(src):
                if shutil._destinsrc(src, dst):
                    raise shutil.Error(f"Cannot move a directory '{src}' into "
                                       f"itself '{dst}'.")
                try:
                    logger.debug(f"Copy tree from {src} to {real_dst}")
                    self.copytree(src, real_dst, copy_function=copy_function,
                                  symlinks=True)
                    shutil.rmtree(src)
                except Exception:
                    logger.debug(f"Error copying {src}")
            else:
                logger.debug(f"Copy file from {src} to {real_dst}")
                copy_function(src, real_dst)
                os.unlink(src)
        return real_dst


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    ex = NavCopier(sys.argv[1:])
    sys.exit(app.exec_())
