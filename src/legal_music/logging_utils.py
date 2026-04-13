"""Terminal color output utilities."""
from __future__ import annotations

import sys


class T:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"


def supports_color() -> bool:
    return sys.stdout.isatty()


class Printer:
    """Colored terminal printer."""

    def __init__(self, color: bool | None = None, verbose: bool = False) -> None:
        self.color = supports_color() if color is None else color
        self.verbose = verbose

    def _c(self, text: str, code: str) -> str:
        return f"{code}{text}{T.RESET}" if self.color else text

    def ok(self, msg: str) -> None:
        print(self._c(msg, T.GREEN))

    def warn(self, msg: str) -> None:
        print(self._c(msg, T.YELLOW))

    def err(self, msg: str) -> None:
        print(self._c(msg, T.RED))

    def info(self, msg: str) -> None:
        print(msg)

    def bold(self, msg: str) -> None:
        print(self._c(msg, T.BOLD))

    def dim(self, msg: str) -> None:
        print(self._c(msg, T.DIM))

    def blue(self, msg: str) -> None:
        print(self._c(msg, T.BLUE))

    def cyan(self, msg: str) -> None:
        print(self._c(msg, T.CYAN))

    def vlog(self, msg: str) -> None:
        if self.verbose:
            print(self._c(f"   > {msg}", T.DIM))

    def progress(self, index: int, total: int, label: str) -> None:
        width = 24
        done = int((index / max(total, 1)) * width)
        bar = f"[{index}/{total}] [{'#' * done}{'-' * (width - done)}]"
        self.blue(f"{bar} {label}")

    def separator(self) -> None:
        print("-" * 72)
