from contextlib import contextmanager
from pathlib import Path

from sqlmodel import SQLModel
from sqlmodel import create_engine
from sqlmodel import Session as SqlModelSession

from shared.config import shared_config as config


db_path = Path(config.db_path).expanduser()
db_path.parent.mkdir(parents=True, exist_ok=True)

connect_args = {
    'check_same_thread': False,
}
engine = create_engine(
    f'sqlite:///{db_path}',
    connect_args=connect_args,
    echo=config.db_engine_echo
)


def create_db():
    # Loading all models before creating the corresponding tables in the DB
    from . import models
    SQLModel.metadata.create_all(engine)


@contextmanager
def Session():
    session = SqlModelSession(engine)

    try:
        yield session
    finally:
        session.close()
