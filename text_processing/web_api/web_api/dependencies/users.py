from typing import Annotated
from typing import Callable

from fastapi import Depends

from shared.config import web_api_config as config


def _get_user_creds(username: str) -> tuple[str, str]:
    return config.username, config.password


UserCredDep = Annotated[Callable[[str], tuple[str, str]], Depends(lambda: _get_user_creds)]
