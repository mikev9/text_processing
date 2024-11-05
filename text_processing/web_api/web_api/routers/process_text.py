from fastapi import APIRouter
from fastapi import Response
from fastapi import status

from shared.db.models.tasks import TaskDTO
from shared.db.exceptions import AlreadyExistsError

from web_api.schemas.process_text import ProcessTextRequest
from web_api.schemas.process_text import ProcessTextResponse
from web_api.dependencies.logging import LoggerDep
from web_api.dependencies.tasks import ProducerDep
from web_api.dependencies.tasks import TaskSaveDep
from web_api.dependencies.tasks import TaskExistsDep


router = APIRouter(
    tags=['process-text'],
)


@router.post(
    '/process-text',
    response_model=ProcessTextResponse,
    status_code=status.HTTP_201_CREATED,
)
async def process_text(
    text_item: ProcessTextRequest,
    producer: ProducerDep,
    save_task: TaskSaveDep,
    task_exists: TaskExistsDep,
    response: Response,
    logger: LoggerDep,
) -> dict:
    task_id = text_item.task_id
    resp = {'task_id': task_id}

    if await task_exists(task_id):
        logger.warning('Task "%s" already exists', task_id)
        response.status_code = 200
        return resp

    task_dto = TaskDTO.model_validate(
        dict(
            original_text=text_item.text,
            type=text_item.type,
        )
    )

    await producer.send(
        task_id=task_id,
        data=task_dto.model_dump(),
    )

    try:
        await save_task(task_id=task_id)
    except AlreadyExistsError:
        logger.warning('Task "%s" already exists', task_id)
        response.status_code = 200

    return resp
