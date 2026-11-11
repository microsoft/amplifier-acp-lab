# Attention experiment design

The experience should give every invited agent a chance to notice relevant work,
without making every chance into a public reply. The lab tests that boundary
using decisions from independently configured ACP agents. Example humans Alex,
Robin and Casey are invented roles, not proxies for real individuals.

The agent decides whether to speak. The client supplies room context, direct versus
group conversation type, the agent's role, and an explicit participation policy.
The client records the decision and controls delivery after cancellation. It does
not share private drafts or select a hidden winner. This leaves the same agent
usable through other ACP clients with their own conversation behavior.

The [Lab execution contract](contracts.md) owns general scenario, recovery and
evidence semantics. This document owns the attention suite's specific controls
and experimental interpretation. Commands run from the repository root.

## Prepare and run the suite

The attention suite asks when an agent should answer, stay quiet, raise a blocker,
or hand work over. It uses the same independent ACP endpoints as ordinary runs.
An agent must return its own `speak` or `pass` decision. The lab never creates a
pass by suppressing a prompt or choosing which peer is allowed to answer.

```sh
python3 -m experiment_lab suite-prepare examples/attention/suite.json \
  --bindings /path/to/private-bindings.json --split calibration \
  --output private/attention-calibration --max-parallel 2
python3 -m experiment_lab suite-prepare examples/attention/suite.json \
  --bindings /path/to/private-bindings.json --split held_out \
  --output private/attention-held-out --max-parallel 2
python3 -m experiment_lab suite-run private/attention-calibration
python3 -m experiment_lab suite-run private/attention-held-out
python3 -m experiment_lab suite-report private/attention-held-out
```

Prepare both splits before inspecting model outputs. Preparation makes no model
calls and freezes every case, expected action, condition, endpoint binding and
driver hash. `suite-run` resumes unfinished work without repeating completed or
uncertain prompts. A changed driver or plan requires a new experiment. Raw
prompts, actual decisions, cancellation receipts, transcripts, evaluator receipts
and HTML/JSON reports remain under the private output folder.

Each condition receives the same base scenario, participant bindings and role
instructions. New ACP sessions are created per case and participant; installed
persona, runtime and persistent workspace remain the existing independent agent's.
Condition order rotates by case. Up to two cases run concurrently in the example
commands, and case records preserve actual timestamps and opportunities.

The supplied suite has two calibration cases and nine held-out cases, including
direct messages, human-to-human exchanges, named requests, covered answers,
ownership offers, an unaddressed blocker, one-answer questions, interrupted work,
and a small implemented-and-reviewed artifact. Alex, Robin and Casey are entirely fictional
participants, with no personal profiles supplied; authored setup lines are labeled `scripted_context` and
are excluded from contribution and artifact counts. Only actual ACP replies count
as observed behavior. The expected actions are operator hypotheses, not ratings
from the real people or proof that the wording felt natural.

Three explicit conditions compare the old general instruction with selective
participation, then selective participation with staggered turns. Configure this
per scenario or suite condition:

```json
{
  "attention": {
    "policy": "selective",
    "scheduling": "staggered",
    "ambient_threshold": "material",
    "duplicate_window": 8,
    "direct_reply": true
  }
}
```

`baseline` preserves the general “contribute if useful” instruction. `selective`
adds explicit expectations for direct replies, ownership, useful silence,
avoiding repetition, and material blockers. `ambient_threshold` can be `material`
or `relevant`; the duplicate window is 1–100 visible messages. These are client
instructions, not a permissions system or runtime scheduler. Existing scenarios
without `attention` retain simultaneous execution and their existing behavior.

With `simultaneous`, all participants see the same published snapshot. With
`staggered`, the declared participant order is used and each completed contribution
is delivered before the next opportunity. Every listed participant is still
prompted. There is no hidden peer coordinator, private draft exchange, or selected
winner. Ordering is an experimental condition because later participants receive
more information. Private role facts and pass reasons are never shown to peers.

Staggering tests whether timely delivery reduces duplicate replies, but also
introduces order and latency effects. Applying that finding in a live experience
requires separate checks for fair opportunities, new input during pending turns
and urgent interruption; this experiment alone does not establish those outcomes.

`recheck` starts the drafts together, then asks the same agent to reconsider its
own unpublished draft if the public room changed before delivery. The extra
prompt contains the updated public room and that agent's draft only. Its fresh
`speak` or `pass` is recorded alongside both inputs and outputs. It consumes the
same total model-call budget. Interrupted or uncertain checks stay unpublished;
they are not counted as successful silence or silently retried.

`examples/attention/recheck-regression-suite.json` compares all three scheduling
conditions over five previously observed cases. It labels them calibration,
not fresh holdouts. Set `--repetitions 3` when preparing it to run 45 cases.
Its `participant_order: "rotate"` counterbalances first-speaker position across
repetitions while keeping each repetition's order identical across conditions.
The report records extra publication calls and their latency. Use new held-out
scenarios and actual human feedback before making broader quality claims.

`examples/attention/fresh-holdouts-suite.json` supplies four additional authored
cases: two distinct named requests, thinking aloud without a request, a material
correction to stale status, and a factual question needing just one reply. Prepare
with `--split held_out --repetitions 2` for 24 runs. Freeze these cases before inspecting new outputs; use fresh cases for later
independent evaluation. Human ratings remain separate from the expected-action checks.

The report shows required replies and useful silence separately. A failed,
cancelled, missing or ambiguous turn earns no silence credit; a missing required
reply remains a miss even when the transport failed. Speech alone does not prove
the request was satisfied. For the work case, a separate operator-owned process
checks the assigned Builder’s exact delivered function against twelve cases;
scripted code and another speaker’s replacement cannot satisfy that check.
Fresh sessions do not guarantee isolated persistent agent memory. Repeated trials
and real human observation are still needed before claiming a better experience.

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
