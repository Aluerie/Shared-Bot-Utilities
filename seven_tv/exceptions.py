from .. import errors

__all__ = (
    "ConflictingEmoteNameError",
    "EmoteNotFoundInSetError",
)


class SevenTVError(errors.CustomError):
    """Error Class for Seven TV Errors.

    I mean this class to be used for those errors that comes from 7TV API directly, i.e. in `message` field.
    """


class EmoteNotFoundInSetError(SevenTVError):
    """Emote Not Found In Set Error."""


class ConflictingEmoteNameError(SevenTVError):
    """Conflicting Emote Name Error."""
