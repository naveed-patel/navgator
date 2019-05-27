import os
import pathlib
from .helper import logger
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class NavWatcher:
    """Helper class to start/stop watchdog and add/remove paths."""
    running = False
    monitored = {}
    event_handler = FileSystemEventHandler()
    observer = Observer()

    @classmethod
    def on_file_system_event(cls, event):
        """Invokes provided callback on FileSystemEvent."""
        loc = str(pathlib.PurePath(event.src_path).parent)
        try:
            for callback in cls.monitored[loc]['callbacks']:
                callback(event, loc)
        except KeyError:
            # KeyError occurs for parent folders. Expected
            # logger.warning(f"No callbacks available for {loc}")
            pass

    @classmethod
    def add_path(cls, loc, callback):
        """Adds callbacks and watches for the said location."""
        if not os.path.exists(loc):
            logger.warning(f"{loc} no longer exists.")
            return
        try:
            if callback not in cls.monitored[loc]['callbacks']:
                cls.monitored[loc]['callbacks'].append(callback)
            logger.debug(f"Callback {callback} registered for {loc}")
        except KeyError:
            cls.monitored[loc] = {
                "stamp": os.stat(loc).st_mtime,
                "callbacks": [callback],
                "watch": cls.observer.schedule(cls.event_handler, loc),
            }
            logger.debug(f"Monitoring started for {loc}")
        logger.debug(f"Current watchers: {cls.observer._watches}")

    @classmethod
    def remove_path(cls, loc, callback):
        """Removes callbacks and watches for the said location."""
        try:
            cls.monitored[loc]['callbacks'].remove(callback)
            logger.debug(f"Callback {callback} removed from {loc}")
        except (KeyError, ValueError):
            logger.warning(f"Error removing callback for {loc}")
        try:
            if "callbacks" not in cls.monitored[loc] or \
                    len(cls.monitored[loc]["callbacks"]) < 1:
                cls.observer.unschedule(cls.monitored[loc]["watch"])
                logger.debug(f"Stopped monitoring for {loc} as no callbacks")
                del cls.monitored[loc]
        except (KeyError, ValueError):
            logger.warning(f"Error unscheduling watch for {loc}.")
        logger.debug(f"Current watchers: {cls.observer._watches}")

    @classmethod
    def start(cls):
        """Starts the watchdog and hooks function for various events."""
        if cls.running is False:
            cls.running = True
            cls.event_handler.on_deleted = cls.on_file_system_event
            cls.event_handler.on_moved = cls.on_file_system_event
            cls.event_handler.on_created = cls.on_file_system_event
            cls.event_handler.on_modified = cls.on_file_system_event
            cls.observer.start()

    @classmethod
    def stop(cls):
        """Unschedules all watchdogs."""
        cls.observer.unschedule_all()
        cls.running = False
