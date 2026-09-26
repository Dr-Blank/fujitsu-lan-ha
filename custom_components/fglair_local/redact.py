"""Keeps LAN keys out of the log, whatever a log line or exception carries."""

import logging

REDACTED = "**REDACTED**"
LOGGERS = ("aioayla_lan", __package__)


class KeyFilter(logging.Filter):
    """Replaces every known LAN key in a record's message and traceback."""

    def __init__(self) -> None:
        """Initialise with no keys."""
        super().__init__()
        self.keys: set[str] = set()

    def _redact(self, text: str) -> str:
        for key in self.keys:
            text = text.replace(key, REDACTED)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact the record in place; never drops it."""
        record.msg = self._redact(record.getMessage())
        record.args = None
        if record.exc_info:
            # Handlers reuse exc_text rather than format the exception again.
            record.exc_text = self._redact(
                record.exc_text or logging.Formatter().formatException(record.exc_info)
            )
        return True


KEY_FILTER = KeyFilter()


def redact_key_in_logs(key: str) -> None:
    """Hide `key` in everything the integration and the library log."""
    if key:
        KEY_FILTER.keys.add(key)
    # A logger's filters do not apply to its children, so each gets one.
    for name in list(logging.root.manager.loggerDict):
        if any(name == root or name.startswith(f"{root}.") for root in LOGGERS):
            logging.getLogger(name).addFilter(KEY_FILTER)
