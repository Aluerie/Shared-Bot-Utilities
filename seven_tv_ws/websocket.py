from __future__ import annotations

import asyncio
import atexit
import json
import logging
import signal
import socket
from typing import TYPE_CHECKING, Any, Self, override

import aiohttp
import websockets

from .exceptions import (
    NoActiveSubscriptionsError,
    NoActiveWSConnectionError,
    SubscriptionError,
    WSConnectionError,
)
from .models import (
    Ack,
    Dispatch,
    EndOfStream,
    Error,
    Heartbeat,
    Hello,
    Reconnect,
    ResponseTypes,
    SubscriptionData,
    WebsocketMessageType,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

_log = logging.getLogger(__name__)
_log.setLevel(logging.INFO)

# https://docs.astral.sh/ruff/rules/asyncio-dangling-task/
# # TODO: learn async to write a saner solution
# _background_tasks: set[asyncio.Task[Any]] = set()


# def add_to_background_tasks(coro: Coroutine[Any, Any, None]) -> None:
#     task = asyncio.create_task(coro)
#     _background_tasks.add(task)
#     task.add_done_callback(_background_tasks.discard)


class SevenTVWebSocket:
    """7TV WebSocket."""

    def __init__(
        self,
        callback: Callable[[ResponseTypes], Coroutine] | None = None,
        websocket_url: str | None = None,
    ) -> None:
        self.WS_URL: str = websocket_url or "wss://events.7tv.io/v3"
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self.handler: asyncio.Task | None = None

        self.queue: asyncio.Queue | None = None
        self.session_id: str | None = None
        self.subscription_limit: int = 500
        self.subscriptions: list[SubscriptionData] = []
        self.callback = callback

        atexit.register(self._close_sync)
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        await self.close()

    def __aiter__(self) -> Self:
        if not self.closed:
            self.queue = asyncio.Queue()
            return self
        raise StopAsyncIteration

    async def __anext__(self):
        if self.queue is None:
            raise StopAsyncIteration
        return await self.queue.get()

    @override
    def __str__(self) -> str:
        return f"<EventApi session_id='{self.session_id}' subscription_limit={self.subscription_limit} closed={self.closed}>"

    @property
    def closed(self) -> bool:
        """Closed."""
        return self.ws is None or self.ws.closed

    def _close_sync(self) -> None:
        if not self.closed:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.close())
            else:
                asyncio.run(self.close())

    def _handle_exit(self, signum, frame) -> None:
        self._close_sync()

    async def connect(self) -> None:
        """Connect."""
        try:
            async with aiohttp.ClientSession() as session:
                self.ws = await session.ws_connect(self.WS_URL)
                session.detach()
            # self.ws = await websockets.connect()
            self.handler = asyncio.create_task(self.message_handler())
        except websockets.exceptions.WebSocketException, socket.gaierror:
            raise WSConnectionError from None

    async def reconnect(self) -> None:
        """Reconnect."""
        await self.close()
        await self.connect()

    async def close(self) -> None:
        """Close."""
        if self.handler:
            try:
                self.handler.cancel()
                await self.handler
            except asyncio.CancelledError:
                pass
            self.handler = None
        if self.ws and not self.closed:
            await self.ws.close()
        self.ws = None

    async def message_handler(self) -> None:
        """message_handler."""
        assert self.ws

        try:
            while True:
                message = await self.ws.receive()
                if isinstance(message, bytes):
                    message = message.decode("utf-8")
                _log.debug(f"Received message: {message}")
                asyncio.create_task(self.on_message(message))
        except Exception as e:
            _log.exception(f"Error in message handler: {e}")
            await self.reconnect()

    async def on_message(self, message: str) -> None:
        message = json.loads(message.data)
        parsed_message = await self.parse_message(message)
        if self.queue:
            await self.queue.put(parsed_message)
        if self.callback and parsed_message:
            try:
                await self.callback(parsed_message)
            except Exception as e:
                _log.exception("Error in callback: %s", e)

    async def parse_message(self, message: dict[str, Any]) -> ResponseTypes | None:
        """Parse Message."""
        assert self.ws

        message_data = message.get("d")
        message_code = message.get("op")

        if message_code == WebsocketMessageType.DISPATCH:
            return Dispatch(message_data)
        if message_code == WebsocketMessageType.HELLO:
            parsed_message = Hello(message_data)
            if self.session_id:
                asyncio.create_task(self.ws.send_str(json.dumps({"op": 34, "d": {"session_id": self.session_id}})))
            self.session_id = parsed_message.session_id
            self.subscription_limit = parsed_message.subscription_limit
            return parsed_message
        if message_code == WebsocketMessageType.HEARTBEAT:
            return Heartbeat(message_data)
        if message_code == WebsocketMessageType.RECONNECT:
            asyncio.create_task(self.reconnect())
            return Reconnect(message_data)
        if message_code == WebsocketMessageType.ACK:
            parsed_message = Ack(message_data)
            if parsed_message.command == "RESUME":
                status = parsed_message.data.get("success", 0)
                _log.info(f"RESUMED session {self.session_id} with status {status}")
                if not status:
                    for s in self.subscriptions:
                        await self.ws.send_str(json.dumps({"op": 35, "d": s.data}))
            return parsed_message
        if message_code == WebsocketMessageType.ERROR:
            return Error(message_data)
        if message_code == WebsocketMessageType.END_OF_STREAM:
            parsed_message = EndOfStream(message_data)
            if parsed_message.should_reconnect:
                asyncio.create_task(self.reconnect())
            return parsed_message
        return None

    async def subscribe(self, subscription_data: SubscriptionData) -> None:
        """Subscribe."""
        assert self.ws

        if self.closed:
            raise NoActiveWSConnectionError
        if len(self.subscriptions) + 1 > self.subscription_limit:
            raise SubscriptionError(limit=self.subscription_limit)
        if subscription_data not in self.subscriptions:
            self.subscriptions.append(subscription_data)
            await self.ws.send_str(json.dumps({"op": 35, "d": subscription_data.data}))
        else:
            _log.warning("Attempted to subscribe to already existing subscription.")

    async def unsubscribe(self, subscription_data: SubscriptionData) -> None:
        """Unsubscribe."""
        assert self.ws

        if self.closed:
            raise NoActiveWSConnectionError
        if len(self.subscriptions) == 0:
            raise NoActiveSubscriptionsError
        if subscription_data in self.subscriptions:
            self.subscriptions.remove(subscription_data)
            await self.ws.send_str(json.dumps({"op": 36, "d": subscription_data.data}))
        else:
            _log.warning("Attempted to unsubscribe from non-existent subscription.")
