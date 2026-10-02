"""
Custom exceptions for ACE Pro system.
"""


class AceException(Exception):
    """Base exception for ACE Pro errors"""
    pass


def gcode_guard(handler):
    """
    Wrap a G-code handler so an AceException becomes a normal G-code command error.

    Klipper treats any exception other than its CommandError as an *internal error*
    and shuts the whole printer down. A failed feed or a sensor that will not clear
    is an operational error: report it, pause, keep Klipper alive.
    """
    def wrapped(gcmd):
        try:
            return handler(gcmd)
        except AceException as exc:
            raise gcmd.error(str(exc))
    wrapped.__name__ = getattr(handler, '__name__', 'wrapped')
    wrapped.__doc__ = getattr(handler, '__doc__', None)
    return wrapped

