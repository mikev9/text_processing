import os
import asyncio
import logging
import datetime

import psutil

from shared.config.config import SharedConfig


def cpu_count() -> int:
    """Returns the number of physical processors available to the process.
    For example, the process may run in a container with limitations.
    """
    phisical_cores = psutil.cpu_count(logical=False) or 1

    try:
        available_cores = len(os.sched_getaffinity(0)) or 1
    except AttributeError:
        available_cores = phisical_cores

    return min(phisical_cores, available_cores)


def utcnow() -> datetime.datetime:
    # timezone-aware
    return datetime.datetime.now(datetime.UTC)


def asyncio_debug_mode(config: SharedConfig):
    if config.asyncio_debug:
        logging.getLogger('asyncio').setLevel(config.asyncio_log_level)
        loop = asyncio.get_running_loop()
        loop.slow_callback_duration = config.asyncio_slow
        loop.set_debug(True)
