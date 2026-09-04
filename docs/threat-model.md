# Threat model

## Assets and trust boundaries

Protected assets are tracker tokens, work-item content, source URLs, policy documents, snapshots, and assessment integrity. Tracker data is untrusted. Bundled/replaced Markdown policy files are trusted configuration and therefore require repository or deployment-level review.

| Threat | v0.1.0 control | Residual risk |
|---|---|---|
| Token disclosure | Environment/secrets only; tokens excluded from domain models, persistence, logs, and error detail | Host/process compromise remains out of scope |
| Excess tracker access | Read-only GET clients and no write tools/endpoints | Provider token scopes must still be configured minimally |
| Prompt injection in ticket text | Tracker output explicitly labeled untrusted; fixed system boundary; allowlisted tools; automated injection case | Novel social-engineering text may still influence prose before validation |
| LLM data exposure | Live mode is opt-in; replay requires no LLM; send only tool-selected run data | Users must assess provider and organizational data policy |
| Invented facts, actions, or IDs | Facts computed before the model; strict schema; exact signal/policy binding; allowlisted action catalog; evidence/item reference validation | A human still owns the final management decision |
| Malformed model output | Strict structured output and Pydantic validation; safe replay fallback | Live synthesis may be unavailable |
| Malicious source URL | Canonical models require HTTPS; UI renders references as text in v0.1.0 | Trusted-provider domain allowlisting is deferred |
| Policy tampering/conflict | File-based reviewable sources, stable section IDs, and conflicting threshold detection | A human policy owner must resolve detected conflicts |
| Arbitrary execution | No shell, network, messaging, tracker-write, or dynamic-code tools | Application host security remains operational responsibility |

The product is advisory. It cannot execute escalation, change ownership/status/deadlines, post comments, send notifications, accept risk, or approve a release.
