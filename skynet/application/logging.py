import logging
import os
from logging import getLogger

from termcolor import colored


max_name_len = 22


def make_logger(name: str, level: int = logging.INFO, verbose: bool = False) -> logging.Logger:
    # create logger
    name_len: int = min(len(name), max_name_len)
    name = name[:name_len]
    logger = getLogger(name)
    name_len = max_name_len

    colors = {
        'critical': 'red',
        'debug': 'magenta',
        'error': 'red',
        'info': None,
        'notice': 'magenta',
        'spam': 'green',
        'success': 'green',
        'verbose': 'blue',
        'warning': 'yellow'
    }

    # color parts of the left bar
    levelname = colored("%(levelname)8s", "grey")
    filename_lineno = colored("%(filename)15s:%(lineno)-4s", "blue")

    # compile format
    format = f"%(name){name_len}s|{filename_lineno} - %(funcName)-15s : %(message)s" \
        if verbose else f"%(name){name_len}s|{levelname} : %(message)s"
    indent = " " * ((40 if verbose else 10) + name_len)

    class CustomFilter(logging.Filter):
        def filter(self, record):
            if not isinstance(record.msg, str):
                record.msg = str(record.msg)
            lines = record.msg.split("\n")
            color = colors[record.levelname.lower()]
            lines = map(lambda l: colored(l, color) if color else l, lines)
            record.msg = f"\n{indent}: ".join(lines)
            return super(CustomFilter, self).filter(record)

    # handle multi-line messages
    logger.addFilter(CustomFilter())

    # create console handler
    ch = logging.StreamHandler()
    # create formatter and add it to the handlers
    formatter = logging.Formatter(format)
    ch.setFormatter(formatter)
    # add the handlers to logger
    logger.addHandler(ch)

    base_set_level = getattr(logger, "setLevel")

    def update_logger(lvl: int):
        # set level
        base_set_level(lvl)
        ch.setLevel(lvl)

    # replace original setLevel in the logger
    setattr(logger, "setLevel", update_logger)

    # set INFO as default level
    logger.setLevel(level)

    # environment given logging level
    if os.environ.get("SKYNET_DEBUG", "").lower() in ["1", "y", "yes"]:
        logger.setLevel(logging.DEBUG)

    # ---
    return logger


salogger: logging.Logger = make_logger("skynet:app")


__all__ = [
    "salogger"
]
