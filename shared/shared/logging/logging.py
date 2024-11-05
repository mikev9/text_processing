import logging

FMT = '[%(levelname)s] %(asctime)s [%(name)s][%(pathname)s:%(lineno)d][%(funcName)s]: %(message)s'

_logger = None

class LimitedLengthFormatter(logging.Formatter):
    def __init__(self, fmt=None, max_length: int=1000, *args, **kwargs):
        super().__init__(fmt, *args, **kwargs)
        self.max_length = max_length

    def format(self, record):
        original_message = record.getMessage()

        if len(original_message) > self.max_length:
            record.msg = original_message[:self.max_length] + '...'
        return super().format(record)


def setup_app_logger(
    name: str,
    level: str | int =logging.DEBUG,
    max_length: int=1000,
    fmt: str | None=FMT,
) -> logging.Logger:
    global _logger

    if fmt is None:
        fmt = FMT

    _logger = logging.getLogger(name)
    _logger.setLevel(level)
    ch = logging.StreamHandler()
    ch.setFormatter(LimitedLengthFormatter(fmt, max_length))
    _logger.addHandler(ch)
    _logger.propagate = False

    return _logger


def get_app_logger() -> logging.Logger:
    if not _logger:
        return setup_app_logger(name='fallback_logger')

    return _logger
