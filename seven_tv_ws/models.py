from __future__ import annotations

from typing import Any, Self, override


class DotDict(dict):
    __getattr__ = dict.get


class WebsocketMessageType(DotDict):
    DISPATCH = 0
    HELLO = 1
    HEARTBEAT = 2
    RECONNECT = 4
    ACK = 5
    ERROR = 6
    END_OF_STREAM = 7
    IDENTIFY = 33
    RESUME = 34
    SUBSCRIBE = 35
    UNSUBSCRIBE = 36
    SIGNAL = 37


class ServerCloseCodes(DotDict):
    SERVER_ERROR = 4000
    UNKNOWN_OPERATION = 4001
    INVALID_PAYLOAD = 4002
    AUTH_FAILURE = 4003
    ALREADY_IDENTIFIED = 4004
    RATE_LIMITED = 4005
    RESTART = 4006
    MAINTENANCE = 4007
    TIMEOUT = 4008
    ALREADY_SUBSCRIBED = 4009
    NOT_SUBSCRIBED = 4010
    INSUFFICIENT_PRIVILEGE = 4011

    RECONNECT_CODES = [4000, 4006, 4007, 4008]


class EventType(DotDict):
    SYSTEM_ANNOUNCEMENT = "system.announcement"
    SYSTEM_ALL = "system.*"
    EMOTE_CREATE = "emote.create"
    EMOTE_UPDATE = "emote.update"
    EMOTE_DELETE = "emote.delete"
    EMOTE_ALL = "emote.*"
    EMOTE_SET_CREATE = "emote_set.create"
    EMOTE_SET_UPDATE = "emote_set.update"
    EMOTE_SET_DELETE = "emote_set.delete"
    EMOTE_SET_ALL = "emote_set.*"
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"
    USER_ADD_CONNECTION = "user.add_connection"
    USER_UPDATE_CONNECTION = "user.update_connection"
    USER_DELETE_CONNECTION = "user.delete_connection"
    USER_ALL = "user.*"
    COSMETIC_CREATE = "cosmetic.create"
    COSMETIC_UPDATE = "cosmetic.update"
    COSMETIC_DELETE = "cosmetic.delete"
    COSMETIC_ALL = "cosmetic.*"
    ENTITLEMENT_CREATE = "entitlement.create"
    ENTITLEMENT_UPDATE = "entitlement.update"
    ENTITLEMENT_DELETE = "entitlement.delete"
    ENTITLEMENT_ALL = "entitlement.*"


class UserConnection:
    """UserConnection."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.id: str = data.get("id")
        self.username: str = data.get("username")
        self.display_name: str = data.get("display_name")
        self.platform: str = data.get("platform")
        self.linked_at: int = data.get("linked_at")
        self.emote_capacity: int = data.get("emote_capacity")
        self.emote_set_id: str = data.get("emote_set_id")

    @override
    def __str__(self) -> str:
        return f"<UserConnection id={self.id} username={self.username} display_name={self.display_name} platform={self.platform} linked_at={self.linked_at} emote_capacity={self.emote_capacity} emote_set_id={self.emote_set_id}>"


class User:
    """User."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.id: str = data.get("id")
        self.username: str = data.get("username")
        self.display_name: str = data.get("display_name")
        self.avatar_url: str = data.get("avatar_url")
        self.style: dict[str, Any] | None = data.get("style")
        self.roles: list[str] | None = data.get("roles")
        self.connections: list[UserConnection] | None = data.get("connections")

    @override
    def __str__(self) -> str:
        return f"<User id={self.id} username={self.username} display_name={self.display_name} avatar_url={self.avatar_url} style={self.style} roles={self.roles} connections={[str(connection) for connection in self.connections] if self.connections else []}>"


class ChangeField:
    """ChangeField."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.key: str = data.get("key")
        self.index: int = data.get("index")
        self.nested: bool = data.get("nested")
        self.old_value: dict[str, Any] | None = data.get("old_value")

        value: list[Self] | dict[str, Any] | None = data.get("value")
        self.value: list[Self] | dict[str, Any] | None = (
            value if not value or isinstance(value, dict) else [ChangeField(c) for c in value]
        )

    @override
    def __str__(self) -> str:
        return f"<ChangeField key={self.key} index={self.index} nested={self.nested} value={self.value} old_value={self.old_value}>"


class ChangeMap:
    """ChangeMap."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.id: str = data.get("id")
        self.kind: int = data.get("kind")
        self.contextual: bool | None = data.get("contextual")
        self.actor: User = User(data.get("actor"))
        self.added: list[ChangeField] | None = [ChangeField(d) for d in data.get("added", [])]
        self.updated: list[ChangeField] | None = [ChangeField(d) for d in data.get("updated", [])]
        self.removed: list[ChangeField] | None = [ChangeField(d) for d in data.get("removed", [])]
        self.pushed: list[ChangeField] | None = [ChangeField(d) for d in data.get("pushed", [])]
        self.pulled: list[ChangeField] | None = [ChangeField(d) for d in data.get("pulled", [])]

    @override
    def __str__(self) -> str:
        return f"<ChangeMap id={self.id} kind={self.kind} contextual={self.contextual} actor={self.actor} added={[str(added) for added in self.added] if self.added else []} updated={[str(updated) for updated in self.updated] if self.updated else []} removed={[str(removed) for removed in self.removed] if self.removed else []} pushed={[str(pushed) for pushed in self.pushed] if self.pushed else []} pulled={[str(pulled) for pulled in self.pulled] if self.pulled else []}>"


class SubscriptionCondition:
    """SubscriptionCondition."""

    def __init__(
        self,
        object_id: str | None = None,
        connection_id: str | None = None,
        host_id: str | None = None,
    ) -> None:
        self.data = {}
        if object_id:
            self.data["object_id"] = object_id
        if connection_id:
            self.data["connection_id"] = connection_id
        if host_id:
            self.data["host_id"] = host_id

    @override
    def __str__(self) -> str:
        return f"<SubscriptionCondition data={self.data}>"


class SubscriptionData:
    """SubscriptionData."""

    def __init__(
        self,
        subscription_type: EventType | str,
        condition: SubscriptionCondition | None = None,
    ) -> None:
        self.data = {
            "type": subscription_type,
            "condition": condition.data if condition else None,
        }

    @override
    def __str__(self) -> str:
        return f"<SubscriptionData data={self.data}>"


class WebsocketMessage:
    """WebsocketMessage."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.raw_data = data

    @override
    def __str__(self) -> str:
        return "<WebsocketMessage>"


class Dispatch(WebsocketMessage):
    """Dispatch."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.type: EventType = data.get("type")
        self.body: ChangeMap = ChangeMap(data.get("body"))
        super().__init__(data)

    @override
    def __str__(self) -> str:
        return f"<Dispatch type={self.type} body={self.body}>"


class Hello(WebsocketMessage):
    """Hello."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.session_id: str = data.get("session_id")
        self.heartbeat_interval: int = data.get("heartbeat_interval")
        self.subscription_limit: int = data.get("subscription_limit")
        super().__init__(data)

    @override
    def __str__(self) -> str:
        return f"<Hello session_id={self.session_id} heartbeat_interval={self.heartbeat_interval} subscription_limit={self.subscription_limit}>"


class Heartbeat(WebsocketMessage):
    """Heartbeat."""

    def __init__(self, data: dict[str, int]) -> None:
        self.count: int = data.get("count")
        super().__init__(data)

    @override
    def __str__(self) -> str:
        return f"<Heartbeat count={self.count}>"


class Ack(WebsocketMessage):
    """Ack."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.command: str = data.get("command")
        self.data: Any = data.get("data")
        super().__init__(data)

    @override
    def __str__(self) -> str:
        return f"<Ack command={self.command} data={self.data}>"


class Reconnect(WebsocketMessage):
    """Reconnect."""

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__(data)

    @override
    def __str__(self) -> str:
        return "<Reconnect>"


class Error(WebsocketMessage):
    """Error."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.message: str = data.get("message")
        self.fields: dict[str, str] = data.get("fields")
        super().__init__(data)

    @override
    def __str__(self) -> str:
        return f"<Error message={self.message} fields={self.fields}>"


class EndOfStream(WebsocketMessage):
    """EndOfStream."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.code: ServerCloseCodes = data.get("code")
        self.should_reconnect: bool = self.code in ServerCloseCodes.RECONNECT_CODES
        self.message: str | None = data.get("message")
        super().__init__(data)

    @override
    def __str__(self) -> str:
        return f"<EndOfStream code={self.code} should_reconnect={self.should_reconnect} message={self.message}>"


ResponseTypes = Dispatch | Hello | Heartbeat | Ack | Reconnect | Error | EndOfStream
