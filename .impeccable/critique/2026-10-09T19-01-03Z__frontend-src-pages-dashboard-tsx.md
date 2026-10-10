---
target: Dashboard
total_score: 25
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 2
target_identity: "file:C:\\Users\\Admin\\Downloads\\member1\\member1\\frontend\\src\\pages\\Dashboard.tsx"
target_fingerprint: "sha256:fb4e53ffcbd8c3c96711bbc77dc2c2b7850b122b1ea4d8cccd69a19281bfe9a9"
target_path: "C:\\Users\\Admin\\Downloads\\member1\\member1\\frontend\\src\\pages\\Dashboard.tsx"
timestamp: 2026-10-09T19-01-03Z
slug: frontend-src-pages-dashboard-tsx
---
Method: dual-agent. Score 25/40 (62.5%, Acceptable). Run 2 after layout/distill/clarify/harden/colorize/polish.

Heuristics: 1:3 2:3 3:3 4:2 5:3 6:3 7:2 8:2 9:2 10:2.
Detector: 0 findings. Text contrast all AA. Chart segments Not reached (2.11) and Acknowledged (2.23) fail 3:1.

Priority issues:
- [P1] Band and headcount fight for focus (52px forecast > 22px count). (layout)
- [P1] One concept, three names (Needs attention / Needs human / follow-up queue); counts differ unexplained. (clarify)
- [P2] Tone collision: warn = Simulated, Priority 2, Running. (harden)
- [P2] Filter does not govern band/campaigns but scope text implies it does. (clarify)
- [P2] Density: always-on disclaimers, Needs human x4. (distill)
- [P3] Focus ring on linked stats clipped by overflow-hidden. (polish)
