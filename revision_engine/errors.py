"""Error and warning types shared by every build stage."""


class BuildError(Exception):
    """A content or configuration problem that must stop the build.

    The message always names the file and, where possible, the key path or line.
    """


class Report:
    """Collects non-fatal warnings during a build for a summary at the end."""

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warn(self, message: str) -> None:
        self.warnings.append(message)
