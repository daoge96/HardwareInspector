"""统一日志：滚动文件 + 控制台。"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from typing import Dict

from .config import config

_LOGGERS: Dict[str, logging.Logger] = {}
_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def get_logger(name: str = "app") -> logging.Logger:
    """返回带滚动文件输出的 logger（同名单例）。"""
    cached = _LOGGERS.get(name)
    if cached is not None:
        return cached
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if not logger.handlers:
        log_dir = config().dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            log_dir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(sh)
    _LOGGERS[name] = logger
    return logger
