# Frontend Status

`frontend/` is currently a retained non-core placeholder UI surface.

It is intentionally **not** the primary product interface for the Power Atlas
pipeline. The working implementation still lives under `demo/`, and the main
graph workflows still run through the CLI and validation surfaces documented in
the root README and `demo/README.md`.

Current checked-in behavior:

- the app is a minimal Next.js scaffold,
- `frontend/app/page.tsx` reads `NEXT_PUBLIC_BACKEND_URL`,
- the page performs a simple `GET /health` check against the backend,
- graph-specific backend APIs remain placeholder-only.

Operational posture:

- keep this directory defer-in-place while it still participates in the local
  scaffold posture through `docker-compose.yml`,
- do not treat it as dead code simply because it is not wired into the main
  GraphRAG runtime,
- reconsider retirement only if the placeholder UI surface is intentionally
  removed or replaced.

For the current repository-level status and migration posture, see:

- [`../README.md`](../README.md)
- `docs/repository_restructure/repository_restructure_decisions.md`
- `docs/repository_restructure/repository_restructure_phase10_legacy_retirement_shortlist.md`