from typing import Annotated
from uuid import UUID

from fastapi import APIRouter
from fastapi import Path
from fastapi import HTTPException

from shared.db.models import Task
from web_api.dependencies.tasks import TaskGetDep


router = APIRouter(
    tags=['task-result'],
)


@router.get('/results/{task_id}')
async def process_text(
    task_id: Annotated[
        UUID,
        Path(
            title='Task Id',
            description='UUID4 Task Id',
            examples=['8c8b4e08-34ac-41f9-8cad-44b9f938180a'],
        )
    ],
    get_task: TaskGetDep,
) -> Task:
    task_result = await get_task(task_id)

    if task_result is None:
        raise HTTPException(status_code=404, detail='Task not found')

    return task_result
