# Environment Audit (2026-10-09)

| Item | Finding |
|---|---|
| OS / shell | Windows 11, PowerShell + Git Bash |
| Python | 3.13.5; project venv at `.venv` (created first, per instruction) |
| Node / npm | v22.17.1 / 9.9.4 |
| Git | 2.54 installed; **directory was not a git repository** (not initialised by me) |
| Docker | 29.1.3 present, not used |
| Repo state | Empty directory — nothing to preserve |
| Credentials | No Exotel / LLM / cloud env vars present (checked names only) |
| Local services | None |

**Skills / tools:** Claude Code skills for design/charts/artifacts exist but no project-specific frontend/FastAPI skill; none were required. No parallel agents were spawned — all four member areas were implemented sequentially in one session.

**Stack chosen:** FastAPI + SQLAlchemy 2 + SQLite; React 18 + TypeScript + Vite + Tailwind 4 + Recharts + lucide. Skipped (unneeded): shadcn/ui, Framer Motion, React Hook Form/Zod, Alembic (tables auto-created; see KNOWN_ISSUES).

**Limitations:** no Exotel account → real calling unverified. No speech-to-text service verified → audio responses route to human review.
