import os
import abc
import asyncio
import signal
import logging
from typing import cast
from typing import Any
from typing import Self
from concurrent.futures import ProcessPoolExecutor

import aio_pika

from shared.utils import cpu_count
from shared.logging import get_app_logger


class ConsumerError(Exception):
    pass


class DeterministicError(ConsumerError):
    """A deterministic error should be returned by the task if reprocessing
    will not change the result. In case of this error, the message should be
    discarded without the possibility of reprocessing(message.reject(requeue=False)).
    """
    pass


class Consumer(abc.ABC):
    def __init__(
        self,
        conn_url: str,
        exchange_name: str,
        queue_name: str,
        routing_key: str,
        workers_num: int | None=None,
        prefetch_count: int | None=None,
        graceful_shutdown: bool=True,
        logger: logging.Logger | None=None,
    ) -> None:
        self._log = logger or get_app_logger()
        self._conn_url = conn_url
        self._exchange_name = exchange_name
        self._queue_name = queue_name
        self._routing_key = routing_key
        self._connection: aio_pika.abc.AbstractConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None
        self._queue: aio_pika.abc.AbstractQueue | None = None
        self._workers_num: int = (
            workers_num if workers_num and workers_num > 0 else
            (cpu_count() - 1) or 1
        )  # One CPU is reserved for the main process.
        self._prefetch_count: int = prefetch_count or 2 * self._workers_num
        self._graceful_shutdown = graceful_shutdown
        self._started = False
        self._executor: ProcessPoolExecutor | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._consumer_tag: str = ''
        self._pending_tasks = set()
        self._sem: asyncio.Semaphore | None = None
        self._shutdown_event: asyncio.Event | None = None
        self._shutdown_is_pending = False

    @staticmethod
    @abc.abstractmethod
    def task(task_id: Any, data: bytes) -> Any:
        pass

    async def __aenter__(self) -> Self:
        await self.startup()
        return self

    async def __aexit__(self, *_):
        await self.shutdown()

    async def startup(self) -> None:
        self._log.info('Starting the consumer..')

        if self._started:
            raise RuntimeError('Consumer already started.')

        self._log.info('Connecting to message broker..')
        self._connection = await aio_pika.connect_robust(self._conn_url)

        self._log.info('Opening the channel..')
        self._channel = cast(
            aio_pika.abc.AbstractChannel,
            await self._connection.channel()
        )
        await self._channel.set_qos(prefetch_count=self._prefetch_count)

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

        self._log.info('Creating the executor..')
        self._executor = ProcessPoolExecutor(max_workers=self._workers_num)
        self._loop = asyncio.get_running_loop()
        self._shutdown_event = asyncio.Event()
        self._sem = asyncio.Semaphore(self._workers_num + 1)  # according to the size of the ProcessPoolExecutor call queue

        if self._graceful_shutdown:
            self._set_signal_handlers()

        self._started =True
        self._log.info(
            '[PID: %s] Consumer successfully started with "%s" workers and prefetch_count=%s.',
            os.getpid(),
            self._workers_num,
            self._prefetch_count,
        )

    async def shutdown(self) -> None:
        self._log.info('The shutdown process has been initiated..')

        if self._shutdown_is_pending:
            raise RuntimeError('The shutdown process already started.')

        self._shutdown_is_pending = True

        if self._consumer_tag and self._queue:
            self._log.info('Stopping the reception of new messages..')
            await self._queue.cancel(self._consumer_tag)

        self._log.info('Waiting for unfinished tasks..')
        await asyncio.gather(*self._pending_tasks)

        if self._executor:
            self._log.info('Waiting for the executor to finish..')
            self._executor.shutdown(wait=True)

        if self._channel:
            self._log.info('Channel closing..')
            await self._channel.close()

        if self._connection:
            self._log.info('Connection closing..')
            await self._connection.close()

        self._log.info('Consumer successfully stopped.')

    def _set_signal_handlers(self):
        loop = cast(asyncio.AbstractEventLoop, self._loop)
        shutdown_event = cast(asyncio.Event, self._shutdown_event)

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown_event.set)

    async def run(self):
        if not self._started:
            raise RuntimeError('Consumer has not been started.')

        shutdown_event = cast(asyncio.Event, self._shutdown_event)
        queue = cast(aio_pika.abc.AbstractQueue, self._queue)
        self._consumer_tag = await queue.consume(self._on_message)
        await shutdown_event.wait()

    async def _on_message(self, message: aio_pika.abc.AbstractIncomingMessage):
        loop = cast(asyncio.AbstractEventLoop, self._loop)
        sem = cast(asyncio.Semaphore, self._sem)
        task_id = cast(str, message.message_id)

        if not (task_id and isinstance(task_id, str)):
            self._log.error('task_id must be non-empty string')
            await message.reject(requeue=False)
            return

        self._log.debug('A new task has been received: %s', task_id)

        async def handle_message():
            self._log.debug('The task %s will be sent to the executor.', task_id)

            try:
                async with sem:
                    await loop.run_in_executor(
                        self._executor,
                        self.task,
                        task_id,
                        message.body,
                    )
                await message.ack()
            except DeterministicError as exc:
                await message.reject(requeue=False)
                self._log.error(
                    'Deterministic error, task will be rejected: %s %r',
                    task_id,
                    exc,
                )
            except BaseException as exc:
                await message.nack(requeue=True)
                self._log.error('Failed to process task %s: %r', task_id, exc)
            else:
                self._log.debug('The task was successfully processed: %s', task_id)

        task = asyncio.create_task(handle_message())
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)
