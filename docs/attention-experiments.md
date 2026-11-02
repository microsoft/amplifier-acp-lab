# Attention experiment design

The experience should give every invited agent a chance to notice relevant work,
without making every chance into a public reply. The lab now tests that boundary
using decisions from independently configured ACP agents. Example humans Alex,
Robin and Casey are invented roles, not proxies for real individuals.

The agent decides whether to speak. The client supplies room context, direct versus
group conversation type, the agent's role, and an explicit participation policy.
The client records the decision and controls delivery after cancellation. It does
not share private drafts or select a hidden winner. This leaves the same agent
usable through other ACP clients with their own conversation behavior.

## Frozen cases and conditions

`examples/attention/suite.json` declares two calibration cases and nine held-out
cases. They cover a direct message, human-to-human discussion, a named request,
an already answered question, accepting ownership, a blocker known only to the
reviewer, an open question that needs one answer, an interruption, and a delivered
and reviewed implementation. All setup messages are authored fiction. Actual
replies come from the configured ACP endpoints. No real-person persona profiles
are included, and simulated replies are not human feedback.

Both splits are frozen before the first model call. Each condition receives the
same base scenario, participant bindings and role instructions. New ACP sessions
are created per case and participant; installed persona, runtime and persistent
workspace remain the existing independent agent's. Condition order rotates by
case. Up to two cases run concurrently, and case-specific records preserve actual
timestamps and opportunities.

The three conditions are:

| Condition | Participation instruction | Context timing |
| --- | --- | --- |
| baseline | Contribute naturally if useful; otherwise pass | Same published snapshot for everyone |
| selective | Answer direct requests; avoid covered replies and unassigned work; raise material blockers | Same published snapshot for everyone |
| selective-staggered | Same selective instruction | Declared participant order; each sees earlier published replies |

Staggering is deliberately visible experiment configuration, not coordination
inside the agents. It tests whether timely delivery solves duplicate replies that
instructions alone cannot prevent. It also introduces order and latency effects;
the first participant gets the first opportunity. Generalizing this into a live
experience will require fair opportunity ordering, handling new messages while a
turn is pending, and preserving urgent interruptions.

## What the measurements establish

Every planned opportunity has an expected `speak`, `pass`, `cancelled`, or explicitly
unscored `optional` action. Expected actions are hypotheses set by the operator;
they are not sent to the agents. The report preserves each actual decision, reason,
prompt and output hash, delivery receipt and cancellation result. It shows missed
required replies alongside useful silence. Missing, errored, undelivered or
cancelled turns never count as a voluntary pass.

The one-answer case has an additional declared response window: exactly one
speaker. This measures excess speakers, not semantic equivalence. The ordinary
duplicate measure remains exact text repetition; it does not pretend to recognize
all redundant paraphrases.

The work case assigns `handoff_state(owner, accepted, blocked)` to Builder, waits
for its published code, then asks Reviewer to inspect that exact contribution.
The operator-owned `evaluate_handoff.py` checks Builder's delivered artifact in a
separate process against twelve cases and records its SHA-256. It accepts only a
small pure-function syntax subset. Neither Reviewer agreement, a scripted example,
nor another speaker's replacement establishes completion. This verifies one small
code artifact, not a production workflow or a durable background assignment.

One delivered required response demonstrates engagement, not answer quality.
One repetition per case does not establish a statistical or causal improvement.
Fresh ACP sessions do not isolate runtime memory or tool-visible workspace state.
Human experience and persona fidelity still need separate feedback from real users.
