import collections
import functools
import logging.config
import sys


lconf = {
        'version': 1,
        'disable_existing_loggers': True,
        'formatters': {
            'detailed': {
                'class': 'logging.Formatter',
                'format': '%(asctime)s - %(relativeCreated)d - %(levelname)s'
                          ' - %(funcName)s - %(lineno)d - %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'DEBUG',
                'formatter': 'detailed',
            },
            'file': {
                'class': 'logging.FileHandler',
                'filename': '/tmp/navgator.log',
                'mode': 'w',
                'level': 'DEBUG',
                'formatter': 'detailed',
            },
        },
        'loggers': {
            'foo': {
                'handlers': []
            }
        },
        'root': {
            'level': 'DEBUG',
            'handlers': ['console', 'file']
        },
    }
logging.config.dictConfig(lconf)
logger = logging.getLogger(__name__)


def humansize(num, power=1024, sep=' ', precision=2, unit=None):
    """Converts raw bytes to a human friendly format."""
    if power == 1024:
        units = ['B  ', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
    else:
        units = ['B ', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    if unit in units:
        if power == 1024:
            num = num >> (units.index(unit) * 10)
        else:
            div = power ** units.index(unit)
            num /= float(div)
        return f"{num:.{precision}f}{sep}{unit}"

    for unit in units[:-1]:
        if abs(round(num, precision)) < power:
            return f"{num:.{precision}f}{sep}{unit}"
        num /= float(power)
    return f"{num:.{precision}f}{sep}{units[-1]}"


def to_bytes(size, power=1024, sep=' '):
    """Converts human size to raw bytes."""
    if not size:
        return 0
    size, suffix = size.split(sep, 1)
    suffix = suffix[0]
    try:
        factor = {
            'K': power,
            'M': power**2,
            'G': power**3,
            'T': power**4,
            'P': power**5,
        }[suffix]
    except KeyError:
        factor = 1
    return int(float(size) * factor)


def deep_merge(d, u):
    """Deep merges one dict (u) into another (d)."""
    stack = [(d, u)]
    while stack:
        d, u = stack.pop(0)
        for k, v in u.items():
            if not isinstance(v, collections.abc.Mapping):
                d[k] = v
            else:
                dv = d.setdefault(k, {})
                if not isinstance(dv, collections.abc.Mapping):
                    d[k] = v
                else:
                    stack.append((dv, v))


def jdefault(o):
    return o.__dict__


def debug(func):
    """Print the function signature and return value."""
    @functools.wraps(func)
    def wrapper_debug(*args, **kwargs):
        caller = sys._getframe().f_back.f_code.co_name
        args_repr = [repr(a) for a in args]
        kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
        signature = ", ".join(args_repr + kwargs_repr)
        logger.debug(f"{caller} called {func.__name__}({signature})")
        value = func(*args, **kwargs)
        logger.debug(f"{func.__name__!r} returned {value!r}")
        return value
    return wrapper_debug
