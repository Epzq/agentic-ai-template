"""``python -m roia run --grant URL --profile URL`` — the whole pipeline from a terminal.

Phase 1's deliverable: a real report, from real sources, without a browser in sight. The
same ``run_pipeline`` the API will call in Phase 2, so anything that works here works there.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from roia.config import get_settings
from roia.events import Run
from roia.evidence import EvidenceStore
from roia.ingest import probe as run_probe
from roia.paths import RUNS_DIR
from roia.pipeline import RunInputs, run_pipeline

#: The Day-1 fixture WI-2.3 replays. A run overwrites it; pass --events to keep it.
DEFAULT_EVENTS = "fixtures/run-001.jsonl"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roia", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="analyse a grant call against a researcher profile")
    run_cmd.add_argument(
        "--grant", required=True,
        help="the call's URL, or a local PDF. A URL is strongly preferred: a local file has "
             "no HTTP status to record honestly, so its rows carry file:// links.",
    )
    run_cmd.add_argument("--profile", help="the researcher's page (default: ROIA_DEMO_PROFILE_URL)")
    run_cmd.add_argument("--out", default=None, help="directory for report.json and report.md")
    run_cmd.add_argument("--events", default=DEFAULT_EVENTS,
                         help=f"JSONL event log (default {DEFAULT_EVENTS})")
    run_cmd.add_argument(
        "--answer", action="append", default=[], metavar="CODE=VALUE",
        help="answer a pre-flight question without being asked; repeatable",
    )
    run_cmd.add_argument("--skip-probe", action="store_true",
                         help="do not run the pre-flight probe (ingests twice; mainly for tests)")

    args = parser.parse_args(argv)
    return _run(args)


def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    profile_url = args.profile or settings.demo_profile_url
    if not profile_url:
        print("no --profile given and ROIA_DEMO_PROFILE_URL is unset", file=sys.stderr)
        return 2

    answers = dict(pair.split("=", 1) for pair in args.answer if "=" in pair)
    run_id = f"run-{datetime.now(UTC):%Y%m%d-%H%M%S}"
    out = Path(args.out) if args.out else RUNS_DIR / run_id
    out.mkdir(parents=True, exist_ok=True)

    run = Run(run_id, jsonl_path=args.events)
    store = EvidenceStore()
    started = time.monotonic()

    probe_result = None
    if not args.skip_probe:
        print(f"probing {args.grant} …", file=sys.stderr)
        probe_result = run_probe(args.grant, profile_url, store)
        for question in probe_result.questions:
            chosen = answers.get(question.code, question.default)
            label = next((o.label for o in question.options if o.value == chosen), chosen)
            print(f"  {question.code}: {label}", file=sys.stderr)

    print(f"running {run_id} …", file=sys.stderr)
    result = run_pipeline(
        RunInputs(grant_src=args.grant, profile_url=profile_url, answers=answers),
        run, probe=probe_result, store=store,
    )

    report_json = out / "report.json"
    report_md = out / "report.md"
    if result.report is not None:
        report_json.write_text(json.dumps(result.report.model_dump(mode="json"), indent=1))
        report_md.write_text(result.markdown)

    elapsed = time.monotonic() - started
    warnings = [e.model_dump()["code"] for e in run.warnings()]
    print(
        f"\n{run_id}  {elapsed:.0f}s\n"
        f"  directions : {len(result.directions)}\n"
        f"  evidence   : {len(result.store)} rows, "
        f"{len(result.store.of_type('paper'))} papers\n"
        f"  events     : {len(run.events)} -> {args.events}\n"
        f"  warnings   : {', '.join(sorted(set(warnings))) or 'none'}\n"
        f"  report     : {report_json} · {report_md}",
        file=sys.stderr,
    )
    # A run that produced no directions did not do its job, whatever else it managed.
    return 0 if result.directions else 1


if __name__ == "__main__":
    raise SystemExit(main())
