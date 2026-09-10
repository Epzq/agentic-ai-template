# Frontend — Vite + React 19 + TypeScript + MUI

The browser half of Research Opportunity Intelligence. The backend lives in `../backend/`.

## Node

**Node 20.19+ or 22.12+** — Vite 8 refuses anything older, and this machine's default `node` is
v18. `.nvmrc` pins the version that was verified:

```bash
nvm use          # reads .nvmrc
npm install
```

Every dependency is pinned exactly, with no `^` or `~` — the same rule `../backend/pyproject.toml`
follows, for the same reason: a transitive minor bump the morning of a demo is not a risk worth
carrying.

## Running it

Two topologies, one codebase. `VITE_API_BASE` is the only difference and it comes from the env
files, so there is no code edit between them.

**Development** — Vite serves the UI, FastAPI answers the API cross-origin:

```bash
cd ../backend && ROIA_DEV=1 uvicorn roia.api:app_factory --factory --port 8000   # no --reload
cd ../frontend && npm run dev                                                    # :5173
```

`ROIA_DEV` is what opens CORS, and only for `localhost:5173` — which is why `vite.config.ts` sets
`strictPort`. A Vite that quietly moved to 5174 would produce CORS failures that look like a
backend bug.

**Production** — FastAPI serves this app itself, same origin, no CORS involved:

```bash
npm run build                                            # writes dist/
cd ../backend && uvicorn roia.api:app_factory --factory  # serves dist/ and the API together
```

## Working without the backend

`?fixture=run-001` replays a real recorded run — no API keys, no network, no five-minute wait:

```
http://localhost:5173/runs/run-001?fixture=run-001&speed=10
```

`&speed=10` gets the whole run through in about two seconds. It is also the demo-day fallback if
the wifi dies.

## Checks

```bash
npm run typecheck   # tsc
npm run lint        # oxlint
npm run build       # tsc -b && vite build
```

The browser tests live in `../backend/tests/e2e/` so the project has one test runner:

```bash
cd ../backend && pytest tests/e2e -m e2e
```
