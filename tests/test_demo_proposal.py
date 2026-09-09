from __future__ import annotations

import json

import pytest

from agentic_ai.demo import fictional_report, run_rehearsal
from scripts import demo_proposal


def test_default_demo_never_builds_a_real_model(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("No live calls in rehearsal")

    monkeypatch.setattr("agentic_ai.summarizer.build_model", fail)
    monkeypatch.setattr("agentic_ai.ui_agent.build_model", fail)
    monkeypatch.setattr(demo_proposal, "analyse", fail)
    assert demo_proposal.main(["--output", str(tmp_path)]) == 0
    assert {path.name for path in tmp_path.iterdir()} == {
        "index.html", "analyst-report.json", "summary.json", "presentation-plan.json",
    }
    assert "FICTIONAL REHEARSAL" in (tmp_path / "index.html").read_text()
    assert json.loads((tmp_path / "summary.json").read_text())["title"]


@pytest.mark.parametrize("args", [
    ["--live"], ["--pi-url", "https://example.org/pi"],
    ["--offline", "--report", "some.json"],
])
def test_invalid_cli_modes_fail_before_models(args):
    with pytest.raises(SystemExit) as error:
        demo_proposal.main(args)
    assert error.value.code == 2


def test_live_cli_wires_all_three_stages(tmp_path, monkeypatch):
    document = tmp_path / "call.txt"
    document.write_text("Grant context")
    summary, plan = run_rehearsal()
    calls = []

    def analyse(path, url, call):
        calls.append((path, url, call))
        return summary.analyst_report

    def summarize(report):
        assert report == summary.analyst_report
        calls.append("summarizer")
        return summary

    def design(value):
        assert value == summary
        calls.append("ui")
        return plan

    monkeypatch.setattr(demo_proposal, "analyse", analyse)
    monkeypatch.setattr(demo_proposal, "summarize", summarize)
    monkeypatch.setattr(demo_proposal, "design_presentation", design)
    output = tmp_path / "live"
    assert demo_proposal.main([
        "--live", "--document", str(document), "--pi-url", "https://example.org/pi",
        "--grant-call", "Call", "--output", str(output),
    ]) == 0
    assert calls == [(str(document), "https://example.org/pi", "Call"), "summarizer", "ui"]
    assert "FICTIONAL REHEARSAL" not in (output / "index.html").read_text()


def test_saved_report_skips_analyst(tmp_path, monkeypatch):
    report = fictional_report()
    source = tmp_path / "report.json"
    source.write_text(report.model_dump_json())
    summary, plan = run_rehearsal()
    monkeypatch.setattr(
        demo_proposal, "summarize", lambda value: summary if value == report else None
    )
    monkeypatch.setattr(demo_proposal, "design_presentation", lambda _: plan)
    monkeypatch.setattr(demo_proposal, "analyse", lambda *args: pytest.fail("No new research"))
    assert demo_proposal.main(["--report", str(source), "--output", str(tmp_path / "out")]) == 0


def test_failed_provider_does_not_create_fake_pitch(tmp_path, monkeypatch, capsys):
    source = tmp_path / "report.json"
    source.write_text(fictional_report().model_dump_json())

    def fail(_):
        raise RuntimeError("sensitive provider details")

    monkeypatch.setattr(demo_proposal, "summarize", fail)
    output = tmp_path / "failed"
    assert demo_proposal.main(["--report", str(source), "--output", str(output)]) == 1
    assert not output.exists()
    error = capsys.readouterr().err
    assert "summarizer failed" in error
    assert "sensitive provider details" not in error