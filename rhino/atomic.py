"""Writing a file so that a power cut leaves the old one or the new one, never half of one.

write_text() makes a temp file of its own beside the target (two writers never share one), writes it, flushes it to the
disk (fsync), renames it over the target, then flushes the folder so the rename itself is on the disk. A Raspberry Pi or a
mini PC on a power strip is switched off without warning; without the fsync an ext4 rename can reach the disk before the
data does, and the target is left empty. The target's permissions are kept; a new file gets 0644. Nothing is left behind
when the write fails.
"""
import os
import tempfile


def write_text(path, text, mode=None):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    if mode is None:
        try:
            mode = os.stat(path).st_mode & 0o7777
        except OSError:
            mode = 0o644
    fd, tmp = tempfile.mkstemp(dir=d, prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)    # mkstemp makes 0600
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _sync_folder(d)


def _sync_folder(d):
    """Best effort: not every filesystem lets a folder be opened and flushed, and the data is safe already."""
    try:
        fd = os.open(d, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
