# log_utils.py
import logging
import os
from logging.handlers import RotatingFileHandler

DEFAULT_LOG_FILE = os.getenv("LOG_FILE", "logs/app.log")
DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
# אם תרצה בעתיד גם למסך: LOG_CONSOLE=1 (ברירת מחדל: 0 = לא למסך)
DEFAULT_LOG_CONSOLE = os.getenv("LOG_CONSOLE", "0") in ("1", "true", "True")

def ensure_log_dir(path: str):
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)

def build_logger(name: str = "app",
                 logfile: str = DEFAULT_LOG_FILE,
                 level: str = DEFAULT_LOG_LEVEL) -> logging.Logger:
    """
    File-only logger by default (no console handler).
    Uses rotating file handler to limit file size.
    """
    ensure_log_dir(logfile)
    logger = logging.getLogger(name)

    # אל תוסיף handlers כפולים אם כבר קיים
    if getattr(logger, "_configured", False):
        return logger

    logger.setLevel(getattr(logging, level, logging.INFO))

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # כתיבה לקובץ בלבד (Rotating)
    file_handler = RotatingFileHandler(
        logfile, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(getattr(logging, level, logging.INFO))
    logger.addHandler(file_handler)

    # אופציונלי: להוסיף גם למסך רק אם LOG_CONSOLE=1
    if DEFAULT_LOG_CONSOLE:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        console.setLevel(getattr(logging, level, logging.INFO))
        logger.addHandler(console)

    logger.propagate = False
    logger._configured = True  # סימון פנימי למניעת הוספה כפולה
    logger.info(f"Logger initialized (level={level}, file='{logfile}', console={DEFAULT_LOG_CONSOLE})")
    return logger
