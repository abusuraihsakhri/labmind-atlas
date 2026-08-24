import logging
import sys
import os


def setup_logging(service_name: str, level: str = None) -> logging.Logger:
    log_level = level or os.getenv("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    return logger
