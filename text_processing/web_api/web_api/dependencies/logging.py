from typing import Annotated
from logging import Logger

from fastapi import Depends

from shared.logging import get_app_logger


LoggerDep = Annotated[Logger, Depends(get_app_logger)]
