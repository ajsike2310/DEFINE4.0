# Member 1 — Frontend
`frontend/`: React + TS + Vite + Tailwind 4. All HTTP goes through `src/services/api.ts` (typed). Vite proxies `/api` to `127.0.0.1:8000`.
Run: `cd frontend; npm install; npm run dev` · Check: `npm run build; npm test`.
Next: browser-test every page, scheduling step in the wizard, code-splitting, component tests, Malayalam message rendering check.
