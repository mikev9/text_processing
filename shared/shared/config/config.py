import os
import logging
from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class SharedConfig(BaseSettings):
    """Configuration shared across all services."""
    model_config = SettingsConfigDict(env_file='.env.shared')

    log_level: str | int = logging.DEBUG
    log_record_max_len: int = 1000
    log_fmt: str | None = (
        '[%(levelname)s] %(asctime)s [%(name)s][%(pathname)s:%(lineno)d][%(funcName)s]: %(message)s'
    )
    #db_path: str = '~/projects/text_processing/db.sqlite3'
    db_filename: str = 'db.sqlite3'
    db_path: Path = Path(__file__).parents[3].joinpath(
        'docker_data/db/',
        db_filename,
    )  # {project_root}/docker_data/db/db.sqlite3
    db_engine_echo: bool = False
    asyncio_debug: bool = False  # Enables "asyncio debug mode"
    asyncio_log_level: str | int = logging.DEBUG
    asyncio_slow: float = 0.1  # loop.slow_callback_duration = 0.1(100 milliseconds)
    rabbitmq_uri: str = 'amqp://guest:guest@localhost:5672'
    rabbitmq_vhost: str = '/'
    rabbitmq_exchange: str = 'text_processing_exchange'
    rabbitmq_queue: str = 'text_processing_queue'
    rabbitmq_routing_key: str = 'text_processing'


class WebAPIConfig(SharedConfig):
    model_config = SettingsConfigDict(env_file='.env.web_api')

    app_name: str = 'web_api'
    web_api_host: str = '127.0.0.1'
    web_api_port: int = 8000
    username: str = 'guest'
    password: str = 'guest'
    disable_auth: bool = False
    producer_persistent: bool = True  # Instructs RabbitMQ to persist the message queue to disk
    producer_publisher_confirms: bool = True  # RabbitMQ must acknowledge the receipt of published messages
    article_max_length: int = 1_000_000  # 1 MB for Latin characters


class TaskProcessorConfig(SharedConfig):
    model_config = SettingsConfigDict(env_file='.env.task_processor')

    app_name: str = 'task_processor'
    consumer_workers_num: int | None = len(os.sched_getaffinity(0))
    consumer_prefetch_count: int | None = None  # If `None`, it is automatically set by the consumer


shared_config = SharedConfig()
web_api_config = WebAPIConfig()
task_processor_config = TaskProcessorConfig()
