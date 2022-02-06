import json
import logging
import traceback
import uuid
from typing import Optional


def make_id() -> str:
    return str(uuid.uuid4())


def print_exc(e: BaseException, logger: Optional[logging.Logger] = None):
    error_msg = "\n".join(traceback.format_exception(type(e), e, e.__traceback__))
    if logger is not None:
        logger.error(error_msg)
    else:
        print(error_msg)


def pretty(data: dict) -> str:
    return json.dumps(data, indent=4, sort_keys=True)
