from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Protocol


class AdapterError(RuntimeError):
    """Raised when a neutral task bundle cannot be adapted honestly."""


@dataclass(frozen=True)
class RunnerProfile:
    """Deployment details kept outside task design and evaluation logic."""

    profile_version: str = "1.0"
    adapter: str = "desktop_base_task"
    asset_base_url: str = ""
    asset_base_env: str = "REFRACT_ASSET_BASE"
    public_namespace: str = "{task_id}"
    task_class_dir: str = "task_class"
    task_assets_dir: str = "task_assets"
    public_assets_dir: str = "public_assets"
    desktop_dir: str = "/home/user/Desktop"
    application_command: tuple[str, ...] = ("wpp", "{deck_path}")
    snapshot: str = "wps"
    platform: str = "linux"
    related_apps: tuple[str, ...] = ("wps",)
    volume_size: int = 60
    proxy: bool = False
    disable_vnc: bool = False
    disable_recording: bool = False
    intermediate_eval_safe: bool = False
    source_label: str = "refract"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RunnerProfile:
        unknown = sorted(set(value) - {item.name for item in fields(cls)})
        if unknown:
            raise AdapterError("unknown runner profile fields: " + ", ".join(unknown))
        defaults = cls()
        for name in (
            "proxy",
            "disable_vnc",
            "disable_recording",
            "intermediate_eval_safe",
        ):
            if name in value and not isinstance(value[name], bool):
                raise AdapterError(f"runner profile field {name} must be a JSON boolean")
        for name in ("application_command", "related_apps"):
            if name in value and not isinstance(value[name], (list, tuple)):
                raise AdapterError(f"runner profile field {name} must be a JSON array")
        return cls(
            profile_version=str(value.get("profile_version", defaults.profile_version)),
            adapter=str(value.get("adapter", defaults.adapter)),
            asset_base_url=str(value.get("asset_base_url", "")).rstrip("/"),
            asset_base_env=str(value.get("asset_base_env", defaults.asset_base_env)),
            public_namespace=str(value.get("public_namespace", defaults.public_namespace)),
            task_class_dir=str(value.get("task_class_dir", defaults.task_class_dir)),
            task_assets_dir=str(value.get("task_assets_dir", defaults.task_assets_dir)),
            public_assets_dir=str(value.get("public_assets_dir", defaults.public_assets_dir)),
            desktop_dir=str(value.get("desktop_dir", defaults.desktop_dir)).rstrip("/"),
            application_command=tuple(
                str(item) for item in value.get("application_command", defaults.application_command)
            ),
            snapshot=str(value.get("snapshot", defaults.snapshot)),
            platform=str(value.get("platform", defaults.platform)),
            related_apps=tuple(
                str(item) for item in value.get("related_apps", defaults.related_apps)
            ),
            volume_size=int(value.get("volume_size", defaults.volume_size)),
            proxy=bool(value.get("proxy", defaults.proxy)),
            disable_vnc=bool(value.get("disable_vnc", defaults.disable_vnc)),
            disable_recording=bool(value.get("disable_recording", defaults.disable_recording)),
            intermediate_eval_safe=bool(
                value.get("intermediate_eval_safe", defaults.intermediate_eval_safe)
            ),
            source_label=str(value.get("source_label", defaults.source_label)),
        )

    @classmethod
    def load(cls, path: str | Path) -> RunnerProfile:
        source = Path(path)
        try:
            value = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AdapterError(f"cannot read runner profile {source}: {exc}") from exc
        if not isinstance(value, dict):
            raise AdapterError("runner profile root must be a JSON object")
        return cls.from_dict(value).require_valid()

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.profile_version != "1.0":
            issues.append("profile_version must be 1.0")
        if self.adapter != "desktop_base_task":
            issues.append("adapter must be desktop_base_task")
        if not self.asset_base_url:
            issues.append("asset_base_url is required")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", self.asset_base_env):
            issues.append("asset_base_env must be an uppercase environment variable name")
        try:
            rendered_namespace = self.public_namespace.format(task_id="example")
        except (KeyError, ValueError):
            rendered_namespace = ""
            issues.append("public_namespace may contain only the {task_id} placeholder")
        if "{task_id}" not in self.public_namespace:
            issues.append("public_namespace must contain {task_id}")
        if rendered_namespace.startswith("/") or ".." in Path(rendered_namespace).parts:
            issues.append("public_namespace must remain relative to the asset root")
        for field_name in (
            "task_class_dir",
            "task_assets_dir",
            "public_assets_dir",
        ):
            value = Path(getattr(self, field_name))
            if not str(getattr(self, field_name)).strip():
                issues.append(f"{field_name} cannot be empty")
            elif value.is_absolute() or ".." in value.parts:
                issues.append(f"{field_name} must be a relative path within the output root")
        if not self.desktop_dir.startswith("/"):
            issues.append("desktop_dir must be an absolute POSIX path")
        if not self.application_command or "{deck_path}" not in self.application_command:
            issues.append("application_command must contain {deck_path} as one argument")
        if not self.snapshot:
            issues.append("snapshot is required")
        if not self.related_apps:
            issues.append("related_apps cannot be empty")
        if self.volume_size < 10:
            issues.append("volume_size must be at least 10 GB")
        if self.intermediate_eval_safe:
            issues.append("intermediate_eval_safe must be false because evaluation closes WPS")
        return issues

    def require_valid(self) -> RunnerProfile:
        issues = self.validate()
        if issues:
            raise AdapterError("invalid runner profile:\n- " + "\n- ".join(issues))
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PackageFile:
    role: str
    relative_path: str
    sha256: str
    size: int
    visibility: str
    remote_path: str = ""
    vm_path: str = ""


@dataclass(frozen=True)
class EmittedPackage:
    package_version: str
    adapter: str
    task_id: str
    root: str
    task_module: str
    files: tuple[PackageFile, ...]
    instruction: str
    profile: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RunnerAdapter(Protocol):
    adapter_id: str

    def emit(
        self,
        bundle: str | Path,
        output: str | Path,
        profile: RunnerProfile,
        *,
        runner_task_id: str | None = None,
    ) -> EmittedPackage: ...


__all__ = [
    "AdapterError",
    "EmittedPackage",
    "PackageFile",
    "RunnerAdapter",
    "RunnerProfile",
]
