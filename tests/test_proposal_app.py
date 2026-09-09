from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

_APP = Path(__file__).resolve().parents[1] / "scripts" / "proposal_app.py"


def test_form_rehearsal_renders_without_credentials():
    app = AppTest.from_file(str(_APP)).run(timeout=20)
    assert not app.exception
    assert all(field.disabled for field in app.text_input)
    app.button[0].click().run(timeout=20)
    assert not app.exception
    html, summary, _ = app.session_state["pitch"]
    assert "FICTIONAL REHEARSAL" in html
    assert summary.overall_score == 82


def test_live_form_requires_valid_input():
    app = AppTest.from_file(str(_APP)).run(timeout=20)
    app.toggle[0].set_value(False).run()
    app.button[0].click().run()
    assert not app.exception
    assert "valid HTTP(S)" in app.error[0].value