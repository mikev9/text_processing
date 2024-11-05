import logging
from typing import Any
from typing import cast
from typing import Self
from uuid import uuid4
from uuid import UUID

import orjson
import aiormq
import aio_pika

from shared.logging import get_app_logger


class ProducerError(Exception):
    pass


class PublishError(ProducerError):
    pass


class Producer:
    def __init__(
        self,
        conn_url: str,
        exchange_name: str,
        queue_name: str,
        routing_key: str,
        persistent: bool=False,
        publisher_confirms: bool=True,
        app_name: str='',
        logger: logging.Logger | None=None,
    ) -> None:
        self._log = logger or get_app_logger()
        self._conn_url = conn_url
        self._exchange_name = exchange_name
        self._queue_name = queue_name
        self._routing_key = routing_key
        self._persistent = persistent
        self._publisher_confirms = publisher_confirms
        self._app_name = app_name
        self._connection: aio_pika.abc.AbstractConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._queue: aio_pika.abc.AbstractQueue | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None
        self._started = False
        self._shutdown_is_pending = False

    async def startup(self) -> None:
        self._log.info('Starting the producer..')

        if self._started:
            raise RuntimeError('Producer already started.')

        self._log.info('Connecting to message broker..')
        self._connection = await aio_pika.connect_robust(self._conn_url)

        self._log.info('Opening the channel..')
        self._channel = cast(
            aio_pika.abc.AbstractChannel,
            await self._connection.channel(
                publisher_confirms=self._publisher_confirms,
            )
        )

        self._log.info('Creating the exchange..')
        self._exchange = await self._channel.declare_exchange(
            name=self._exchange_name,
            type=aio_pika.abc.ExchangeType.DIRECT,
            durable=True,
        )

        self._log.info('Creating the queue..')
        self._queue = await self._channel.declare_queue(
            name=self._queue_name,
            durable=True,
        )
        await self._queue.bind(self._exchange_name, routing_key=self._routing_key)

        self._started = True
        self._log.info('Producer successfully started.')

    async def shutdown(self) -> None:
        self._log.info('The shutdown process has been initiated..')

        if self._shutdown_is_pending:
            raise RuntimeError('The shutdown process already started.')

        self._shutdown_is_pending = True

        if self._channel:
            self._log.info('Channel closing..')
            await self._channel.close()

        if self._connection:
            self._log.info('Connection closing..')
            await self._connection.close()

        self._log.info('Producer successfully stopped.')

    async def send(self, data: Any, task_id: str | int | UUID | None=None) -> str:
        if not self._started:
            raise RuntimeError(
                'Producer has not been started. Call `startup()` before '
                'using this method.'
            )

        exchange = cast(aio_pika.abc.AbstractExchange, self._exchange)

        match task_id:
            case None:
                task_id = uuid4().hex
            case UUID():
                task_id = task_id.hex
            case int():
                task_id = str(task_id)

        message = aio_pika.Message(
            body=orjson.dumps(data),
            message_id=task_id,
            app_id=self._app_name,
            delivery_mode=(
                aio_pika.DeliveryMode.PERSISTENT if self._persistent else None
            ),
        )

        try:
            confirmation = await exchange.publish(
                message=message,
                routing_key=self._routing_key,
            )
        except Exception as exc:
            raise PublishError('Publish error', exc)

        if not isinstance(confirmation, aiormq.spec.Basic.Ack):
            raise PublishError(
                'Message was not acknowledged by broker!',
                confirmation,
            )

        return task_id

    async def __aenter__(self) -> Self:
        await self.startup()
        return self

    async def __aexit__(self, *_):
        await self.shutdown()
