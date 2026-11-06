# Comparing harness changes

Freeze the engine, Instance and adapter revisions, model/settings, scenario,
initial files and accepted task budgets before testing. Prepare calibration and
held-out cases before inspecting outputs. A different conversation experience
is a separate condition, not an interchangeable run.

Use the existing suite-prepare/run/report commands for matched collaboration
cases. Collect the optional native `diagnostics` report before and after each
condition with the lab's authenticated `observe` command. Store evidence
privately. Compare only non-overlapping event windows; a retained sample cannot
reconstruct older events. Missing provider measurements are unknown.

Include these cases alongside task outcome checks:

| Case | Required observation |
| --- | --- |
| A slow healthy response | No short adapter cutoff; actual terminal result |
| A disconnected provider | Explicit unknown/failure; no uncertain replay |
| Several updates during one tool | Stable ordered input IDs, original effect once, latest final answer |
| Compaction while updates arrive | Signed state preserved, matching terminal, no lost tool result |
| Incorporation followed by attention | Same source revision/time; policy sees receipt but completion remains unproven |
| Human question during work pacing | Response latency measured separately from action admission |
| Commentary before a tool | Scoped public status, no private reasoning, no commentary-only final |
| Resume after maintenance | Same session and authority; no renewed work budget |

Report independently: checked task outcome, duplicate effects, human response
latency, model steps, observed provider responses, reported input/output/cache
usage, compaction time, context bytes and stop reasons. Usage notifications are
not model request counts. A smaller prompt or cache hit is not an overall
quality/cost improvement by itself. Obtain actual human feedback for whether
participation feels helpful; a model judge alone cannot establish that.

Deterministic protocol regressions live with Runtime, Instance and the adapters.
They establish transport and effect invariants, not model quality. Live provider
smoke checks establish only the tested model/account combination. Do not present
a fixture result as a live model success or infer cross-provider equivalence.

Reference guidance: [OpenAI agent improvement loop](https://developers.openai.com/cookbook/examples/agents_sdk/agent_improvement_loop),
[cache diagnostics](https://developers.openai.com/api/docs/guides/prompt-caching/diagnostics),
[Anthropic context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents),
and [writing tools for agents](https://www.anthropic.com/research/writing-tools-for-agents).
