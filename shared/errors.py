class CustomError(Exception):
    """The base exception for my projects. All other exceptions should inherit from this."""


class SilentError(CustomError):
    """Errors to be ignored by error handlers."""
