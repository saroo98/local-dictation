"""Small durable JSON writes. Callers own their read/modify/write locks."""
import json
import os
import tempfile
from pathlib import Path


read_errors: dict[Path, str] = {}


def read_json(path: Path, expected_type: type):
    path = Path(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, expected_type):
            raise ValueError(f"Expected a JSON {expected_type.__name__}.")
    except FileNotFoundError:
        read_errors.pop(path, None)
        return None
    except (OSError, UnicodeError, ValueError) as exc:
        read_errors[path] = f"Cannot read {path.name}: {exc}. Original file preserved."
        raise ValueError(read_errors[path]) from exc
    read_errors.pop(path, None)
    return value


def atomic_write_json(path: Path, value, *, recover: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        read_json(path, type(value))
    except ValueError:
        if not recover:
            raise
        # Preserve corrupt bytes before an explicit settings save/history clear.
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.corrupt-', delete=False) as backup:
            backup.write(path.read_bytes())
            backup.flush()
            os.fsync(backup.fileno())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.' + path.name + '-', suffix='.tmp', delete=False) as file:
            temporary = Path(file.name)
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        read_errors.pop(path, None)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
