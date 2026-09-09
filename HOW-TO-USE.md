# How to Use the Grant-Fit Analyst with Conda

This guide shows how to set up and run the `agentic-ai-template` project using **Conda** and **Gemini**, without using `uv` or an Anthropic API key.

## 1. Go to the project directory

```bash
cd /data/nrf1/home/chinthani/hackathon/agentic-ai-template
```

Make sure the project files are present:

```bash
ls
```

You should see files/directories such as:

```text
pyproject.toml
src/
tests/
```

---

## 2. Create a Conda environment

Create a Python 3.11 environment:

```bash
conda create -n agentic-ai python=3.11 -y
```

Activate it:

```bash
conda activate agentic-ai
```

Check the Python version:

```bash
python --version
```

You should see Python 3.11.x.

> You only need to create the environment once. For future runs, just use:
>
> ```bash
> conda activate agentic-ai
> ```

---

## 3. Install the project and required packages

From the project root, run:

```bash
pip install -e ".[gemini,docs]" "langchain[google-genai]"
```

This installs:

- the `agentic-ai` project in editable mode,
- Gemini web-research support,
- PDF/DOCX document support,
- LangChain's Gemini model integration.

Verify that the CLI is installed:

```bash
agentic-ai --help
```

Also check the analyst command:

```bash
agentic-ai analyse --help
```

---

## 4. Create the `.env` file

If `.env` does not already exist:

```bash
cp .env.example .env
```

Open it:

```bash
nano .env
```

Replace its contents with the following:

```text
# Main model used by the agent/orchestrator
AGENT_MODEL=google_genai:gemini-2.5-flash

# Gemini API key
GOOGLE_API_KEY=YOUR_ACTUAL_GOOGLE_API_KEY

# Gemini model used by the web-research tools
AGENT_RESEARCHER_MODEL=gemini-2.5-flash

# Optional agent settings
AGENT_TEMPERATURE=0.0
AGENT_MAX_TOKENS=4096
AGENT_WORKDIR=./workspace
AGENT_REPORTS_DIR=./reports
```

Replace:

```text
YOUR_ACTUAL_GOOGLE_API_KEY
```

with your real Gemini API key.

You **do not need**:

```text
ANTHROPIC_API_KEY=
```

because the main agent is configured to use Gemini.

Do not commit the `.env` file to Git or share your API key publicly.

Save and exit `nano` with:

```text
Ctrl+O
Enter
Ctrl+X
```

---

## 5. Verify that the API key is being loaded

Run:

```bash
python - <<'PY'
import os
from dotenv import load_dotenv

load_dotenv()

print("Google API key available:", bool(os.getenv("GOOGLE_API_KEY")))
print("Main model:", os.getenv("AGENT_MODEL"))
print("Research model:", os.getenv("AGENT_RESEARCHER_MODEL"))
PY
```

Expected output should look similar to:

```text
Google API key available: True
Main model: google_genai:gemini-2.5-flash
Research model: gemini-2.5-flash
```

---

## 6. Optional: test Gemini before running the full analyst

```bash
python - <<'PY'
from dotenv import load_dotenv
load_dotenv()

from langchain.chat_models import init_chat_model

model = init_chat_model("google_genai:gemini-2.5-flash")
response = model.invoke("Reply with exactly: Gemini works")

print(response.content)
PY
```

If the setup is correct, you should get a response similar to:

```text
Gemini works
```

---

## 7. Run the grant-fit analyst

For the current CRP call PDF and researcher profile:

```bash
agentic-ai analyse \
    "/home/chinthani/home_of_nrf1/hackathon/agentic-ai-template/data/CRP Call Information Sheet.pdf" \
    "https://basurafernando.github.io/"
```

The quotation marks around the PDF path are required because the filename contains spaces.

### Run with the grant-call name explicitly specified

```bash
agentic-ai analyse \
    "/home/chinthani/home_of_nrf1/hackathon/agentic-ai-template/data/CRP Call Information Sheet.pdf" \
    "https://basurafernando.github.io/" \
    --call "CRP"
```

### Run and return JSON output

```bash
agentic-ai analyse \
    "/home/chinthani/home_of_nrf1/hackathon/agentic-ai-template/data/CRP Call Information Sheet.pdf" \
    "https://basurafernando.github.io/" \
    --call "CRP" \
    --json
```

---

## 8. Commands needed on future runs

After the first-time installation, you normally only need:

```bash
cd /data/nrf1/home/chinthani/hackathon/agentic-ai-template

conda activate agentic-ai

agentic-ai analyse \
    "/home/chinthani/home_of_nrf1/hackathon/agentic-ai-template/data/CRP Call Information Sheet.pdf" \
    "https://basurafernando.github.io/" \
    --call "CRP"
```

---

## 9. Optional: the browser UI

A web front end is being built in front of the same analyst. It needs one extra
install:

```bash
conda activate agentic-ai
pip install -e ".[web]"

agentic-ai serve                 # http://127.0.0.1:8000
agentic-ai serve --host 0.0.0.0 --port 8080
```

Check it is up:

```bash
curl -s localhost:8000/api/health | python -m json.tool
# {"ok": true, "model": "google_genai:gemini-2.5-flash", "gemini_key": true}
```

Upload a context document (the API the page will use in WI-5):

```bash
curl -s -F "file=@data/CRP Call Information Sheet.pdf" \
     localhost:8000/api/upload | python -m json.tool
# {"run_id": "50395eb6-...", "filename": "CRP Call Information Sheet.pdf"}
```

The file is stored under `workspace/uploads/<run_id>/`. Only `.pdf`, `.docx`,
`.txt`, `.md`, `.markdown` and `.rst` are accepted (400 otherwise), up to 10 MB
(413 otherwise).

**At this stage the page itself is only a placeholder heading** - the upload form,
the live progress log and the rendered report are still being built. Use
`agentic-ai analyse` (section 7) for real runs for now.

---

## Troubleshooting

### `agentic-ai: command not found`

Make sure the Conda environment is active:

```bash
conda activate agentic-ai
```

Then reinstall the project:

```bash
cd /data/nrf1/home/chinthani/hackathon/agentic-ai-template
pip install -e ".[gemini,docs]" "langchain[google-genai]"
```

Check again:

```bash
agentic-ai --help
```

### `Unable to import ... langchain_google_genai`

Install the Gemini LangChain integration:

```bash
pip install -U "langchain[google-genai]"
```

### Authentication error / API key not found

Check that the `.env` file is in the project root:

```bash
pwd
ls -la .env
```

Then check whether Python can load the key:

```bash
python - <<'PY'
import os
from dotenv import load_dotenv
load_dotenv()
print(bool(os.getenv("GOOGLE_API_KEY")))
PY
```

It should print:

```text
True
```

### PDF path error

Because the PDF filename contains spaces, always wrap the complete path in quotation marks:

```bash
"/home/chinthani/home_of_nrf1/hackathon/agentic-ai-template/data/CRP Call Information Sheet.pdf"
```

---

## Quick setup summary

First-time setup:

```bash
cd /data/nrf1/home/chinthani/hackathon/agentic-ai-template

conda create -n agentic-ai python=3.11 -y
conda activate agentic-ai

pip install -e ".[gemini,docs]" "langchain[google-genai]"

cp .env.example .env
nano .env

agentic-ai --help
```

Then run:

```bash
agentic-ai analyse \
    "/home/chinthani/home_of_nrf1/hackathon/agentic-ai-template/data/CRP Call Information Sheet.pdf" \
    "https://basurafernando.github.io/" \
    --call "CRP"
```
