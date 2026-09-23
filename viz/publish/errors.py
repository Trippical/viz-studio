"""The one exception the CLI turns into exit codes and stderr lines."""


class CliError(Exception):
    """messages: one line each, printed as 'error: <line>'. code: process exit code.
    1 = validation failure or refusal, 2 = usage, missing input or deny-list."""

    def __init__(self, messages: list[str] | str, code: int = 1):
        self.messages = [messages] if isinstance(messages, str) else list(messages)
        self.code = code
        super().__init__("; ".join(self.messages))
