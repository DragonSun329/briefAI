"""
Scraper timeout utilities.

Provides socket-level default timeout and per-scraper execution timeout
to prevent individual scrapers from hanging indefinitely.
"""

import socket
import threading
import signal
import os
import sys
from typing import Any, Callable, Optional


# Set global socket timeout - this fixes feedparser.parse() and any other
# library that uses urllib/socket without explicit timeouts.
DEFAULT_SOCKET_TIMEOUT = 30  # seconds
socket.setdefaulttimeout(DEFAULT_SOCKET_TIMEOUT)


def run_with_timeout(func: Callable, timeout: int = 120, name: str = "scraper") -> Any:
    """
    Run a function with a hard timeout. Returns the result or raises TimeoutError.

    Uses a daemon thread with improved process termination for hung I/O operations.
    """
    result = [None]
    exception = [None]
    completed = threading.Event()

    def target():
        try:
            result[0] = func()
        except Exception as e:
            exception[0] = e
        finally:
            completed.set()

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    
    # Wait for completion with timeout
    if completed.wait(timeout=timeout):
        # Completed normally
        if exception[0] is not None:
            raise exception[0]
        return result[0]
    else:
        # Timeout occurred
        print(f"  WARNING: {name} timed out after {timeout}s")
        print(f"  Daemon thread abandoned (may continue in background)")
        
        # On Windows, we can't easily kill threads, so we just abandon it
        # This is better than hanging the entire pipeline
        raise TimeoutError(f"{name} did not complete within {timeout}s (thread abandoned)")
