# Track F — Similar Platforms Review (similar-platforms) — v0.1

**Track slug:** similar-platforms  
**Applies to:** comparative reviews of tools/platforms with adjacent capabilities (OSINT, link analysis, KG tools, “influence scoring”)  
**Primary purpose:** learn capability patterns + failure modes (authority laundering, escalation, UI-driven semantic drift).  
**Default depth level:** Level 2; Level 3 if adoption or deep influence is plausible

---

## 1) When to use this track
Use when:
- reviewing an existing platform to learn what to emulate or avoid
Avoid when:
- you’re making an implementation choice for a component (use `tech-evaluation`)

## 2) Required inputs (minimum)
- [ ] Product docs + screenshots/videos where possible
- [ ] At least 1 independent critique/review or user discussion if available

## 3) Required outputs (minimum)
- Level 2:
  - [ ] Notes
  - [ ] Brief summary (recommended)
- Level 3 if it might shape PA UX/metrics:
  - [ ] Research memo (recommended)

## 4) Track-specific evaluation checklist
- [ ] What are the core affordances (search, graph exploration, ranking, pathfinding, exports)?
- [ ] What are the default interpretations invited by UI language?
- [ ] Where are provenance/time/confidence exposed vs hidden?
- [ ] What escalation hazards exist (leaderboards, “top actors”, implied guilt-by-proximity)?
- [ ] What export/share context stripping risks are likely?
- [ ] What “anti-patterns we must not replicate” are visible?

## 5) Stop rules
Stop when:
- you can list (a) 3 useful patterns and (b) 3 hazards/anti-patterns with examples
Continue to Level 3 if:
- the platform is likely to influence your design language or be integrated/competed-with

## 6) Integration targets
- Metrics philosophy + risk model docs (language/guardrails)
- A “UI hazard library” section in memos (even if informal at first)

## 7) Common pitfalls
- Copying “influence/power” language that launder authority
- Underestimating harm from defaults and exports

## 8) Suggested tags
- `comparative`, `ui-risk`, `authority-laundering`, `exports`, `osint`
