import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from monitor.instance_lock import InstanceLock, InstanceLockError


def _flock_is_held(lock_path: Path) -> bool:
    import fcntl

    fd = os.open(str(lock_path), os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def _read_lock_content(lock: InstanceLock) -> str:
    if sys.platform == "win32":
        # Windows byte locks block reads of the locked region from other
        # handles, so inspect the file through the owning handle instead.
        lock._handle.seek(0)
        return lock._handle.read().decode("ascii")
    return lock.lock_path.read_text(encoding="ascii")


def _write_lock_content(lock: InstanceLock, data: bytes) -> None:
    if sys.platform == "win32":
        lock._handle.seek(0)
        lock._handle.truncate()
        lock._handle.write(data)
        lock._handle.flush()
    else:
        lock.lock_path.write_bytes(data)


@unittest.skipUnless(
    sys.platform != "win32", "flock-based lock semantics are POSIX-only"
)
class PosixInstanceLockTests(unittest.TestCase):
    def test_second_acquire_fails_with_owner_pid(self):
        with TemporaryDirectory() as directory:
            first = InstanceLock(Path(directory))
            first.acquire()
            second = InstanceLock(Path(directory))
            with self.assertRaises(InstanceLockError) as ctx:
                second.acquire()
            self.assertIn(str(os.getpid()), str(ctx.exception))
            first.release()

    def test_release_keeps_lock_file_and_allows_reacquire(self):
        with TemporaryDirectory() as directory:
            lock = InstanceLock(Path(directory))
            lock.acquire()
            lock_path = lock.lock_path
            self.assertTrue(lock_path.exists())
            lock.release()
            self.assertTrue(lock_path.exists())
            lock.acquire()
            lock.release()

    def test_release_keeps_file_taken_over_by_another_flock_holder(self):
        with TemporaryDirectory() as directory:
            first = InstanceLock(Path(directory))
            first.acquire()
            lock_path = first.lock_path
            lock_path.write_text("999999\n", encoding="ascii")
            first.release()
            self.assertTrue(lock_path.exists())

    def test_held_lock_blocks_flock_from_another_handle(self):
        with TemporaryDirectory() as directory:
            lock = InstanceLock(Path(directory))
            lock.acquire()
            try:
                self.assertTrue(_flock_is_held(lock.lock_path))
            finally:
                lock.release()


class InstanceLockContractTests(unittest.TestCase):
    def test_release_without_acquire_is_a_no_op(self):
        with TemporaryDirectory() as directory:
            lock = InstanceLock(Path(directory))
            lock.release()
            self.assertFalse((Path(directory) / ".sentinel.lock").exists())

    def test_acquire_creates_lock_file_with_owner_pid(self):
        with TemporaryDirectory() as directory:
            lock = InstanceLock(Path(directory))
            lock.acquire()
            try:
                content = _read_lock_content(lock)
                self.assertEqual(content.strip(), str(os.getpid()))
            finally:
                lock.release()

    def test_release_does_not_delete_foreign_lock_file(self):
        with TemporaryDirectory() as directory:
            lock = InstanceLock(Path(directory))
            lock.acquire()
            _write_lock_content(lock, b"not-my-pid\n")
            lock.release()
            self.assertTrue(lock.lock_path.exists())
            self.assertEqual(
                lock.lock_path.read_text(encoding="ascii"), "not-my-pid\n"
            )


if sys.platform == "win32":

    class WindowsInstanceLockTests(unittest.TestCase):
        def test_second_acquire_fails(self):
            with TemporaryDirectory() as directory:
                first = InstanceLock(Path(directory))
                first.acquire()
                second = InstanceLock(Path(directory))
                with self.assertRaises(InstanceLockError):
                    second.acquire()
                first.release()

        def test_release_keeps_lock_file_and_allows_reacquire(self):
            with TemporaryDirectory() as directory:
                lock = InstanceLock(Path(directory))
                lock.acquire()
                lock.release()
                self.assertTrue(lock.lock_path.exists())
                second = InstanceLock(Path(directory))
                second.acquire()
                second.release()

        def test_release_does_not_delete_zero_byte_foreign_file(self):
            # A file we did not create must survive: an empty file could be a
            # fallback-mode lock another process just created via O_EXCL.
            with TemporaryDirectory() as directory:
                lock = InstanceLock(Path(directory))
                lock.acquire()
                mode = lock._mode
                lock._handle.close()
                lock._handle = None
                lock.lock_path.write_bytes(b"")
                lock._mode = mode
                lock.release()
                self.assertTrue(lock.lock_path.exists())

    WindowsInstanceLockTests.__name__ = "WindowsInstanceLockTests"
