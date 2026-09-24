class EventApiError(Exception):
    """Base class for all exceptions defined by EventApi."""


class SubscriptionError(EventApiError):
    """
    Thrown when a subscription limit is exceeded.

    Attributes
    ----------
        limit (int): The maximum number of subscriptions.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit


class NoActiveSubscriptionsError(EventApiError):
    """Thrown when there are no active subscriptions."""


class WSConnectionError(EventApiError):
    """Thrown when a websocket connection fails."""


class NoActiveWSConnectionError(EventApiError):
    """Thrown when a trying to send a data when there is no active WebSocket connection."""
