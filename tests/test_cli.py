from __future__ import annotations

import argparse

import agentic_ai.cli as cli
from tests.test_analyst import _REPORT


def test_analyse_command_prints_report(monkeypatch, capsys):
    monkeypatch.setattr("agentic_ai.analyst.analyse", lambda *a, **k: _REPORT)
    cli._analyse(argparse.Namespace(document="c.md", pi_url="http://pi", call=None, json=False))

    out = capsys.readouterr().out
    assert "PI: Dr A. Tan" in out
    assert "Grant to PI match %: 78" in out
    assert "Solid Power Lab" in out


def test_analyse_command_json(monkeypatch, capsys):
    monkeypatch.setattr("agentic_ai.analyst.analyse", lambda *a, **k: _REPORT)
    cli._analyse(argparse.Namespace(document="c.md", pi_url="http://pi", call=None, json=True))

    out = capsys.readouterr().out
    assert '"grant_to_pi_match_pct": 78' in out
