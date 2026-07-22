class AIAdapterError(Exception):
    """Base error safe to translate at the gateway boundary."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class ProviderUnavailableError(AIAdapterError):
    def __init__(self, message: str = "AI provider is unavailable") -> None:
        super().__init__(message, retryable=True)


class ProviderAuthenticationError(AIAdapterError):
    pass


class ProviderProtocolError(AIAdapterError):
    pass


class ProviderTimeoutError(AIAdapterError):
    def __init__(self, message: str = "AI provider request timed out") -> None:
        super().__init__(message, retryable=True)


class RequestCancelledError(AIAdapterError):
    pass
