import os
import pathlib
# import psutil
from .helper import logger
from watchdog.observers import Observer
# from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler


class NavWatcher:
    """Helper class to start/stop watchdog and add/remove paths."""
    running = False
    monitored = {}
    event_handler = FileSystemEventHandler()
    observer = Observer()
    # poller = PollingObserver()

    @classmethod
    def on_file_system_event(cls, event):
        """Invokes provided callback on FileSystemEvent."""
        loc = str(pathlib.PurePath(event.src_path).parent)
        logger.debug(f"Change detected in {loc}")
        try:
            for callback in cls.monitored[loc]['callbacks']:
                callback(event, loc)
        except KeyError:
            # KeyError occurs for parent folders. Expected
            pass

    @classmethod
    def add_path(cls, loc, callback, recursive=False):
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
                "watch": cls.observer.schedule(cls.event_handler, loc,
                                               recursive=recursive),
            }
            # partitions = psutil.disk_partitions()
            # mp = None
            # for p in partitions:
            #     if loc.startswith(p):
            #         if mp is None or mp in p.mountpoint:
            #             mp = p.mountpoint
            #             logger.debug(f"{loc} mounted on {mp}")
            # try:
            #     if callback not in cls.monitored[mp]['callbacks']:
            #         cls.monitored[mp]['callbacks'].append(callback)
            # except KeyError:
            #     cls.monitored[mp] = {
            #         "stamp": os.stat(loc).st_mtime,
            #         "callbacks": [callback],
            #         "watch": cls.poller.schedule(cls.event_handler, mp),
            #     }
            logger.debug(f"Monitoring started for {loc}")
        logger.debug(f"Current watchers: {cls.observer._watches}")

    @classmethod
    def remove_path(cls, loc, callback):
        """Removes callbacks and watches for the said location."""
        try:
            cls.monitored[loc]['callbacks'].remove(callback)
            logger.debug(f"Callback removed from {loc}")
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
            cls.event_handler.on_thread_stop = cls.on_thread_stop
            cls.observer.daemon = True
            cls.observer.start()
            # cls.poller.start()

    def on_thread_stop(cls):
        logger.debug(f"Watchdog stopped.")

    @classmethod
    def stop(cls):
        """Unschedules all watchdogs."""
        cls.observer.unschedule_all()
        cls.running = False
