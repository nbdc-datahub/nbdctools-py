class NBDCtoolsRError(RuntimeError):
    """Raised when the underlying R call to NBDCtools fails."""

    def __init__(self, message: str, *, r_message: str | None = None) -> None:
        self.r_message = r_message or message
        super().__init__(message)
