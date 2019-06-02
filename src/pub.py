import functools
import operator
# from helper import logger


class Pub:
    sub = {}

    @staticmethod
    def add_subscriber(tree, topic, val):
        """Adds a subscriber to list of subscribers for said topic."""
        k = topic[0]
        if len(topic) == 1:
            tree.setdefault(k, {"sub": []})
            tree[k]["sub"].append(val)
        else:
            if k not in tree:
                tree[k] = {"sub": []}
            Pub.add_subscriber(tree[k], topic[1:], val)
        return tree

    @staticmethod
    def get_subscribers(topics):
        """Gets all subcribers subscribed to the said topic."""
        topics.append("All")
        val = Pub.sub
        out = []
        try:
            for k in topics:
                val = val[k]
                if "sub" in val:
                    out.append(val["sub"])
        except KeyError:
            pass
        if out:
            return functools.reduce(operator.concat, out)
        else:
            return []

    @staticmethod
    def subscribe(topic, fn):
        """Subscribes a callback for the said topic."""
        # logger.debug(f"Subscribe {topic} by {fn}")
        topic = topic.title()
        topics = topic.split(".")
        Pub.sub = Pub.add_subscriber(Pub.sub, topics, fn)

    @staticmethod
    def unsubscribe(topic, fn):
        """Unsubscribes a callback for the said topic."""
        # logger.debug(f"UnSubscribe {topic} by {fn}")
        val = Pub.sub
        topics = topic.split(".")
        for k in topics:
            try:
                val = val[k]
                val["sub"].remove(fn)
            except (KeyError, ValueError):
                pass

    @staticmethod
    def notify(event, *args, **kwargs):
        """Notifies the callbacks when publisher sends a notification."""
        event = event.title()
        # logger.debug(f"Notification received for {event}")
        try:
            for fn in Pub.get_subscribers(event.split(".")):
                try:
                    # logger.debug(f"Notifying for {event} to {fn}")
                    fn(*args, **kwargs)
                except TypeError:
                    pass
        except KeyError:
            pass
