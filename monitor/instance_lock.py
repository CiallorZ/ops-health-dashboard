"""Cross-platform single-instance lock for the Sentinel data directory."""

from __future__ import annotations

import os
import sys
from pathlib import Path


class InstanceLockError(RuntimeError):
    """Raised when another Sentinel process already owns the data directory."""


class InstanceLock:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir).resolve()
        self.lock_path = self.data_dir / ".sentinel.lock"
        self._handle = None
        self._mode: str | None = None

    def acquire(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            self._acquire_windows()
        else:
            self._acquire_posix()

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            try:
                handle.close()
            except OSError:
                pass
            self._handle = None
        try:
            if self.lock_path.exists():
                self.lock_path.unlink()
        except OSError:
            pass

    def _acquire_posix(self) -> None:
        import fcntl

        handle = self.lock_path.open("a+b")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise InstanceLockError(_owner_message(self.lock_path)) from exc
        handle.seek(0)
        handle.truncate()
        try:
            handle.write(f"{os.getpid()}\n".encode("ascii"))
            handle.flush()
        except OSError:
            pass
        self._handle = handle
        self._mode = "flock"

    def _acquire_windows(self) -> None:
        import msvcrt

        handle = self.lock_path.open("a+b")
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            handle.close()
            self._acquire_windows_fallback()
            return
        handle.seek(0)
        handle.truncate()
        try:
            handle.write(f"{os.getpid()}\n".encode("ascii"))
            handle.flush()
        except OSError:
            pass
        self._handle = handle
        self._mode = "msvcrt"

    def _acquire_windows_fallback(self) -> None:
        try:
            fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError as exc:
            raise InstanceLockError(_owner_message(self.lock_path)) from exc
        handle = os.fdopen(fd, "r+b")
        try:
            handle.seek(0)
            handle.truncate()
            handle.write(f"{os.getpid()}\n".encode("ascii"))
            handle.flush()
        except OSError:
            pass
        self._handle = handle
        self._mode = "o_excl"


def _owner_message(lock_path: Path) -> str:
    pid = None
    try:
        text = lock_path.read_text(encoding="ascii", errors="replace").strip()
        if text:
            pid = text
    except OSError:
        pass
    if pid:
        return (
            f"another Sentinel process already holds the lock on {lock_path} "
            f"(pid {pid}); start only one instance per data directory"
        )
    return (
        f"another Sentinel process already holds the lock on {lock_path}; "
        "start only one instance per data directory"
    )
