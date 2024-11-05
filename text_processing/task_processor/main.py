import asyncio

import uvloop

from shared.config import task_processor_config as config
from shared.logging import setup_app_logger
from shared.db.core import create_db

from task_processor.consumer import Consumer


setup_app_logger(
    name=config.app_name,
    level=config.log_level,
    max_length=config.log_record_max_len,
    fmt=config.log_fmt,
)


async def main():
    create_db()

    async with Consumer(
        conn_url=config.rabbitmq_uri,
        exchange_name=config.rabbitmq_exchange,
        queue_name=config.rabbitmq_queue,
        routing_key=config.rabbitmq_routing_key,
        workers_num=config.consumer_workers_num,
        prefetch_count=config.consumer_prefetch_count,
    ) as consumer:
        await consumer.run()


if __name__ == '__main__':
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    asyncio.run(main())
