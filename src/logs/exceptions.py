class LoggingError(Exception):
    """Base logging domain error."""


class LoggingPolicyError(LoggingError):
    pass


class LoggingIngestError(LoggingError):
    pass


class LoggingQueryError(LoggingError):
    pass


class ExpiredCursorError(LoggingQueryError):
    """Client cursor points at deleted/expired history."""


class ExportLimitExceeded(LoggingQueryError):
    pass
