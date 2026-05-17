class SahiyAgentError(Exception):
    """Base exception for the application."""


class DatabaseError(SahiyAgentError):
    """Raised when a database operation fails."""


class ConfigurationError(SahiyAgentError):
    """Raised when required configuration is missing or invalid."""


class SessionNotFoundError(SahiyAgentError):
    """Raised when session_id does not exist."""


class SessionAccessDeniedError(SahiyAgentError):
    """Raised when user_id does not match the session owner."""


class SessionClosedError(SahiyAgentError):
    """Raised when the session is not active."""


class LLMError(SahiyAgentError):
    """Raised when the LLM provider fails."""


class LLMTimeoutError(LLMError):
    """Raised when the LLM does not respond within the configured timeout."""
