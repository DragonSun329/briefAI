"""
Scraper timeout utilities.

Provides socket-level default timeout and per-scraper execution timeout
to prevent individual scrapers from hanging indefinitely.
"""

import socket
import threading
from typing import Any, Callable, Optional


# Set global socket timeout - this fixes feedparser.parse() and any other
# library that uses urllib/socket without explicit timeouts.
DEFAULT_SOCKET_TIMEOUT = 30  # seconds
socket.setdefaulttimeout(DEFAULT_SOCKET_TIMEOUT)


def run_with_timeout(func: Callable, timeout: int = 120, name: str = "scraper") -> Any:
    """
    Run a function with a hard timeout. Returns the result or raises TimeoutError.

    Uses a daemon thread so it won't block the main process even if the
    function is stuck in a blocking I/O call.
    """
    result = [None]
    exception = [None]

    def target():
        try:
            result[0] = func()
        except Exception as e:
            exception[0] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        raise TimeoutError(f"{name} did not complete within {timeout}s")

    if exception[0] is not None:
        raise exception[0]

    return result[0]
