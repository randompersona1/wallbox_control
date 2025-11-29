"""Utilities for consistent exception logging across Wallbox Control."""

from __future__ import annotations

import logging
import sys
import threading
from types import TracebackType


def install_global_exception_logging(logger: logging.Logger | None = None) -> None:
    """Ensure unhandled exceptions are logged before the process exits.

    The handler respects ``KeyboardInterrupt`` to allow graceful shutdowns while
    still emitting critical logs for unexpected errors.
    """

    active_logger = logger or logging.getLogger("wallbox_control.unhandled")

    def _excepthook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        active_logger.critical(
            "Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback)
        )

    original_thread_hook = getattr(threading, "excepthook", None)

    def _threading_excepthook(args: threading.ExceptHookArgs) -> None:
        if issubclass(args.exc_type, KeyboardInterrupt):
            if original_thread_hook and original_thread_hook is not _threading_excepthook:
                original_thread_hook(args)
            return
        active_logger.critical(
            "Unhandled exception in thread %s",
            args.thread.name,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = _excepthook
    threading.excepthook = _threading_excepthook
