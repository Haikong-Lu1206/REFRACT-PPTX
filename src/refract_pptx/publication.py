from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

from refract_pptx.adapters import AdapterError, validate_emitted_package


def load_deployment(path: str | Path) -> tuple[Path, dict[str, Any]]:
    root = Path(path).resolve()
    issues = validate_emitted_package(root)
    if issues:
        raise AdapterError("invalid deployment package: " + "; ".join(issues))
    return root, json.loads((root / "deployment.json").read_text(encoding="utf-8"))


def _sha256_stream(stream: Any) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _sha256_path(path: Path) -> str:
    with path.open("rb") as stream:
        return _sha256_stream(stream)


def _asset_url(base: str, remote_path: str) -> str:
    base = base.rstrip("/")
    if "://" not in base:
        return str(Path(base).joinpath(*remote_path.split("/")))
    quoted = "/".join(urllib.parse.quote(item, safe="") for item in remote_path.split("/"))
    return f"{base}/{quoted}"


def verify_public_assets(
    deployment: str | Path,
    *,
    asset_base_url: str | None = None,
    timeout: int = 60,
) -> list[dict[str, Any]]:
    """Download every public asset and verify the exact published bytes."""
    _, manifest = load_deployment(deployment)
    profile = dict(manifest.get("profile", {}))
    base = (asset_base_url or profile.get("asset_base_url") or "").strip()
    if not base:
        raise AdapterError("asset base URL is required for remote verification")
    results: list[dict[str, Any]] = []
    for record in manifest["files"]:
        if record.get("visibility") != "public":
            continue
        url = _asset_url(base, record["remote_path"])
        try:
            if "://" not in url:
                with open(url, "rb") as stream:
                    observed = _sha256_stream(stream)
            else:
                request = urllib.request.Request(url, headers={"User-Agent": "REFRACT/0.3"})
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    observed = _sha256_stream(response)
        except (OSError, urllib.error.URLError) as exc:
            raise AdapterError(f"cannot fetch published asset {url}: {exc}") from exc
        expected = record["sha256"]
        if observed != expected:
            raise AdapterError(
                f"published asset hash mismatch for {url}: {observed}, expected {expected}"
            )
        results.append({"url": url, "sha256": observed, "status": "verified"})
    return results


def copy_public_assets(deployment: str | Path, destination: str | Path) -> list[str]:
    """Populate a local dataset/mirror using the manifest's remote paths."""
    root, manifest = load_deployment(deployment)
    target_root = Path(destination).resolve()
    written: list[str] = []
    for record in manifest["files"]:
        if record.get("visibility") != "public":
            continue
        source = root / record["relative_path"]
        target = target_root.joinpath(*record["remote_path"].split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and _sha256_path(target) != record["sha256"]:
            raise AdapterError(
                f"public asset destination already contains different bytes: {target}"
            )
        if not target.exists():
            shutil.copy2(source, target)
        written.append(str(target))
    return written


def stage_runner_files(
    deployment: str | Path,
    runner_root: str | Path,
    *,
    verify_assets: bool = True,
    asset_base_url: str | None = None,
) -> list[str]:
    """Install runner and hidden files only after public assets are reachable."""
    root, manifest = load_deployment(deployment)
    if verify_assets:
        verify_public_assets(root, asset_base_url=asset_base_url)
    destination = Path(runner_root).resolve()
    selected = [
        record for record in manifest["files"] if record.get("visibility") in {"runner", "hidden"}
    ]
    conflicts = []
    for record in selected:
        target = destination / record["relative_path"]
        if target.exists() and _sha256_path(target) != record["sha256"]:
            conflicts.append(str(target))
    if conflicts:
        raise AdapterError("runner destination contains conflicting files: " + ", ".join(conflicts))

    destination.mkdir(parents=True, exist_ok=True)
    staging = destination / f".refract-stage-{uuid4().hex}"
    staging.mkdir()
    try:
        for record in selected:
            source = root / record["relative_path"]
            staged = staging / record["relative_path"]
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, staged)
        written: list[str] = []
        for record in selected:
            staged = staging / record["relative_path"]
            target = destination / record["relative_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                os.replace(staged, target)
            written.append(str(target))
        return written
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


__all__ = [
    "copy_public_assets",
    "load_deployment",
    "stage_runner_files",
    "verify_public_assets",
]
