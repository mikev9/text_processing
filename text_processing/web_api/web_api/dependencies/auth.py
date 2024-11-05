import secrets
from typing import Annotated

from fastapi import status
from fastapi import Depends
from fastapi import HTTPException
from fastapi.security import HTTPBasic
from fastapi.security import HTTPBasicCredentials

from .users import UserCredDep
from .config import ConfigDep


security = HTTPBasic(auto_error=False)


def _verify_basic_http_cred(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(security)],
    get_user_cred: UserCredDep,
    config: ConfigDep,
) -> None:
    if config.disable_auth:
        return

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Basic"},
        )

    username = credentials.username
    current_username_bytes = username.encode("utf8")
    correct_username_bytes, correct_password_bytes = [
        x.encode() for x in get_user_cred(username)]
    is_correct_username = secrets.compare_digest(
        current_username_bytes, correct_username_bytes
    )
    current_password_bytes = credentials.password.encode("utf8")
    is_correct_password = secrets.compare_digest(
        current_password_bytes, correct_password_bytes
    )

    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )


BasicHttpAuthDep = Depends(_verify_basic_http_cred)
