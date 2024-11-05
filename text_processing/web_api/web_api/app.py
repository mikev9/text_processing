from contextlib import asynccontextmanager
from fastapi import FastAPI
from shared.config import web_api_config as config
from shared.utils import asyncio_debug_mode
from shared.logging import setup_app_logger
from shared.db.core import create_db
from shared.dist_tasks.producer import Producer

from .dependencies.auth import BasicHttpAuthDep
from .routers import process_text
from .routers import task_result


setup_app_logger(
    name=config.app_name,
    level=config.log_level,
    max_length=config.log_record_max_len,
    fmt=config.log_fmt,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio_debug_mode(config)
    create_db()
    app.state.config = config
    app.state.producer = producer = Producer(
        conn_url=config.rabbitmq_uri,
        exchange_name=config.rabbitmq_exchange,
        queue_name=config.rabbitmq_queue,
        routing_key=config.rabbitmq_routing_key,
        persistent=config.producer_persistent,
        publisher_confirms=config.producer_publisher_confirms,
        app_name=config.app_name,
    )
    await producer.startup()

    yield

    await producer.shutdown()


app = FastAPI(
    title='Text Processing Web API',
    lifespan=lifespan,
    dependencies=[BasicHttpAuthDep],
)


app.include_router(process_text.router)
app.include_router(task_result.router)
