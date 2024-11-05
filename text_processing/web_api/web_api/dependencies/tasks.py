import asyncio
from uuid import UUID
from functools import partial
from typing import Annotated
from typing import Callable
from typing import Awaitable

from fastapi import Depends
from fastapi import Request

from shared.db.core import Session
from shared.db.models import Task
from shared.dist_tasks.producer import Producer


def _save_task(task_id: UUID, **values) -> None:
    with Session() as session:
        try:
            Task.create(session=session, task_id=task_id, **values)
            session.commit()
        except Exception:
            session.rollback()
            raise


async def _save_task_async(task_id: UUID, **values) -> None:
    await asyncio.get_running_loop().run_in_executor(
        None,
        partial(_save_task, task_id=task_id, **values),
    )


def _get_task(task_id: UUID) -> Task | None:
    with Session() as session:
        res = session.get(Task, task_id)

        if res:
            session.expunge(res)

        return res


async def _get_task_async(task_id: UUID) -> Task | None:
    return await asyncio.get_running_loop().run_in_executor(None, _get_task, task_id)


def _task_exists(task_id: UUID) -> bool:
    with Session() as session:
        return Task.exists(session=session, task_id=task_id)


async def _task_exists_async(task_id: UUID) -> bool:
    return await asyncio.get_running_loop().run_in_executor(None, _task_exists, task_id)


def _get_producer(request: Request) -> Producer:
    return request.app.state.producer


TaskSaveDep = Annotated[Callable[..., Awaitable[None]], Depends(lambda: _save_task_async)]
TaskGetDep = Annotated[Callable[[UUID], Awaitable[Task]], Depends(lambda: _get_task_async)]
TaskExistsDep = Annotated[Callable[[UUID], Awaitable[bool]], Depends(lambda: _task_exists_async)]
ProducerDep = Annotated[Producer, Depends(_get_producer)]
