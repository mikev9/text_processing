import os
from uuid import UUID
from typing import Any

import orjson
from pydantic import ValidationError

from shared.logging import get_app_logger
from shared.dist_tasks.consumer import Consumer as BaseConsumer
from shared.dist_tasks.consumer import DeterministicError
from shared.utils import utcnow
from shared.db.core import Session
from shared.db.models.tasks import Task
from shared.db.models.tasks import TaskDTO
from shared.db.models.tasks import TaskStatus

from .text_utils import count_words
from .text_utils import detect_language
from .text_utils import clean_text
from .text_utils import LangDetectError


COMPLETED = TaskStatus.completed
FAILED = TaskStatus.failed
FAILED_FIN = TaskStatus.failed_final


def _upsert(**values):
    with Session() as session:
        try:
            Task.upsert(session, updated_at=utcnow(), **values)
            session.commit()
        except Exception:
            session.rollback()
            raise


class Consumer(BaseConsumer):
    @staticmethod
    def task(task_id: Any, data: bytes) -> None:
        log = get_app_logger()
        log.debug('Received task: %s, pid: %s', task_id, os.getpid())

        try:
            task_id = UUID(task_id)
        except Exception as exc:
            # No task_id, so nothing is written to the database.
            raise DeterministicError('Invalid task_id(must be UUID string)')

        try:
            dto = TaskDTO.model_validate(orjson.loads(data))
        except orjson.JSONDecodeError as exc:
            _upsert(task_id=task_id, status=FAILED_FIN, cause='Invalid JSON')
            raise DeterministicError(exc)
        except ValidationError as exc:
            _upsert(task_id=task_id, status=FAILED_FIN, cause='Invalid task DTO')
            raise DeterministicError(exc)

        try:
            word_count = count_words(dto.original_text)
            language = detect_language(dto.original_text)
            processed_text = clean_text(dto.original_text)
        except LangDetectError as exc:
            _upsert(
                task_id=task_id,
                original_text=dto.original_text,
                status=FAILED_FIN,
                type=dto.type,
                cause='lang detect error',
            )
            raise DeterministicError(exc)
        except Exception as exc:
            _upsert(
                task_id=task_id,
                original_text=dto.original_text,
                status=FAILED,
                type=dto.type,
                cause='fake error 222',
            )
            raise

        _upsert(
            task_id=task_id,
            original_text=dto.original_text,
            processed_text=processed_text,
            word_count=word_count,
            language=language,
            status=COMPLETED,
            type=dto.type,
        )
