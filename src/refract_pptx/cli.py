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
from refract_pptx.build import build_task
from refract_pptx.corpus.discovery import discover_local
from refract_pptx.corpus.screening import screen_presentation
from refract_pptx.corpus.zenodo import search_zenodo
from refract_pptx.design import compile_proposal, load_proposal, proposal_prompt
from refract_pptx.evaluation import evaluate_candidate
from refract_pptx.families import registered_families
from refract_pptx.models import ContractError, TaskFamily, load_task_spec
from refract_pptx.mutation import apply_mutations
from refract_pptx.presentation import inspect_pptx, object_inventory
from refract_pptx.reports import render_report
from refract_pptx.validation import validate_bundle


def _write_json(value: Any, path: str | None = None) -> None:
    text = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


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


def _discover_zenodo(args: argparse.Namespace) -> int:
    records = (
        record.to_dict()
        for record in search_zenodo(args.query, pages=args.pages, page_size=args.page_size)
    )
    count = _write_jsonl(records, args.output)
    print(f"wrote {count} remote source records to {args.output}")
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
                f"episode {episode.episode_id}: {item}"
                for item in plugin.validate_episode(episode)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="refract",
        description="Build evidence-grounded editable-presentation reconstruction tasks.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

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

    zenodo = commands.add_parser("discover-zenodo", help="query Zenodo for PPTX records")
    zenodo.add_argument("--query", default='filetype:"pptx"')
    zenodo.add_argument("--pages", type=int, default=1)
    zenodo.add_argument("--page-size", type=int, default=100)
    zenodo.add_argument("--output", required=True)
    zenodo.set_defaults(handler=_discover_zenodo)

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

    build = commands.add_parser(
        "build-task", help="atomically build and validate a task bundle"
    )
    build.add_argument("presentation")
    build.add_argument("proposal")
    build.add_argument("--reference", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--task-id", required=True)
    build.add_argument("--source-uri", required=True)
    build.add_argument("--license", required=True)
    build.add_argument("--materials")
    build.set_defaults(handler=_build_task)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (ContractError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
