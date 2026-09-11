from .base import AdapterError, EmittedPackage, PackageFile, RunnerAdapter, RunnerProfile
from .desktop import DesktopBaseTaskAdapter, validate_emitted_package


def adapter_for(profile: RunnerProfile) -> RunnerAdapter:
    if profile.adapter == "desktop_base_task":
        return DesktopBaseTaskAdapter()
    raise AdapterError(f"no runner adapter is registered for {profile.adapter!r}")

__all__ = [
    "AdapterError",
    "DesktopBaseTaskAdapter",
    "EmittedPackage",
    "PackageFile",
    "RunnerAdapter",
    "RunnerProfile",
    "adapter_for",
    "validate_emitted_package",
]
