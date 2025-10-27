"""
Logging Configuration

Centralized logging setup using loguru.
"""

import os
import sys
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


def setup_logger(
    log_dir: str = "./logs",
    log_level: str = None,
    log_to_file: bool = True
):
    """
    Configure loguru logger

    Args:
        log_dir: Directory for log files
        log_level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_to_file: Whether to write logs to file
    """
    # Get log level from env or parameter
    log_level = log_level or os.getenv("LOG_LEVEL", "INFO")

    # Remove default handler
    logger.remove()

    # Add console handler with colors
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=log_level,
        colorize=True
    )

    # Add file handler if enabled
    if log_to_file:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_path / "briefing_agent_{time:YYYY-MM-DD}.log",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level=log_level,
            rotation="00:00",  # Rotate at midnight
            retention="30 days",  # Keep logs for 30 days
            compression="zip",
            encoding="utf-8"
        )

    logger.info(f"Logger initialized (level: {log_level})")
    return logger


# Initialize logger when module is imported
setup_logger()
