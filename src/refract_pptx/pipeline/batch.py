from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from refract_pptx import __version__
from refract_pptx.adapters import RunnerProfile, adapter_for, validate_emitted_package
from refract_pptx.build import build_task
from refract_pptx.design import load_proposal
from refract_pptx.validation import validate_bundle
from refract_pptx.validation.production import bundle_identity

from .locking import task_lock
from .registry import TaskRegistry
from .state import RunState, StageStatus


class BatchError(ValueError):
    """Raised when a batch manifest is invalid."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class BatchItem:
    key: str
    presentation: str
    reference: str
    proposal: str
    source_uri: str
    license: str
    materials: str = ""
    task_id: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any], *, base: Path) -> BatchItem:
        def local(name: str, required: bool = True) -> str:
            token = str(value.get(name, "")).strip()
            if not token:
                if required:
                    raise BatchError(f"batch item is missing {name}")
                return ""
            path = Path(token)
            return str((base / path).resolve() if not path.is_absolute() else path.resolve())

        item = cls(
            key=str(value.get("key", "")).strip(),
            presentation=local("presentation"),
            reference=local("reference"),
            proposal=local("proposal"),
            source_uri=str(value.get("source_uri", "")).strip(),
            license=str(value.get("license", "")).strip(),
            materials=local("materials", required=False),
            task_id=str(value.get("task_id", "")).strip(),
        )
        if not item.key:
            raise BatchError("batch item key is required")
        if not item.source_uri or not item.license:
            raise BatchError(f"batch item {item.key}: source_uri and license are required")
        for label in ("presentation", "reference", "proposal"):
            if not Path(getattr(item, label)).is_file():
                raise BatchError(f"batch item {item.key}: {label} does not exist")
        if item.materials and not Path(item.materials).is_dir():
            raise BatchError(f"batch item {item.key}: materials is not a directory")
        return item


@dataclass(frozen=True)
class BatchItemResult:
    key: str
    task_id: str
    status: str
    bundle: str = ""
    deployment: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BatchResult:
    items: tuple[BatchItemResult, ...]
    state: dict[str, int]

    @property
    def successful(self) -> int:
        return sum(item.status == StageStatus.COMPLETE.value for item in self.items)

    @property
    def failed(self) -> int:
        return sum(item.status == StageStatus.FAILED.value for item in self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "successful": self.successful,
            "failed": self.failed,
            "items": [item.to_dict() for item in self.items],
            "state": self.state,
        }


def load_batch_manifest(path: str | Path) -> tuple[BatchItem, ...]:
    source = Path(path).resolve()
    items: list[BatchItem] = []
    keys: set[str] = set()
    task_ids: set[str] = set()
    with source.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise BatchError("record must be a JSON object")
                item = BatchItem.from_dict(value, base=source.parent)
            except (json.JSONDecodeError, BatchError) as exc:
                raise BatchError(f"{source}:{line_number}: {exc}") from exc
            if item.key in keys:
                raise BatchError(f"duplicate batch key: {item.key}")
            if item.task_id and item.task_id in task_ids:
                raise BatchError(f"duplicate requested task_id: {item.task_id}")
            keys.add(item.key)
            if item.task_id:
                task_ids.add(item.task_id)
            items.append(item)
    if not items:
        raise BatchError("batch manifest contains no items")
    return tuple(items)


class BatchRunner:
    def __init__(
        self,
        output: str | Path,
        *,
        state_path: str | Path,
        registry_path: str | Path,
        workers: int = 4,
        task_prefix: str = "refract",
        runner_profile: RunnerProfile | None = None,
    ):
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.state = RunState(state_path, default_lease_seconds=4 * 60 * 60)
        self.registry = TaskRegistry(registry_path)
        self.workers = max(1, min(int(workers), 32))
        self.task_prefix = task_prefix
        self.runner_profile = runner_profile

    def _input_hash(self, item: BatchItem) -> str:
        material_hashes: list[tuple[str, str]] = []
        if item.materials:
            material_root = Path(item.materials)
            material_hashes = sorted(
                (str(path.relative_to(material_root)).replace("\\", "/"), _sha256(path))
                for path in material_root.rglob("*")
                if path.is_file()
            )
        payload = {
            "framework_version": __version__,
            "presentation": _sha256(Path(item.presentation)),
            "reference": _sha256(Path(item.reference)),
            "proposal": _sha256(Path(item.proposal)),
            "materials": material_hashes,
            "source_uri": item.source_uri,
            "license": item.license,
            "runner_profile": (
                self.runner_profile.to_dict() if self.runner_profile is not None else None
            ),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _task_id(self, item: BatchItem) -> str:
        source_digest = _sha256(Path(item.presentation))
        design_key = self._input_hash(item)
        return self.registry.allocate(
            source_digest,
            design_key,
            prefix=self.task_prefix,
            requested_id=item.task_id or None,
        )

    def _run_item(self, item: BatchItem) -> BatchItemResult:
        task_id = self._task_id(item)
        with task_lock(self.output / ".locks" / f"{task_id}.lock") as acquired:
            if not acquired:
                return BatchItemResult(item.key, task_id, StageStatus.RUNNING.value)
            return self._run_locked(item, task_id)

    def _run_locked(self, item: BatchItem, task_id: str) -> BatchItemResult:
        digest = self._input_hash(item)
        bundle = self.output / "bundles" / task_id
        deployment = self.output / "deployments" / task_id
        if not self.state.start(item.key, "build", digest):
            receipt = self.state.receipt(item.key, "build")
            if receipt and receipt.status is StageStatus.COMPLETE:
                bundle_ok = bundle.is_dir() and validate_bundle(bundle).valid
                deployment_ok = self.runner_profile is None or (
                    deployment.is_dir() and not validate_emitted_package(deployment)
                )
                identity_ok = bundle_ok and receipt.output.get(
                    "bundle_identity"
                ) == bundle_identity(bundle)
                if bundle_ok and not identity_ok:
                    return BatchItemResult(
                        item.key,
                        task_id,
                        StageStatus.FAILED.value,
                        error="completed bundle changed; refusing stale reuse",
                    )
                if identity_ok and deployment_ok:
                    return BatchItemResult(
                        item.key,
                        task_id,
                        StageStatus.COMPLETE.value,
                        str(bundle),
                        str(deployment) if deployment.exists() else "",
                    )
                self.state.reset(item.key, "build")
                if not self.state.start(item.key, "build", digest):
                    return BatchItemResult(item.key, task_id, StageStatus.RUNNING.value)
            else:
                return BatchItemResult(item.key, task_id, StageStatus.RUNNING.value)
        try:
            if bundle.exists():
                validation = validate_bundle(bundle)
                if not validation.valid:
                    raise BatchError(
                        "existing bundle is invalid and was not overwritten: "
                        + "; ".join(validation.issues)
                    )
            else:
                build_task(
                    item.presentation,
                    item.reference,
                    load_proposal(item.proposal),
                    bundle,
                    task_id=task_id,
                    source_uri=item.source_uri,
                    license_name=item.license,
                    materials=item.materials or None,
                )
            deployment_path = ""
            if self.runner_profile is not None:
                if deployment.exists():
                    issues = validate_emitted_package(deployment)
                    if issues:
                        raise BatchError(
                            "existing deployment is invalid and was not overwritten: "
                            + "; ".join(issues)
                        )
                else:
                    adapter_for(self.runner_profile).emit(
                        bundle, deployment, self.runner_profile, runner_task_id=task_id
                    )
                deployment_path = str(deployment)
            output = {
                "task_id": task_id,
                "bundle": str(bundle),
                "deployment": deployment_path,
                "bundle_identity": bundle_identity(bundle),
            }
            self.state.complete(item.key, "build", output)
            return BatchItemResult(
                item.key,
                task_id,
                StageStatus.COMPLETE.value,
                str(bundle),
                deployment_path,
            )
        except Exception as exc:
            try:
                self.state.fail(item.key, "build", f"{type(exc).__name__}: {exc}")
            except RuntimeError:
                pass  # A reclaimed worker must not overwrite the current owner's state.
            return BatchItemResult(
                item.key,
                task_id,
                StageStatus.FAILED.value,
                str(bundle) if bundle.exists() else "",
                str(deployment) if deployment.exists() else "",
                f"{type(exc).__name__}: {exc}",
            )

    def run(self, items: tuple[BatchItem, ...]) -> BatchResult:
        logical_keys: set[tuple[str, str]] = set()
        for item in items:
            logical_key = (_sha256(Path(item.presentation)), self._input_hash(item))
            if logical_key in logical_keys:
                raise BatchError(
                    f"duplicate logical task in batch manifest (source + design): {item.key}"
                )
            logical_keys.add(logical_key)
        results: list[BatchItemResult] = []
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(self._run_item, item): item.key for item in items}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    results.append(
                        BatchItemResult(
                            futures[future],
                            "",
                            StageStatus.FAILED.value,
                            error=f"{type(exc).__name__}: {exc}",
                        )
                    )
        results.sort(key=lambda item: item.key)
        return BatchResult(tuple(results), self.state.summary())


__all__ = [
    "BatchError",
    "BatchItem",
    "BatchItemResult",
    "BatchResult",
    "BatchRunner",
    "load_batch_manifest",
]
