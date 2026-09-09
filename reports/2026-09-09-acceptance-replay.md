# Acceptance-contract repair — 2026-09-09

Observed failure: a coordinator accepted implementation/build receipts that did
not establish every requested user-facing outcome. A follow-up could repeat an
old completion receipt while a known defect or backend dependency remained.

Correction: the identity contract now retains per-requirement ownership and
requested endpoint, separates delivery from interaction acceptance, and requires
artifact review plus precise repair delivery. It does not introduce another task
store or mandate deployment for read-only work. The installed Agent Zero skill
was updated separately; running sessions are not claimed to reload it.

Bounded independent Luna replay using the revised installed skill:

| Case | Actual decision | Result |
| --- | --- | --- |
| Clipped popup; successful build; repeated old receipt | Reject completion; return exact repair to owner | PASS |
| Read-only icon discovery confirmed from source | Accept without requiring commit or deployment | PASS |
| Voice UI calling a missing backend route | Keep integration open with backend owner | PASS |

The third case was held out from the popup repair and checks the dependency rule.
These are synthetic decision replays, not production interaction tests and not a
measured latency or future reliability improvement. No before/after model replay
was run. Repository checks and installed-skill validation passed. This report
contains no private transcript excerpts or credentials.
