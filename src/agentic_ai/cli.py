from __future__ import annotations

import argparse
import uuid

from .agent import build_agent


def _repl() -> None:
    """A tiny REPL. One conversation thread stays alive for the whole session."""
    agent = build_agent()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    print("agentic-ai - ask a question, or type 'exit' to quit.")
    while True:
        try:
            user = input("\nyou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user.lower() in {"exit", "quit"}:
            break
        if not user:
            continue

        result = agent.invoke(
            {"messages": [{"role": "user", "content": user}]},
            config,
        )
        print(f"bot > {result['messages'][-1].content}")


def _analyse(args: argparse.Namespace) -> None:
    from .analyst import analyse

    report = analyse(args.document, args.pi_url, args.call)
    if args.json:
        print(report.model_dump_json(indent=2))
        return
    d = report.model_dump()
    print(f"PI: {d['pi']}")
    print(f"Grant Call: {d['grant_call']}")
    print(f"PI strengths and track record: {d['pi_strengths_and_track_record']}")
    print(f"Grant to PI match %: {d['grant_to_pi_match_pct']}  ({d['match_rationale']})")
    print(f"Proposed direction: {d['proposed_direction']}")
    print("Competitors:")
    for c in d["competitors"]:
        print(f"  - {c['group']} ({c['institution']}): {c['their_strengths']}")
        print(f"    vs PI: {c['vs_pi']}")
        print(f"    attack: {c['attack']}  |  avoid: {c['avoid']}")
    print("Relevant past grants:")
    for g in d["relevant_past_grants"]:
        print(f"  - {g}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="agentic-ai")
    sub = parser.add_subparsers(dest="command")

    a = sub.add_parser("analyse", help="Grant-fit analysis from a context doc + PI profile URL")
    a.add_argument("document", help="Path to the project-context document (PDF/DOCX/TXT/MD)")
    a.add_argument("pi_url", help="URL to the PI's profile page")
    a.add_argument("--call", default=None, help="Target grant call (optional; else best-fit found)")
    a.add_argument("--json", action="store_true", help="Print the raw JSON report")

    args = parser.parse_args()
    if args.command == "analyse":
        _analyse(args)
    else:
        _repl()


if __name__ == "__main__":
    main()
