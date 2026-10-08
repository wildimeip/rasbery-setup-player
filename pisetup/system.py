"""Thin layer over the machine: files under a root directory and commands.

Everything that touches the Pi goes through System, so tests can run the whole setup into a
scratch directory with a fake command runner.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Result:
    returncode: int
    stdout: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


Runner = Callable[[Sequence[str], dict], Result]


def run_for_real(cmd: Sequence[str], opts: dict) -> Result:
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    try:
        proc = subprocess.run(
            list(cmd),
            cwd=opts.get("cwd"),
            env=env,
            text=True,
            stdout=subprocess.PIPE if opts.get("capture") else None,
            input=opts.get("input"),
        )
    except FileNotFoundError:
        return Result(127)  # like the shell: command not found
    return Result(proc.returncode, proc.stdout or "")


class CommandFailed(Exception):
    pass


class System:
    def __init__(self, root: Path | str = "/", runner: Runner = run_for_real):
        self.root = Path(root)
        self.runner = runner

    def path(self, p: str | Path) -> Path:
        """A path on the Pi (like /etc/x), inside the root directory."""
        return self.root / str(p).lstrip("/")

    def run(
        self,
        *cmd: str,
        check: bool = True,
        capture: bool = False,
        cwd: str | None = None,
        input: str | None = None,
    ) -> Result:
        opts = {"capture": capture, "cwd": str(self.path(cwd)) if cwd else None, "input": input}
        result = self.runner(cmd, opts)
        if check and not result.ok:
            raise CommandFailed(f"Command failed ({result.returncode}): {' '.join(cmd)}")
        return result

    def has_command(self, name: str) -> bool:
        return self.run("sh", "-c", f"command -v {name}", check=False, capture=True).ok

    def read(self, p: str | Path, default: str = "") -> str:
        f = self.path(p)
        return f.read_text() if f.is_file() else default

    def write(self, p: str | Path, text: str, mode: int | None = None) -> bool:
        """Writes a file; returns True when its content changed."""
        f = self.path(p)
        f.parent.mkdir(parents=True, exist_ok=True)
        if f.is_file() and f.read_text() == text:
            changed = False
        else:
            f.write_text(text)
            changed = True
        if mode is not None:
            f.chmod(mode)
        return changed

    def exists(self, p: str | Path) -> bool:
        return self.path(p).exists()

    def mkdir(self, p: str | Path, mode: int | None = None) -> None:
        d = self.path(p)
        d.mkdir(parents=True, exist_ok=True)
        if mode is not None:
            d.chmod(mode)

    def copy(self, src: Path, dest: str | Path) -> None:
        d = self.path(dest)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, d)

    def chown(self, owner: str, *paths: str | Path, recursive: bool = False) -> None:
        args = ["chown", "-R"] if recursive else ["chown"]
        self.run(*args, owner, *(str(self.path(p)) for p in paths))
