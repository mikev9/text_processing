from typing import Annotated

from fastapi import Depends
from fastapi import Request
from shared.config.config import WebAPIConfig


def _get_config(request: Request) -> WebAPIConfig:
    return request.app.state.config


ConfigDep = Annotated[WebAPIConfig, Depends(_get_config)]
