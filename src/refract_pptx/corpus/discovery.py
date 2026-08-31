from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DiscoveredPresentation:
    path: str
    sha256: str
    bytes: int
    modified_at: str
    source_uri: str
    license: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_local(
    root: str | Path,
    *,
    recursive: bool = True,
    source_prefix: str = "file://",
    license_name: str = "unknown",
) -> Iterable[DiscoveredPresentation]:
    source = Path(root).resolve()
    if source.is_file():
        candidates = [source]
    elif source.is_dir():
        candidates = source.rglob("*.pptx") if recursive else source.glob("*.pptx")
    else:
        raise FileNotFoundError(source)

    for path in sorted(candidates):
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
        yield DiscoveredPresentation(
            path=str(path),
            sha256=hash_file(path),
            bytes=stat.st_size,
            modified_at=modified,
            source_uri=f"{source_prefix}{path.as_posix()}",
            license=license_name,
        )
