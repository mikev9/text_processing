import time
import asyncio
from urllib import parse
from typing import Any
from typing import cast
from typing import TypedDict
from typing import Literal
from dataclasses import dataclass
from dataclasses import field

import aiohttp
import uvloop
from sqlalchemy import text

from shared.logging import setup_app_logger
from shared.config import shared_config as config
from shared.config import web_api_config
from shared.db.core import Session
from shared.db.core import create_db
from shared.db.models.tasks import TextTypeEnum
from shared.db.models.tasks import TaskStatus
from text_processing.web_api.web_api.schemas.process_text import ProcessTextRequest
from text_processing.web_api.web_api.schemas.process_text import ProcessTextResponse


logger = setup_app_logger('test_requests')


SAMPLE = (
    "Hey!/// Just wanted to confirm if we're still meeting for lunch "
    "tomorrow at 12 pm."
)
TEXT_SIZE = 1_000_000  # 1 MB for Latin characters
REQUESTS_COUNT = 100
CONN_LIMIT = 1000
BASE_URL = f'http://{web_api_config.web_api_host}:{web_api_config.web_api_port}'
PROCESS_TEXT_PATH = '/process-text'
RESULTS_PATH = '/results/{task_id}'
POLLING_INTERVAL = 2.  # sec
POLLING_LIMIT = 100
USERNAME = web_api_config.username
PASSWORD = web_api_config.password

unknown_status: Literal['unknown'] = 'unknown'


class StagingTimestamps(TypedDict):
    start_creating: float
    end_creating: float
    start_waiting: float
    end_waiting: float


@dataclass
class TaskResult:
    task_id: str
    ok: bool = field(default=False)
    status: TaskStatus | Literal['unknown'] = field(default=unknown_status)


def truncate_table_tasks():
    # SQLite truncate: https://sqlite.org/lang_delete.html#the_truncate_optimization
    with Session() as dbs:
        dbs.exec(text('DELETE FROM tasks'))  # type: ignore
        dbs.commit()
        dbs.exec(text('VACUUM'))  # type: ignore


async def fetch(
    session: aiohttp.ClientSession,
    method: str,
    path: str,
    data: Any=None,
) -> Any:
    async with getattr(session, method)(path, data=data) as resp:
        return await resp.json()


async def purge_rabbitmq_queue(
    uri: str=config.rabbitmq_uri,
    vhost: str=config.rabbitmq_vhost,
    queue_name: str=config.rabbitmq_queue,
):
    if '/' in vhost:
        vhost = parse.quote(vhost, safe='')

    uri = uri.rstrip('/')
    p = parse.urlparse(uri)

    async with aiohttp.ClientSession(
        headers={'content-type': 'application/json'},
        auth=aiohttp.BasicAuth(cast(str, p.username), cast(str, p.password)),
    ) as session:
        async with session.delete(
            f'http://{p.hostname}:15672/api/queues/{vhost}/{queue_name}/contents',
        ) as resp:
            if resp.ok:
                logger.info('RabbitMQ queue "%s:" successfully purged', queue_name)
                return resp
            elif resp.status == 404:
                raise Exception(f'RabbitMQ queue "{queue_name}" not found')
            elif resp.status == 401:
                raise Exception(
                    'Unable to purge RabbitMQ queue: Invalid rabbitmq auth', resp)
            else:
                raise Exception(
                    f'Error while purging RabbitMQ queue "{queue_name}": {resp!r}', resp)


def generate_text(length: int, sample: str) -> str:
    result = (
        (sample + ' ') * (length // (len(sample) + 1)) +
        sample[:length % (len(sample) + 1)]
    )
    return result[:length]


def generate_request_data(
    text_size: int,
    requests_count: int,
    sample: str,
) -> list[ProcessTextRequest]:
    match text_size:
        case text_size if 0 < text_size <= 300:
            text_type = TextTypeEnum.chat_item
        case text_size if text_size <= 3_000:
            text_type = TextTypeEnum.summary
        case text_size if 300_000 <= text_size <= web_api_config.article_max_length:
            text_type = TextTypeEnum.article
        case _:
            raise ValueError(
                f'Invalid text_size: "{text_size}": 0 < text_size <= 300 or '
                f'300 < text_size <= 3_000 or 300_000 <= text_size <= {web_api_config.article_max_length}'
            )

    return [
        ProcessTextRequest.model_validate(
            dict(
                text=generate_text(
                    length=text_size,
                    sample=sample,
                ),
                type=text_type,
            ),
        )
        for _ in range(requests_count)
    ]


def serialize_request_data(requests_data: list[ProcessTextRequest]) -> list[str]:
    return [x.model_dump_json() for x in requests_data]


async def process_text_request(
    session: aiohttp.ClientSession,
    path: str,
    data: str,
) -> dict:
    resp = await fetch(
        session=session,
        method='post',
        path=path,
        data=data,
    )
    logger.debug('task created: %s', resp['task_id'])
    return resp


async def create_process_text_tasks(
    requests_data: list[str],
    conn_limit: int,
    base_url: str,
    process_text_path: str,
    username: str,
    password: str
) -> list[ProcessTextResponse]:
    connector = aiohttp.TCPConnector(limit=conn_limit)

    async with aiohttp.ClientSession(
        base_url,
        connector=connector,
        headers={'content-type': 'application/json'},
        auth=aiohttp.BasicAuth(username, password)
    ) as session:
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(
                    process_text_request(
                        session=session,
                        path=process_text_path,
                        data=data,
                    )
                ) for data in requests_data
            ]

    return [ProcessTextResponse.model_validate(task.result()) for task in tasks]


async def wait_for_task(
    session: aiohttp.ClientSession,
    task_id: str,
    results_path: str,
    polling_interval: int | float,
    polling_limit: int | None,
) -> TaskResult:
    path = results_path.format(task_id=task_id)
    final_statuses = {TaskStatus.completed, TaskStatus.failed_final}

    if polling_limit and polling_limit < 0:
        raise Exception(f'Invalid polling_limit {polling_limit}')

    limit = polling_limit or True
    status = unknown_status

    while limit:
        if polling_limit:
            limit -= 1

        await asyncio.sleep(polling_interval)
        resp = await fetch(
            session=session,
            method='get',
            path=path,
        )

        try:
            status = resp['status']

            if status in final_statuses:
                logger.info('Task "%s" finished with status "%s"', task_id, status)
                return TaskResult(
                    task_id=task_id,
                    ok=True if status == TaskStatus.completed else False,
                    status=status,
                )
            elif status == TaskStatus.failed:
                logger.warning('Temporary task failure("failed"): "%s"', task_id)
        except Exception as exc:
            logger.debug(
                'An error occurred while polling the task status. '
                'Task: "%s", exc: "%r", resp: "%s"', task_id, exc, resp)
            raise

    logger.warning('Polling limit reached for task: "%s"', task_id)
    return TaskResult(task_id=task_id)


async def wait_for_all_tasks_completion(
    task_ids: list[ProcessTextResponse],
    conn_limit: int,
    base_url: str,
    results_path: str,
    username: str,
    password: str,
    polling_interval: int | float,
    polling_limit: int | None
) -> list[TaskResult]:
    connector = aiohttp.TCPConnector(limit=conn_limit)

    async with aiohttp.ClientSession(
        base_url,
        connector=connector,
        auth=aiohttp.BasicAuth(username, password)
    ) as session:
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(
                    wait_for_task(
                        session=session,
                        task_id=x.task_id.hex,
                        results_path=results_path,
                        polling_interval=polling_interval,
                        polling_limit=polling_limit,
                    )
                ) for x in task_ids
            ]

    return [task.result() for task in tasks]


async def test_process_text(
    requests_data: list[str],
    conn_limit: int,
    base_url: str,
    process_text_path: str,
    results_path: str,
    username: str,
    password: str,
    polling_interval: int | float,
    polling_limit: int | None,
) -> tuple[StagingTimestamps, list[TaskResult]]:
    ts: StagingTimestamps = {
        'start_creating': 0.,
        'end_creating': 0.,
        'start_waiting': 0.,
        'end_waiting': 0.,
    }
    ts['start_creating'] =  time.time()

    created_task_ids = await create_process_text_tasks(
        requests_data=requests_data,
        conn_limit=conn_limit,
        base_url=base_url,
        process_text_path=process_text_path,
        username=username,
        password=password,
    )

    ts['end_creating'] = time.time()
    ts['start_waiting'] = time.time()

    task_results = await wait_for_all_tasks_completion(
        task_ids=created_task_ids,
        conn_limit=conn_limit,
        base_url=base_url,
        results_path=results_path,
        username=username,
        password=password,
        polling_interval=polling_interval,
        polling_limit=polling_limit,
    )

    ts['end_waiting'] = time.time()

    return ts, task_results


def main(
    text_size: int=TEXT_SIZE,
    requests_count: int=REQUESTS_COUNT,
    conn_limit: int=CONN_LIMIT,
    sample: str=SAMPLE,
    base_url: str=BASE_URL,
    process_text_path: str=PROCESS_TEXT_PATH,
    results_path: str=RESULTS_PATH,
    username: str=USERNAME,
    password: str=PASSWORD,
    polling_interval: int | float=POLLING_INTERVAL,
    polling_limit: int | None=POLLING_LIMIT,
    purge_db: bool = False
) -> None:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    # Deleting old data if it exists.
    asyncio.run(purge_rabbitmq_queue())

    if purge_db:
        logger.warning('Clearing the tasks table. Note: This may take a few minutes for a large table.')
        truncate_table_tasks()

    create_db()

    # generate test requests data
    requests_data = serialize_request_data(
        requests_data=generate_request_data(
            text_size=text_size,
            requests_count=requests_count,
            sample=sample,
        ),
    )

    ts, task_results = asyncio.run(
        test_process_text(
            requests_data=requests_data,
            conn_limit=conn_limit,
            base_url=base_url,
            process_text_path=process_text_path,
            results_path=results_path,
            username=username,
            password=password,
            polling_interval=polling_interval,
            polling_limit=polling_limit,
        ),
    )

    completed = []
    failed_final = []
    unknown = []

    for t in task_results:
        match t.status:
            case TaskStatus.completed:
                completed.append(t)
            case TaskStatus.failed_final:
                failed_final.append(t)
            case x if x == unknown_status:
                unknown.append(t)
            case _:
                raise Exception('Unexpected task status', t)

    completed_count = len(completed)
    failed_final_count = len(failed_final)
    unknown_count = len(unknown)

    print(
        f'text size: {text_size}\n'
        f'requests: {requests_count}\n'
        f'creating time: {ts["end_creating"] - ts["start_creating"]}\n'
        f'waiting time: {ts["end_waiting"] - ts["start_waiting"]}\n'
        f'total time: {ts["end_waiting"] - ts["start_creating"]}\n'
        f'task completed: {completed_count}\n'
        f'task failed_final: {failed_final_count}\n'
        f'task unknown: {unknown_count}\n'
    )


if __name__ == '__main__':
    main()
