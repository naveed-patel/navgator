import os
import pathlib
import psutil
from datetime import datetime
from .helper import logger


class NavTrash:
    """Trash implementation"""
    HOME = pathlib.Path(os.path.expandvars("$HOME"))

    @classmethod
    def get_path(cls, variable, default):
        value = os.environ.get(variable)
        if value:
            return pathlib.Path(value)
        return default

    @classmethod
    def get_paths(cls, variable, default):
        value = os.environ.get(variable)
        if value:
            return [pathlib.Path(path) for path in value.split(":")]
        return default

    @classmethod
    def get_xdg_data_home(cls):
        return cls.get_path("XDG_DATA_HOME", cls.HOME / ".local" / "share")

    @classmethod
    def get_xdg_cache_home(cls):
        return cls.get_path("XDG_CACHE_HOME", cls.HOME / ".cache")

    @classmethod
    def get_xdg_config_dirs(cls):
        return cls.get_paths("XDG_CONFIG_DIRS", [pathlib.Path("/etc/xdg")])

    @classmethod
    def get_xdg_config_home(cls):
        return cls.get_path("XDG_CONFIG_HOME", cls.HOME / ".config")

    @classmethod
    def get_xdg_data_dirs(cls):
        return cls.get_paths("XDG_DATA_DIRS",
                             [pathlib.Path(path) for path in
                              "/usr/local/share/:/usr/share/".split(":")])

    @classmethod
    def get_xdg_runtime_dir(cls):
        return cls.get_path("XDG_RUNTIME_DIR", None)

    @classmethod
    def get_xdg_variables(cls):
        xdg = {
            'HOME': cls.HOME,
            'XDG_CACHE_HOME': cls.get_xdg_cache_home(),
            'XDG_CONFIG_DIRS': cls.get_xdg_config_dirs(),
            'XDG_CONFIG_HOME': cls.get_xdg_config_home,
            'XDG_DATA_DIRS': cls.get_xdg_data_dirs(),
            'XDG_DATA_HOME': cls.get_xdg_data_home(),
            'XDG_RUNTIME_DIR': cls.get_xdg_runtime_dir(),
        }
        return xdg

    @classmethod
    def get_mountpoints(cls):
        return psutil.disk_partitions()

    @classmethod
    def get_mountpoint_names(cls):
        for mp in cls.get_mountpoints():
            yield mp.mountpoint

    @classmethod
    def get_trash_folders(cls):
        trash = [str(cls.get_xdg_data_home()) + os.sep + "Trash"]
        for mp in cls.get_mountpoint_names():
            p = pathlib.Path(mp)
            a = [x for x in p.iterdir() if x.name.startswith(".Trash")
                 and x.is_dir()]
            trash += a
        for a1 in trash:
            logger.debug(f"{a1}")
        return trash

    @classmethod
    def get_trash(cls):
        for tf in cls.get_trash_folders():
            p = pathlib.Path(f"{tf}{os.sep}files")
            mp = pathlib.Path(f"{tf}{os.sep}").parent
            for f in p.iterdir():
                info = f"{tf}{os.sep}info{os.sep}{f.name}.trashinfo"
                with open(info, "r") as fh:
                    contents = fh.readlines()
                    for line in contents:
                        line = line.strip()
                        if line.startswith('DeletionDate='):
                            date = datetime.strptime(
                                    line, "DeletionDate=%Y-%m-%dT%H:%M:%S")
                        elif line.startswith('Path='):
                            path = line[len('Path='):]
                            if not path.startswith("/"):
                                path = f"{mp}{os.sep}{path}"
                logger.debug(f"{f.name} was deleted at {date} from {path}")
                
