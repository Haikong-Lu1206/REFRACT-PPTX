from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RemotePresentation:
    record_id: str
    title: str
    doi: str
    license: str
    filename: str
    bytes: int
    checksum: str
    download_url: str
    source_url: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _license_name(metadata: dict[str, Any]) -> str:
    value = metadata.get("license", "")
    if isinstance(value, dict):
        return str(value.get("id") or value.get("title") or "unknown")
    return str(value or "unknown")


def search_zenodo(
    query: str,
    *,
    pages: int = 1,
    page_size: int = 100,
    api_base: str = "https://zenodo.org/api/records",
    timeout: int = 30,
) -> Iterable[RemotePresentation]:
    """Discover PPTX files through the public Zenodo records API without downloading them."""
    if pages < 1 or page_size < 1 or page_size > 200:
        raise ValueError("pages must be positive and page_size must be between 1 and 200")
    for page in range(1, pages + 1):
        parameters = urllib.parse.urlencode(
            {"q": query, "page": page, "size": page_size, "sort": "bestmatch"}
        )
        request = urllib.request.Request(
            f"{api_base}?{parameters}",
            headers={"Accept": "application/json", "User-Agent": "REFRACT-PPTX/0.1"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = json.load(response)
        for record in payload.get("hits", {}).get("hits", []):
            metadata = dict(record.get("metadata", {}))
            source_url = str(record.get("links", {}).get("html", ""))
            for item in record.get("files", []):
                filename = str(item.get("key", ""))
                if not filename.lower().endswith(".pptx"):
                    continue
                links = item.get("links", {})
                yield RemotePresentation(
                    record_id=str(record.get("id", "")),
                    title=str(metadata.get("title", "")),
                    doi=str(metadata.get("doi", "")),
                    license=_license_name(metadata),
                    filename=filename,
                    bytes=int(item.get("size", 0) or 0),
                    checksum=str(item.get("checksum", "")),
                    download_url=str(links.get("content") or links.get("self") or ""),
                    source_url=source_url,
                )
