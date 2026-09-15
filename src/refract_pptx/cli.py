from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from refract_pptx import __version__
from refract_pptx.adapters import (
    AdapterError,
    RunnerProfile,
    adapter_for,
    validate_emitted_package,
)
from refract_pptx.build import build_task
from refract_pptx.corpus.discovery import discover_local
from refract_pptx.corpus.screening import screen_presentation
from refract_pptx.demo import create_demo
from refract_pptx.design import compile_proposal, load_proposal, proposal_prompt
from refract_pptx.evaluation import evaluate_candidate
from refract_pptx.families import registered_families
from refract_pptx.models import ContractError, TaskFamily, load_task_spec
from refract_pptx.mutation import apply_mutations
from refract_pptx.office import render_pdf
from refract_pptx.pipeline import BatchRunner, RunState, load_batch_manifest
from refract_pptx.presentation import inspect_pptx, object_inventory
from refract_pptx.publication import (
    copy_public_assets,
    stage_runner_files,
    verify_public_assets,
)
from refract_pptx.reports import render_report
from refract_pptx.validation import (
    ProductionPolicy,
    record_blind_review,
    record_office_roundtrip,
    validate_bundle,
    validate_production,
)
from refract_pptx.workspace import build_workspace, init_workspace, prepare_task, workspace_status


def _write_json(value: Any, path: str | None = None) -> None:
    text = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def _capabilities(args: argparse.Namespace) -> int:
    from refract_pptx.design.catalog import OPERATION_ARGUMENTS
    from refract_pptx.design.proposal import ALLOWED_OPERATIONS, OPERATION_SCORE_COMPONENTS

    _write_json(
        {
            "version": __version__,
            "plan_version": "1.1",
            "families": {
                family.value: sorted(operations)
                for family, operations in ALLOWED_OPERATIONS.items()
            },
            "operations": {
                name: {
                    "arguments": arguments,
                    "score_components": sorted(OPERATION_SCORE_COMPONENTS.get(name, [])),
                }
                for name, arguments in OPERATION_ARGUMENTS.items()
            },
        },
        args.output,
    )
    return 0


def _write_jsonl(records: Iterable[dict[str, Any]], path: str) -> int:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def _read_json_object(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _presentation_paths(path: str) -> list[Path]:
    source = Path(path).resolve()
    if source.is_file():
        return [source]
    if source.is_dir():
        return sorted(source.rglob("*.pptx"))
    raise FileNotFoundError(source)


def _doctor(_: argparse.Namespace) -> int:
    payload = {
        "refract_version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "office_roundtrip_commands": {
            "libreoffice": shutil.which("libreoffice") or shutil.which("soffice"),
        },
        "registered_families": [plugin.family.value for plugin in registered_families()],
        "status": "ready" if sys.version_info >= (3, 11) else "unsupported_python",
    }
    _write_json(payload)
    return 0 if payload["status"] == "ready" else 1


def _inspect(args: argparse.Namespace) -> int:
    _write_json(inspect_pptx(args.path).to_dict(), args.output)
    return 0


def _discover(args: argparse.Namespace) -> int:
    seen: set[str] = set()

    def records() -> Iterable[dict[str, Any]]:
        for record in discover_local(
            args.path, license_name=args.license, source_prefix=args.source_prefix
        ):
            payload = record.to_dict()
            payload["duplicate"] = record.sha256 in seen
            seen.add(record.sha256)
            yield payload

    count = _write_jsonl(records(), args.output)
    print(f"wrote {count} source records to {args.output}")
    return 0


def _screen(args: argparse.Namespace) -> int:
    paths = _presentation_paths(args.path)

    def records() -> Iterable[dict[str, Any]]:
        for path in paths:
            try:
                yield screen_presentation(
                    path,
                    minimum_slides=args.minimum_slides,
                    maximum_slides=args.maximum_slides,
                    minimum_shapes=args.minimum_shapes,
                    minimum_quality_score=args.minimum_quality,
                ).to_dict()
            except (OSError, ValueError) as exc:
                yield {
                    "path": str(path),
                    "accepted": False,
                    "quality_score": 0.0,
                    "reasons": [f"inspection failed: {exc}"],
                    "recommended_families": [],
                }

    count = _write_jsonl(records(), args.output)
    print(f"wrote {count} screening decisions to {args.output}")
    return 0


def _validate_spec(args: argparse.Namespace) -> int:
    spec = load_task_spec(args.path)
    issues = spec.validate()
    plugin = next((item for item in registered_families() if item.family == spec.family), None)
    if plugin is None:
        issues.append(f"family is not registered: {spec.family.value}")
    elif spec.family == TaskFamily.MIXED_PRESENTATION_REPAIR:
        plugins = {item.family: item for item in registered_families()}
        for episode in spec.episodes:
            episode_plugin = plugins.get(episode.family)
            if episode_plugin is None:
                issues.append(
                    f"episode {episode.episode_id}: family is not registered: "
                    f"{episode.family.value}"
                )
            else:
                issues.extend(
                    f"episode {episode.episode_id}: {item}"
                    for item in episode_plugin.validate_episode(episode)
                )
    else:
        for episode in spec.episodes:
            issues.extend(
                f"episode {episode.episode_id}: {item}" for item in plugin.validate_episode(episode)
            )
    _write_json({"valid": not issues, "issues": issues, "task_id": spec.task_id})
    return 0 if not issues else 1


def _validate_bundle(args: argparse.Namespace) -> int:
    result = validate_bundle(args.path)
    _write_json(result.to_dict())
    return 0 if result.valid else 1


def _report(args: argparse.Namespace) -> int:
    target = render_report(args.input, args.output)
    print(target.resolve())
    return 0


def _object_inventory(args: argparse.Namespace) -> int:
    _write_json(object_inventory(args.path).to_dict(), args.output)
    return 0


def _proposal_prompt(args: argparse.Namespace) -> int:
    text = proposal_prompt(object_inventory(args.path), tuple(args.evidence))
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


def _compile_proposal(args: argparse.Namespace) -> int:
    proposal = load_proposal(args.proposal)
    plan = compile_proposal(proposal, object_inventory(args.presentation))
    _write_json(plan.to_dict(), args.output)
    return 0


def _mutate(args: argparse.Namespace) -> int:
    target = apply_mutations(args.presentation, _read_json_object(args.plan), args.output)
    print(target.resolve())
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    result = evaluate_candidate(
        args.candidate,
        args.initial,
        _read_json_object(args.plan),
    )
    _write_json(result.to_dict(), args.output)
    return 0


def _build_task(args: argparse.Namespace) -> int:
    result = build_task(
        args.presentation,
        args.reference,
        load_proposal(args.proposal),
        args.output,
        task_id=args.task_id,
        source_uri=args.source_uri,
        license_name=args.license,
        materials=args.materials,
    )
    _write_json(result.to_dict())
    return 0


def _batch_build(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest).resolve()
    output = Path(args.output).resolve()
    state = Path(args.state).resolve() if args.state else output / "run-state.sqlite"
    registry = Path(args.registry).resolve() if args.registry else output / "task-registry.sqlite"
    profile = RunnerProfile.load(args.profile) if args.profile else None
    result = BatchRunner(
        output,
        state_path=state,
        registry_path=registry,
        workers=args.workers,
        task_prefix=args.task_prefix,
        runner_profile=profile,
    ).run(load_batch_manifest(manifest))
    _write_json(result.to_dict(), args.result)
    return 0 if result.successful == len(result.items) else 1


def _run_status(args: argparse.Namespace) -> int:
    state = RunState(args.state)
    receipts = [
        {
            "item_id": item.item_id,
            "stage": item.stage,
            "status": item.status.value,
            "input_hash": item.input_hash,
            "output": item.output,
            "error": item.error,
            "updated_at": item.updated_at,
            "attempts": item.attempts,
            "owner": item.owner,
            "lease_until": item.lease_until,
        }
        for item in state.receipts()
    ]
    _write_json({"summary": state.summary(), "receipts": receipts})
    return 0


def _record_blind_review(args: argparse.Namespace) -> int:
    target = record_blind_review(
        args.bundle,
        reviewer=args.reviewer,
        decision=args.decision,
        notes=args.notes,
    )
    print(target.resolve())
    return 0


def _record_office_roundtrip(args: argparse.Namespace) -> int:
    target = record_office_roundtrip(
        args.bundle,
        args.baseline,
        args.roundtripped,
        office_suite=args.office_suite,
        notes=args.notes,
    )
    print(target.resolve())
    return 0


def _validate_production(args: argparse.Namespace) -> int:
    result = validate_production(args.bundle, ProductionPolicy.load(args.policy))
    _write_json(result.to_dict(), args.output)
    return 0 if result.valid else 1


def _emit_desktop(args: argparse.Namespace) -> int:
    if getattr(args, "production", False):
        result = validate_production(args.bundle, ProductionPolicy.load(args.policy))
        if not result.valid:
            _write_json(result.to_dict())
            return 1
    profile = RunnerProfile.load(args.profile)
    package = adapter_for(profile).emit(
        args.bundle,
        args.output,
        profile,
        runner_task_id=args.task_id,
    )
    _write_json(package.to_dict())
    return 0


def _demo(args: argparse.Namespace) -> int:
    _write_json(create_demo(args.output))
    return 0


def _render_pdf(args: argparse.Namespace) -> int:
    print(
        render_pdf(
            args.presentation, args.output, executable=args.office_executable, timeout=args.timeout
        )
    )
    return 0


def _init_workspace(args: argparse.Namespace) -> int:
    print(init_workspace(args.path))
    return 0


def _prepare_task(args: argparse.Namespace) -> int:
    print(
        prepare_task(
            args.presentation,
            args.output,
            reference=args.reference,
            source_uri=args.source_uri,
            license_name=args.license,
            materials=args.materials,
            office_executable=args.office_executable,
        )
    )
    return 0


def _workspace_status(args: argparse.Namespace) -> int:
    result = workspace_status(args.path)
    _write_json(result)
    return 0 if result["total"] and result["ready"] == result["total"] else 1


def _build_workspace(args: argparse.Namespace) -> int:
    result = build_workspace(args.path, workers=args.workers)
    _write_json(result)
    return 0 if result["successful"] == len(result["items"]) else 1


def _validate_deployment(args: argparse.Namespace) -> int:
    issues = validate_emitted_package(args.path)
    _write_json({"valid": not issues, "issues": issues, "path": str(Path(args.path).resolve())})
    return 0 if not issues else 1


def _copy_public_assets(args: argparse.Namespace) -> int:
    written = copy_public_assets(args.deployment, args.destination)
    _write_json({"written": written, "count": len(written)})
    return 0


def _verify_public_assets(args: argparse.Namespace) -> int:
    results = verify_public_assets(
        args.deployment,
        asset_base_url=args.asset_base_url,
        timeout=args.timeout,
    )
    _write_json({"verified": results, "count": len(results)})
    return 0


def _stage_runner(args: argparse.Namespace) -> int:
    written = stage_runner_files(
        args.deployment,
        args.runner_root,
        verify_assets=not args.skip_asset_verification,
        asset_base_url=args.asset_base_url,
    )
    _write_json({"written": written, "count": len(written)})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="refract",
        description="Build evidence-grounded editable-presentation reconstruction tasks.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init-workspace", help="create a portable authoring workspace")
    init.add_argument("path")
    init.set_defaults(handler=_init_workspace)
    prepare = commands.add_parser("prepare-task", help="prepare inputs and a design-agent handoff")
    prepare.add_argument("presentation")
    prepare.add_argument("--reference", help="omit to export with local LibreOffice")
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--source-uri", required=True)
    prepare.add_argument("--license", required=True)
    prepare.add_argument("--materials")
    prepare.add_argument("--office-executable")
    prepare.set_defaults(handler=_prepare_task)
    status = commands.add_parser("workspace-status", help="check which designs are ready to build")
    status.add_argument("path")
    status.set_defaults(handler=_workspace_status)
    workspace = commands.add_parser("build-workspace", help="build all ready workspace designs")
    workspace.add_argument("path")
    workspace.add_argument("--workers", type=int, default=4)
    workspace.set_defaults(handler=_build_workspace)

    demo = commands.add_parser(
        "demo", help="generate original example inputs and score real repairs"
    )
    demo.add_argument("--output", required=True)
    demo.set_defaults(handler=_demo)

    render = commands.add_parser("render-pdf", help="export a reference with isolated LibreOffice")
    render.add_argument("presentation")
    render.add_argument("--output", required=True)
    render.add_argument("--office-executable")
    render.add_argument("--timeout", type=int, default=120)
    render.set_defaults(handler=_render_pdf)

    catalog = commands.add_parser(
        "capabilities", help="list implemented operations and scoring contracts"
    )
    catalog.add_argument("--output")
    catalog.set_defaults(handler=_capabilities)

    doctor = commands.add_parser("doctor", help="check the local runtime")
    doctor.set_defaults(handler=_doctor)

    inspect_command = commands.add_parser("inspect", help="inspect a PPTX package")
    inspect_command.add_argument("path")
    inspect_command.add_argument("--output")
    inspect_command.set_defaults(handler=_inspect)

    object_inventory_command = commands.add_parser(
        "inventory-objects", help="inventory editable objects and native chart semantics"
    )
    object_inventory_command.add_argument("path")
    object_inventory_command.add_argument("--output")
    object_inventory_command.set_defaults(handler=_object_inventory)

    discover = commands.add_parser("discover", help="manifest PPTX files in a local corpus")
    discover.add_argument("path")
    discover.add_argument("--output", required=True)
    discover.add_argument("--license", default="unknown")
    discover.add_argument("--source-prefix", default="file://")
    discover.set_defaults(handler=_discover)

    screen = commands.add_parser("screen", help="mechanically screen a PPTX corpus")
    screen.add_argument("path")
    screen.add_argument("--output", required=True)
    screen.add_argument("--minimum-slides", type=int, default=3)
    screen.add_argument("--maximum-slides", type=int, default=100)
    screen.add_argument("--minimum-shapes", type=int, default=8)
    screen.add_argument("--minimum-quality", type=float, default=0.35)
    screen.set_defaults(handler=_screen)

    validate_spec = commands.add_parser("validate-spec", help="validate a TaskSpec")
    validate_spec.add_argument("path")
    validate_spec.set_defaults(handler=_validate_spec)

    validate_bundle_command = commands.add_parser(
        "validate-bundle", help="validate a complete task bundle"
    )
    validate_bundle_command.add_argument("path")
    validate_bundle_command.set_defaults(handler=_validate_bundle)

    report = commands.add_parser("report", help="render an HTML corpus report")
    report.add_argument("input")
    report.add_argument("--output", required=True)
    report.set_defaults(handler=_report)

    prompt = commands.add_parser(
        "proposal-prompt", help="produce the evidence-limited agent design prompt"
    )
    prompt.add_argument("path")
    prompt.add_argument("--output")
    prompt.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="describe an attached reference render or material visible to the design agent",
    )
    prompt.set_defaults(handler=_proposal_prompt)

    compile_command = commands.add_parser(
        "compile-proposal", help="compile a declarative agent proposal against a deck"
    )
    compile_command.add_argument("presentation")
    compile_command.add_argument("proposal")
    compile_command.add_argument("--output", required=True)
    compile_command.set_defaults(handler=_compile_proposal)

    mutate = commands.add_parser("mutate", help="apply a compiled mutation plan")
    mutate.add_argument("presentation")
    mutate.add_argument("plan")
    mutate.add_argument("--output", required=True)
    mutate.set_defaults(handler=_mutate)

    evaluate = commands.add_parser("evaluate", help="score a candidate relative to its init")
    evaluate.add_argument("candidate")
    evaluate.add_argument("initial")
    evaluate.add_argument("plan")
    evaluate.add_argument("--output")
    evaluate.set_defaults(handler=_evaluate)

    build = commands.add_parser("build-task", help="atomically build and validate a task bundle")
    build.add_argument("presentation")
    build.add_argument("proposal")
    build.add_argument("--reference", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--task-id", required=True)
    build.add_argument("--source-uri", required=True)
    build.add_argument("--license", required=True)
    build.add_argument("--materials")
    build.set_defaults(handler=_build_task)

    batch = commands.add_parser(
        "batch-build", help="resume-safe concurrent build from a JSONL manifest"
    )
    batch.add_argument("manifest")
    batch.add_argument("--output", required=True)
    batch.add_argument("--state")
    batch.add_argument("--registry")
    batch.add_argument("--workers", type=int, default=4)
    batch.add_argument("--task-prefix", default="refract")
    batch.add_argument("--profile", help="optionally emit runner deployments after each build")
    batch.add_argument("--result")
    batch.set_defaults(handler=_batch_build)

    run_status = commands.add_parser("run-status", help="show resumable batch stage state")
    run_status.add_argument("state")
    run_status.set_defaults(handler=_run_status)

    blind = commands.add_parser(
        "record-blind-review", help="record a review using only agent-visible evidence"
    )
    blind.add_argument("bundle")
    blind.add_argument("--reviewer", required=True)
    blind.add_argument("--decision", choices=("pass", "fail"), required=True)
    blind.add_argument("--notes", default="")
    blind.set_defaults(handler=_record_blind_review)

    roundtrip = commands.add_parser(
        "record-office-roundtrip",
        help="compare an oracle-quality deck before and after office save",
    )
    roundtrip.add_argument("bundle")
    roundtrip.add_argument("baseline")
    roundtrip.add_argument("roundtripped")
    roundtrip.add_argument("--office-suite", required=True)
    roundtrip.add_argument("--notes", default="")
    roundtrip.set_defaults(handler=_record_office_roundtrip)

    production = commands.add_parser(
        "validate-production", help="apply strict publication gates to a bundle"
    )
    production.add_argument("bundle")
    production.add_argument("--policy")
    production.add_argument("--output")
    production.set_defaults(handler=_validate_production)

    emit_desktop = commands.add_parser(
        "emit-desktop", help="adapt a neutral bundle for a BaseTask desktop runner"
    )
    emit_desktop.add_argument("bundle")
    emit_desktop.add_argument("--profile", required=True)
    emit_desktop.add_argument("--output", required=True)
    emit_desktop.add_argument("--task-id")
    emit_desktop.set_defaults(handler=_emit_desktop)

    release = commands.add_parser(
        "release-desktop", help="validate production evidence then export"
    )
    release.add_argument("bundle")
    release.add_argument("--profile", required=True)
    release.add_argument("--output", required=True)
    release.add_argument("--task-id")
    release.add_argument("--policy")
    release.set_defaults(handler=_emit_desktop, production=True)

    validate_deployment = commands.add_parser(
        "validate-deployment", help="validate an emitted runner deployment package"
    )
    validate_deployment.add_argument("path")
    validate_deployment.set_defaults(handler=_validate_deployment)

    copy_public = commands.add_parser(
        "copy-public-assets", help="copy public task assets into a local dataset or mirror"
    )
    copy_public.add_argument("deployment")
    copy_public.add_argument("destination")
    copy_public.set_defaults(handler=_copy_public_assets)

    verify_public = commands.add_parser(
        "verify-public-assets", help="download and hash every published public asset"
    )
    verify_public.add_argument("deployment")
    verify_public.add_argument("--asset-base-url")
    verify_public.add_argument("--timeout", type=int, default=60)
    verify_public.set_defaults(handler=_verify_public_assets)

    stage_runner = commands.add_parser(
        "stage-runner", help="install task code and hidden evaluator assets into a runner"
    )
    stage_runner.add_argument("deployment")
    stage_runner.add_argument("runner_root")
    stage_runner.add_argument("--asset-base-url")
    stage_runner.add_argument("--skip-asset-verification", action="store_true")
    stage_runner.set_defaults(handler=_stage_runner)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (AdapterError, ContractError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
