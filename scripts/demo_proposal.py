"""Generate an offline pitch dashboard, or run live agents with --live / --report.

Examples and the 90-second walkthrough are in docs/proposal-demo.md.
The default is a clearly labelled, fictional replay. No credentials are required.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from agentic_ai.analyst import analyse
from agentic_ai.demo import run_rehearsal
from agentic_ai.renderer import save_presentation
from agentic_ai.report import GrantFitReport
from agentic_ai.summarizer import summarize
from agentic_ai.ui_agent import design_presentation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--offline", action="store_true", help="Fictional replay (the default)")
    modes.add_argument("--live", action="store_true", help="Live analyst + summarizer + UI agent")
    modes.add_argument(
        "--report", type=Path, help="Saved GrantFitReport JSON; run only the two new agents"
    )
    parser.add_argument("--document", type=Path, help="Local grant context: TXT, MD, PDF, or DOCX")
    parser.add_argument("--pi-url", help="Researcher's public HTTP(S) profile URL")
    parser.add_argument("--grant-call", help="Target grant call name")
    parser.add_argument("--output", type=Path, default=Path("reports/proposal-demo"))
    parser.add_argument("--open", action="store_true", help="Open the HTML in the default browser")
    args = parser.parse_args(argv)
    if args.live:
        if not args.document or not args.pi_url:
            parser.error("--live requires --document and --pi-url")
        if not args.document.is_file():
            parser.error("The context document does not exist")
        parsed = urlparse(args.pi_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            parser.error("--pi-url must be an HTTP(S) URL")
    elif args.document or args.pi_url or args.grant_call:
        parser.error("Input fields require --live; offline mode never processes real inputs")
    fictional = not (args.live or args.report)
    stage = "rehearsal"
    try:
        if fictional:
            print("FICTIONAL REPLAY: prepared analyst data + two scripted agent outputs; no APIs.")
            summary, plan = run_rehearsal()
        else:
            stage = "analyst / report loading"
            if args.report:
                print("[1/3] Loading saved analyst report (no new research)...", flush=True)
                report = GrantFitReport.model_validate_json(args.report.read_text(encoding="utf-8"))
            else:
                print("[1/3] Analyst: reading context and researching the PI...", flush=True)
                report = analyse(str(args.document.resolve()), args.pi_url, args.grant_call)
            stage = "summarizer"
            print("[2/3] Summarizer: distilling the pitch and checking quotes...", flush=True)
            summary = summarize(report)
            stage = "UI agent"
            print("[3/3] UI agent: choosing the visual story and presenter cues...", flush=True)
            plan = design_presentation(summary)
        stage = "artifact export"
        output = args.output.expanduser().resolve()
        html = save_presentation(summary, plan, output / "index.html", fictional=fictional)
        for name, artifact in (
            ("analyst-report.json", summary.analyst_report),
            ("summary.json", summary),
            ("presentation-plan.json", plan),
        ):
            (output / name).write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        score = summary.overall_score if summary.overall_score is not None else "unknown"
        print(f"\nOverall: {score}/100")
        print(f"Open: {html.as_uri()}\nTyped handoffs saved alongside the HTML.")
        if args.open:
            webbrowser.open(html.as_uri())
        return 0
    except Exception as exc:  # noqa: BLE001 - a useful stage boundary for the live demo
        print(
            f"{stage} failed ({type(exc).__name__}). No fictional result was substituted. "
            "Check model/provider configuration, input JSON, and evidence quotes. "
            "Use --offline for an explicitly labelled rehearsal.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())