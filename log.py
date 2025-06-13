"""
A small wrapper for extending the native logging module.

This wrapper aims to isolate our custom logging code for clarity.
But it also allows any future developers to migrate their logging
without any real issues. So why not claim it as the main benefit?

The following log levels are used:
    DEBUG: The DEBUG level is used for logging messages that help
           developers find out what went wrong during a debugging
           session.
    INFO: The INFO level indicates events in the system that are
          significant to the business purpose of the app.
    WARNING: Messages logged at the WARN level are typically used
             for situations that should be addressed soon, before
             they pose a problem for the application.
    ERROR: This level is used to represent error conditions in an
           application that prevent a specific operation, but the
           application itself can continue working. This might be
           with a reduced level of functionality or performance.
    CRITICAL: This level shows that something has broken, and the
              app can't continue to work without the intervention
              of an engineer.

Most log messages are written to both the console and a log file.
The log file will contain all INFO level messages and up. When it
gets close to the limit, the log file is closed and a new file is
opened. The old log files are stored by adding a numerical suffix
`.1`, `.2`, etc. to the filename. These suffixes are increased if
a file is closed. For example, `.1` is renamed as `.2`.

Examples:
    >>> log.init(verbosity=log.Level.DEBUG)

    >>> log.debug('Initialized logs')
    [2023-04-05 13:01:04  DEBUG   ]  Initialized logs

    >>> log.warning('Example ended!')
    [2023-04-05 13:01:06  WARNING ]  Example ended!

Constants:
    Level: An enumeration over all supported logging levels

Functions:
    critical: Log a message with the CRITICAL level
    debug: Log a message with the DEBUG level
    error: Log a message with the ERROR level
    info: Log a message with the INFO level
    init: Initialize the logging module
    warning: Log a message with the WARNING level
"""
import enum
import logging.handlers
import pathlib
import sys
import types
import typing

from logging import debug, info, warning, error, critical


__all__ = (
    'critical',
    'debug',
    'error',
    'info',
    'init',
    'Level',
    'warning',
)


class Level(enum.IntEnum):
    """
    An enumeration over all supported logging levels.

    The levels are given as integers which increase by 10 for each
    level of severity. It is not advised to assume specific values
    for each level. These might be subject to changes later on.
    """

    DEBUG = logging.DEBUG
    """
    The DEBUG level is used for logging messages that help
    developers find out what went wrong during a debugging
    session.
    """

    INFO = logging.INFO
    """
    The INFO level indicates events in the system that
    are significant to the business purpose of the app.
    """

    WARNING = logging.WARNING
    """
    Messages logged at the WARN level are typically used
    for situations that should be addressed soon, before
    they pose a problem for the application.
    """

    ERROR = logging.ERROR
    """
    This level is used to represent error conditions in an
    application that prevent a specific operation, but the
    application itself can continue working. This might be
    with a reduced level of functionality or performance.
    """

    CRITICAL = logging.CRITICAL
    """
    This level shows that something has broken, and the
    app can't continue to work without the intervention
    of an engineer.
    """


class _ColouredFormatter(logging.Formatter):
    """
    A formatter which adds some nice colours for consoles to use.

    This is implemented by adding a few new attributes:
        b: Turns the upcoming text bold
        c: A mapping for using the 4-bit colours by name
        levelclr: The colour used for a specific log level
        r: Resets the console to its normal style
    """

    COLOURS: dict[str, str] = {
        'GRAY': '\033[30m',
        'RED': '\033[31m',
        'GREEN': '\033[32m',
        'YELLOW': '\033[33m',
        'BLUE': '\033[34m',
        'MAGENTA': '\033[35m',
        'CYAN': '\033[36m',
        'WHITE': '\033[37m',
    }
    """A mapping between colour names and their 4-bit ANSI escape codes"""

    LEVEL_COLOURS: dict[int, str] = {
        Level.DEBUG: '\033[30m',          # Gray
        Level.INFO: '\033[32m',           # Green
        Level.WARNING: '\033[33m',        # Yellow
        Level.ERROR: '\033[31m',          # Red
        Level.CRITICAL: '\033[31;1;4m',   # Red, Bold, & Underlined
    }
    """A mapping between log levels and their 4-bit ANSI escape codes"""

    RESET = '\033[0m'
    """The 4-bit ANSI escape code used to reset the console style"""

    BOLD = '\033[;1m'
    """The 4-bit ANSI escape code used to start bold text"""

    def formatMessage(self, record):
        """
        Format the given log message into the final string.

        :see: logging.Formatter
        """
        # Add the new styling attributes to the record
        record.c = self.COLOURS
        record.r = self.RESET
        record.levelclr = self.LEVEL_COLOURS[record.levelno]
        record.b = self.BOLD

        # Let the default implementation handle the rest
        return super().formatMessage(record)


def _excepthook(
            exc_type: typing.Type[BaseException],
            exc_value: BaseException,
            exc_traceback: types.TracebackType | None
        ) -> None:
    """
    Ensure an uncaught exception gets logged properly.

    Arguments:
        exc_type: The class of the original exception
        exc_value: The original exception itself
        exc_traceback: The traceback of the original exception

    Raises:
        SystemExit: Always thrown (with a positive exit status)

    :see: sys.excepthook
    """
    # Write the error to the log files
    logging.critical(
        'Unhandled exception',
        exc_info=(exc_type, exc_value, exc_traceback),
    )

    # Ensure the logs are flushed and closed properly.
    #
    # This is likely also done by `atexit`, but better safe than sorry.
    logging.shutdown()

    # Ensure the software stops here and the console is informed.
    sys.exit(1)


def init(
            verbosity: Level | int = Level.INFO,
            log_file: pathlib.Path | str = './logs/itg_machine_logs.log',
            rotate_file_at: int = 10 * 1024**2,     # 10 MB
            backup_count: int = 5,
        ) -> None:
    """
    Initialize the logging library.

    This function overrides the value of `sys.excepthook`.

    Arguments:
        verbosity: The log level to apply in the console
        log_file: The path to the log file to use
        rotate_file_at: The size in bytes to rotate the log files at
        backup_count: The number of old log files to keep as backup
    """
    # Create the rotating file handler for the log file(s).
    #
    # This prevents log files from growing out of control,
    # while the recent history is always preserved.
    file_hdlr = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=rotate_file_at,
        backupCount=backup_count,
    )

    file_hdlr.setFormatter(logging.Formatter(
        datefmt='%Y-%b-%d %H:%M:%S',
        style='{',
        fmt='[{asctime}  {module:12}:{lineno:4}  {levelname:8}]  {message}',
    ))

    file_hdlr.setLevel(Level.INFO)

    # Initialize the handler for the console messages
    console_hdlr = logging.StreamHandler()

    console_hdlr.setFormatter(_ColouredFormatter(
        datefmt='%Y-%b-%d %H:%M:%S',
        style='{',
        fmt='[{c[BLUE]}{asctime}{r}  {c[MAGENTA]}{module:12}{r}:{c[MAGENTA]}{lineno:4}{r}  {levelclr}{levelname:8}{r}]  {message}',   # pylint:disable=line-too-long
    ))

    console_hdlr.setLevel(verbosity)

    # Initialize the root logger
    logging.basicConfig(
        level=min(file_hdlr.level, console_hdlr.level),
        force=True,
        handlers=[file_hdlr, console_hdlr],
    )

    # Register our hook as the one to call on uncaught exceptions
    sys.excepthook = _excepthook