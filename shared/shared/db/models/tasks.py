import datetime
from uuid import uuid4
from uuid import UUID
from enum import StrEnum

from sqlalchemy import DateTime
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from pydantic import BaseModel
from pydantic import field_validator
from sqlmodel import SQLModel
from sqlmodel import Field
from sqlmodel import Enum
from sqlmodel import Column
from sqlmodel import Session
from sqlmodel import insert
from sqlmodel import select

from shared.utils import utcnow

from ..exceptions import AlreadyExistsError


class TaskStatus(StrEnum):
    pending = 'pending'
    completed = 'completed'
    failed = 'failed'
    failed_final = 'failed_final'  # The final status: reprocessing will lead to the same result and therefore is pointless.


class TextTypeEnum(StrEnum):
    chat_item = 'chat_item'
    summary = 'summary'
    article = 'article'


class TaskDTO(BaseModel):
    original_text: str
    type: TextTypeEnum


    @field_validator('original_text')
    def validate_non_empty(cls, value):
        if value.strip():
            return value
        else:
            raise ValueError(
                'The string must contain at least one non-whitespace character'
            )


class Task(SQLModel, table=True):
    __tablename__: str = 'tasks'  # type: ignore

    task_id: UUID = Field(default_factory=uuid4, primary_key=True)
    original_text: str | None = None
    processed_text: str | None = None
    word_count: int | None = None
    language: str | None = None
    status: TaskStatus = Field(
        default=TaskStatus.pending,
        sa_column=Column(
            Enum(TaskStatus),
            default=TaskStatus.pending,
        ),
    )
    type: TextTypeEnum = Field(
        sa_column=Column(
            Enum(TextTypeEnum),
        ),
    )
    cause: str | None = None
    created_at: datetime.datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(),
            default=utcnow,
            index=True,
        ),
    )
    updated_at: datetime.datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(),
            default=lambda ctx: ctx.get_current_parameters()['created_at'],
            index=True,
        ),
    )

    @classmethod
    def create(cls, session: Session, **values):
        try:
            session.exec(
                insert(cls.__table__).values(values)  # type: ignore
            )
        except IntegrityError as exc:
            if exc.orig and ('UNIQUE constraint failed' in exc.orig.args[0]):
                raise AlreadyExistsError from exc

            raise

    @classmethod
    def upsert(cls, session: Session, **values):
        insert_stmt = sqlite_insert(cls.__table__).values(values)  # type: ignore # type: ignore
        do_update_stmt = insert_stmt.on_conflict_do_update(
            index_elements=['task_id'],
            set_=values,
        )
        session.exec(do_update_stmt)  # type: ignore

    @classmethod
    def exists(cls, session: Session, task_id: UUID) -> bool:
        return bool(session.execute(select(cls.task_id).where(cls.task_id == task_id)).scalar())
