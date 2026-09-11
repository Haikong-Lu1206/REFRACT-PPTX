from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import types
import zipfile
from pathlib import Path

import pytest

from refract_pptx.adapters import (
    AdapterError,
    DesktopBaseTaskAdapter,
    RunnerProfile,
    validate_emitted_package,
)
from refract_pptx.build import build_task
from refract_pptx.design import AgentProposal
from refract_pptx.publication import (
    copy_public_assets,
    stage_runner_files,
    verify_public_assets,
)


def _proposal() -> AgentProposal:
    return AgentProposal.from_dict(
        {
            "proposal_version": "1.0",
            "title": "Restore the title alignment",
            "instruction": (
                "Restore the damaged editable title so the presentation matches the visible "
                "reference while preserving all unrelated content."
            ),
            "deck_summary": "A two-slide project update with editable native content.",
            "mutations": [
                {
                    "mutation_id": "move-title",
                    "family": "spatial_structure_repair",
                    "capability": "object_alignment",
                    "slide": 1,
                    "target": {"shape_id": 2, "kind": "shape"},
                    "operation": {"type": "move_shape", "dx_points": 60, "dy_points": 0},
                    "evidence_tier": "reference_visible",
                    "evidence": [
                        {
                            "source": "reference",
                            "locator": "slide 1 title",
                            "supports": "the target title position",
                        }
                    ],
                    "rationale": "The shifted title visibly breaks the page alignment.",
                    "accepted_solutions": ["Move or recreate an equivalent editable title."],
                    "scoring": {"geometry": 1.0},
                    "weight": 1.0,
                }
            ],
            "preservation_contracts": ["Preserve all unrelated visible content."],
        }
    ).require_valid()


def _build_bundle(synthetic_pptx: Path, root: Path) -> Path:
    reference = root / "reference.pdf"
    reference.write_bytes(b"%PDF-1.4\n% adapter test\n")
    bundle = root / "bundle"
    build_task(
        synthetic_pptx,
        reference,
        _proposal(),
        bundle,
        task_id="adapter-test-task",
        source_uri="synthetic://adapter-test",
        license_name="CC0-1.0",
    )
    return bundle


def _profile(asset_base: str = "https://assets.example.invalid/refract") -> RunnerProfile:
    return RunnerProfile.from_dict(
        {
            "asset_base_url": asset_base,
            "public_namespace": "tasks/{task_id}",
        }
    ).require_valid()


def _install_fake_desktop_env(monkeypatch):
    desktop_env = types.ModuleType("desktop_env")
    task_base = types.ModuleType("desktop_env.task_base")
    evaluators = types.ModuleType("desktop_env.evaluators")
    getters = types.ModuleType("desktop_env.evaluators.getters")

    class BaseTask(dict):
        _names = (
            "id",
            "instruction",
            "config",
            "proxy",
            "disable_vnc",
            "disable_recording",
            "intermediate_eval_safe",
            "snapshot",
            "volume_size",
            "platform",
            "related_apps",
            "source",
            "trajectory",
            "user_simulator",
            "evaluator",
        )

        def __init__(self):
            super().__init__((name, getattr(self, name, None)) for name in self._names)

    task_base.BaseTask = BaseTask
    getters.get_vm_file = lambda *_args, **_kwargs: None
    getters.get_vm_command_line = lambda *_args, **_kwargs: ""
    monkeypatch.setitem(sys.modules, "desktop_env", desktop_env)
    monkeypatch.setitem(sys.modules, "desktop_env.task_base", task_base)
    monkeypatch.setitem(sys.modules, "desktop_env.evaluators", evaluators)
    monkeypatch.setitem(sys.modules, "desktop_env.evaluators.getters", getters)


def test_runner_profile_rejects_unsafe_or_incomplete_values():
    issues = RunnerProfile().validate()
    assert "asset_base_url is required" in issues
    unsafe = RunnerProfile.from_dict(
        {
            "asset_base_url": "https://assets.example.invalid",
            "task_class_dir": "../outside",
            "intermediate_eval_safe": True,
        }
    )
    assert any("task_class_dir" in issue for issue in unsafe.validate())
    assert any("intermediate_eval_safe" in issue for issue in unsafe.validate())
    with pytest.raises(AdapterError, match="unknown runner profile fields"):
        RunnerProfile.from_dict(
            {"asset_base_url": "https://example.invalid", "snapshop": "wps"}
        )


def test_desktop_adapter_emits_separated_self_contained_package(
    synthetic_pptx, workspace_tmp
):
    bundle = _build_bundle(synthetic_pptx, workspace_tmp)
    output = workspace_tmp / "deployment"
    package = DesktopBaseTaskAdapter().emit(bundle, output, _profile())

    assert not validate_emitted_package(output)
    assert package.task_id == "adapter-test-task"
    manifest = json.loads((output / "deployment.json").read_text(encoding="utf-8"))
    public = [item for item in manifest["files"] if item["visibility"] == "public"]
    hidden = [item for item in manifest["files"] if item["visibility"] == "hidden"]
    assert {item["role"] for item in public} == {"initial_presentation", "reference_render"}
    assert {Path(item["relative_path"]).name for item in hidden} >= {
        "plan.json",
        "init_inventory.json",
        "runtime.zip",
    }
    assert all("plan.json" not in item["remote_path"] for item in public)
    runtime = output / next(
        item["relative_path"] for item in hidden if item["relative_path"].endswith("runtime.zip")
    )
    with zipfile.ZipFile(runtime) as archive:
        assert "_refract_runtime/evaluation/progress.py" in archive.namelist()
    sys.path.insert(0, str(runtime))
    try:
        runtime_evaluation = __import__(
            "_refract_runtime.evaluation", fromlist=["evaluate_snapshots"]
        )
        runtime_presentation = __import__(
            "_refract_runtime.presentation", fromlist=["object_inventory"]
        )
        hidden_root = runtime.parent
        plan = json.loads((hidden_root / "plan.json").read_text(encoding="utf-8"))
        initial = runtime_presentation.deck_snapshot_from_dict(
            json.loads((hidden_root / "init_inventory.json").read_text(encoding="utf-8"))
        )
        damaged = runtime_presentation.object_inventory(
            output / "public_assets" / "adapter-test-task" / "init.pptx"
        )
        oracle = runtime_presentation.object_inventory(synthetic_pptx)
        assert runtime_evaluation.evaluate_snapshots(damaged, initial, plan).score == 0.0
        assert runtime_evaluation.evaluate_snapshots(oracle, initial, plan).score == 1.0
    finally:
        sys.path.remove(str(runtime))


def test_generated_task_matches_base_task_contract(
    synthetic_pptx, workspace_tmp, monkeypatch
):
    bundle = _build_bundle(synthetic_pptx, workspace_tmp)
    output = workspace_tmp / "deployment"
    package = DesktopBaseTaskAdapter().emit(
        bundle, output, _profile(), runner_task_id="990-test"
    )
    _install_fake_desktop_env(monkeypatch)
    module_path = output / package.task_module
    spec = importlib.util.spec_from_file_location("generated_refract_task", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    task = module.TASK_CLASS()

    assert task["id"] == "990-test"
    assert task["snapshot"] == "wps"
    assert task["related_apps"] == ["wps"]
    assert task["intermediate_eval_safe"] is False
    assert "reference.pdf" in task["instruction"]
    assert "/home/user/Desktop/task_990-test.pptx" in task["instruction"]

    class Controller:
        def __init__(self):
            self.commands = []
            self.files = []
            self.launched = []

        def execute(self, **kwargs):
            self.commands.append(kwargs)

        def download(self, files):
            self.files.extend(files)

        def launch(self, command):
            self.launched.append(command)

    controller = Controller()
    task.setup(controller)
    assert len(controller.files) == 2
    assert controller.launched == [["wpp", "/home/user/Desktop/task_990-test.pptx"]]
    assert any("sha256sum" in item["command"] for item in controller.commands)

    oracle_sha = hashlib.sha256(synthetic_pptx.read_bytes()).hexdigest()

    def vm_command(_env, config):
        command = " ".join(config["command"])
        return oracle_sha + "\n" if "sha256sum" in command else ""

    module.get_vm_command_line = vm_command
    module.get_vm_file = lambda *_args, **_kwargs: str(synthetic_pptx)
    module.time.sleep = lambda _seconds: None
    result = task.evaluate(object())
    assert result["score"] == 1.0
    assert result["evidence"]["disk_changed"] is True


def test_local_publication_verifies_before_runner_staging(
    synthetic_pptx, workspace_tmp
):
    bundle = _build_bundle(synthetic_pptx, workspace_tmp)
    output = workspace_tmp / "deployment"
    mirror = workspace_tmp / "asset-mirror"
    runner = workspace_tmp / "runner"
    DesktopBaseTaskAdapter().emit(bundle, output, _profile(str(mirror)))

    copied = copy_public_assets(output, mirror)
    verified = verify_public_assets(output)
    staged = stage_runner_files(output, runner)

    assert len(copied) == 2
    assert len(verified) == 2
    assert any(path.endswith("task_adapter-test-task.py") for path in staged)
    assert not (runner / "public_assets").exists()
    assert (runner / "task_assets" / "task_adapter-test-task" / "tests" / "assets").is_dir()


def test_material_subdirectories_are_preserved_without_flattening(
    synthetic_pptx, workspace_tmp
):
    bundle = _build_bundle(synthetic_pptx, workspace_tmp)
    for folder, payload in (("first", b"one"), ("second", b"two")):
        target = bundle / "materials" / folder / "input.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    output = workspace_tmp / "deployment"
    DesktopBaseTaskAdapter().emit(bundle, output, _profile())

    first = output / "public_assets" / "adapter-test-task" / "materials" / "first" / "input.txt"
    second = output / "public_assets" / "adapter-test-task" / "materials" / "second" / "input.txt"
    assert first.read_bytes() == b"one"
    assert second.read_bytes() == b"two"
    module = (output / "task_class" / "task_adapter-test-task.py").read_text(encoding="utf-8")
    assert "materials/first/input.txt" in module
    assert "materials/second/input.txt" in module
