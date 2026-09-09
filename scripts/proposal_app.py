"""Optional Streamlit input form. Run with streamlit run scripts/proposal_app.py."""

from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st
import streamlit.components.v1 as components

from agentic_ai.analyst import analyse
from agentic_ai.config import Settings
from agentic_ai.demo import run_rehearsal
from agentic_ai.renderer import render_presentation
from agentic_ai.summarizer import summarize
from agentic_ai.ui_agent import design_presentation


def main() -> None:
    st.set_page_config(page_title="Proposal Studio", page_icon="✳", layout="wide")
    st.title("✳ Proposal Studio")
    st.caption("Grant call + PI → research → story → an audience-ready pitch")
    with st.sidebar:
        st.header("Build your pitch")
        fictional = st.toggle("Fictional rehearsal (no API keys)", value=True)
        if fictional:
            st.info("Replays an invented battery project. Disabled inputs are not processed.")
        else:
            st.warning("Live mode sends grant text and PI information to your model providers.")
        with st.form("proposal-input"):
            grant_call = st.text_input("Grant call name", disabled=fictional)
            pi_url = st.text_input("PI webpage (https://…)", disabled=fictional)
            context = st.text_area(
                "Paste grant call / project context", height=180, disabled=fictional
            )
            upload = st.file_uploader(
                "Or upload the grant context",
                type=["txt", "md", "pdf", "docx"], disabled=fictional,
            )
            st.caption("Paste text OR upload. PDF/DOCX need the docs extra. Max upload: 10 MB.")
            submitted = st.form_submit_button("Generate pitch ↗", type="primary")
    if submitted:
        if not fictional:
            parsed = urlparse(pi_url)
            if parsed.scheme not in ("https", "http") or not parsed.netloc:
                st.error("Enter a valid HTTP(S) PI webpage.")
                st.stop()
            if bool(context.strip()) == bool(upload):
                st.error("Provide either pasted context or an upload, not both.")
                st.stop()
            if upload is not None and upload.size > 10 * 1024 * 1024:
                st.error("Upload must be 10 MB or smaller.")
                st.stop()
        # Never show a stale pitch as the result of a failed or different run.
        st.session_state.pop("pitch", None)
        with st.status("Building the three-agent pitch…", expanded=True) as status:
            try:
                if fictional:
                    st.write("Replaying fictional research and prepared outputs for both agents.")
                    summary, plan = run_rehearsal()
                else:
                    with tempfile.TemporaryDirectory(prefix="proposal-studio-") as folder:
                        suffix = Path(upload.name).suffix.lower() if upload is not None else ".txt"
                        document = Path(folder) / f"grant-context{suffix}"
                        content = upload.getvalue() if upload is not None else context.encode()
                        document.write_bytes(content)
                        settings = Settings(reports_dir=str(Path(folder) / "analyst-reports"))
                        st.write("1 / Analyst · Researching the grant and PI.")
                        report = analyse(
                            str(document), pi_url, grant_call or None, settings=settings
                        )
                    st.write("2 / Summarizer · Distill the story; validate supporting quotes.")
                    summary = summarize(report)
                    st.write("3 / UI agent · Choose composition and speaker cues.")
                    plan = design_presentation(summary)
                html = render_presentation(summary, plan, fictional=fictional)
                st.session_state["pitch"] = (html, summary, plan)
                status.update(label="Pitch ready", state="complete", expanded=False)
            except Exception as exc:  # noqa: BLE001 - preserve a recoverable demo UI
                status.update(label="Generation failed", state="error")
                st.error(
                    f"{type(exc).__name__}: check API/provider configuration and input quality. "
                    "No fabricated fallback was substituted. Rehearsal mode works without APIs."
                )
    if "pitch" in st.session_state:
        html, summary, plan = st.session_state["pitch"]
        st.download_button("Download standalone pitch", html, "proposal.html", mime="text/html")
        st.caption("Open the downloaded HTML in its own tab for the best presenter experience.")
        components.html(html, height=1100, scrolling=True)
        with st.expander("Inspect typed agent handoffs"):
            st.json(summary.model_dump())
            st.json(plan.model_dump())
    else:
        st.info("Start with rehearsal, or switch it off to use your grant call and PI.")


if __name__ == "__main__":
    main()