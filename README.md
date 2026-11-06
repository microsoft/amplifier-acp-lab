# Agent Experiment Lab

Part of [Amplifier Constellation](https://github.com/microsoft/amplifier-constellation).

## Attention experiments

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

A standalone lab for observing independent agents collaborating through ordinary ACP endpoints. Define a scenario, connect the participants, run it, inspect exact contributions and delivery receipts, and compare repeated runs. Nothing depends on a fleet manager or an agent's private database.

The lab is a conversation experience of its own. It does not pretend to be Slack, and a direct ACP attachment does not acquire a Slack adapter's context or authority. Existing Slack trial recordings can be imported and compared as a separate experience.

## Start locally

Python 3.11 or newer; no runtime dependencies.

```sh
python3 -m experiment_lab --help
python3 -m unittest discover -s tests -v
python3 examples/fixture_demo.py --output /tmp/agent-lab-demo
```

Open `/tmp/agent-lab-demo/report.html`. This demonstration uses deterministic ACP subprocess fixtures, not language models or human proxies. It tests room separation, a late participant, an interrupted private draft, a revised requirement, and a separately evaluated artifact. The nine checks apply only to that exact Python artifact.

Optional installation: `python3 -m pip install .` adds the `agent-experiment-lab` command. Every command also works as `python3 -m experiment_lab` from this repository.

## Connect actual agents

Copy `examples/bindings.example.json` to a private file. Give each participant an argv array for its ordinary ACP stdio entry point and the endpoint's working directory. An argv array may invoke the agent directly, an authenticated remote ACP bridge, or SSH to an installed entry point. The lab never inserts a shell around it. Keep each participant's persistent installation separate; reuse its endpoint across rooms when testing one identity in several places.

Bindings may specify `launch_cwd`, non-secret `env`, and `secret_env` mapping environment variable names to secret file paths. Credentials belong in referenced files, not scenario text. The run captures a private copy of the bindings and their hash. It inherits a small set of ordinary operating-system and TLS variables, not all environment tokens. Existing endpoint permissions still apply. The client offers no filesystem or terminal callbacks, sends `mcpServers: []`, and cancels interactive permission requests. It does not confer responsibility tools or cross-conversation access on a bare ACP session.

```sh
python3 -m experiment_lab validate examples/workshop.json --bindings /private/lab-bindings.json
python3 -m experiment_lab run examples/workshop.json --bindings /private/lab-bindings.json --output /private/lab-runs/workshop-01
python3 -m experiment_lab evaluate /private/lab-runs/workshop-01 --evaluator profile-status
python3 -m experiment_lab report /private/lab-runs/workshop-01
```

`run` starts the configured programs and submits actual prompts. `validate` makes no connections. The sample workshop gives Alex, Robin, and Casey simulations a product problem, adds a reviewer late, revises the acceptance criteria, interrupts a builder's draft, reopens work, and requests a complete replacement artifact. A separate side room tests the same participants in another conversation. The lab supplies room history, not another room's private notes or another participant's drafts.

The final evaluator is an operator-owned program selected in the scenario. `evaluate` runs it in a separate process against the exact last delivered Python artifact from Builder; agent-proposed commands are never selected as evaluators. The scenario must still match its captured hash, and the receipt records that hash. If a recorded evaluator program changes during the check, its result is rejected. The optional evaluator `participant` filter prevents a peer's later code copy from being counted as the assigned builder's delivery. The sample verifier permits only a narrow pure-function AST and checks nine input cases. This is not a general-purpose code sandbox or a claim that the whole product is complete. Broader evaluators should run in an appropriate execution environment.

## Scenario contract

`agent-experiment-lab.scenario/1` contains a label, seed, participant map, room map, ordered steps, limits, and optional evaluators. `examples/workshop.json` is the complete example.

Participant kinds are `simulated_human`, `support_agent`, or `protocol_fixture`. The lab cannot label a generated persona as a real human. A room's members are explicit. A participant can belong to several rooms and receives a separate ACP session in each. No private agent data is read or copied between participants.

Steps:

| Action | Fields | Behavior |
| --- | --- | --- |
| `cue` | `room`, `text` | Publish a clearly labeled operator message. |
| `round` | `room`, optional `participants`, `max_words` | Ask current members concurrently against the same visible snapshot. Agents decide whether to speak or pass. |
| `join` / `leave` | `room`, `participant` | Change membership visibly. A late arrival sees the bounded room history. |

A round can include `interrupt: {"when":"first_chunk","participant":"builder","text":"..."}`. The operator cue is published when the target first streams response text. The client sends ACP cancellation, records whether cancellation was actually acknowledged, and withholds all draft replies computed against the superseded room state. A subsequent round receives the participant's own delivery receipts. A private draft is never described as something peers saw. The interruption cannot undo tools already used before it arrived.

Responses use `{"action":"speak","text":"..."}` or `{"action":"pass","reason":"..."}` in the final ACP text. Some ACP endpoints stream progress prose before their final JSON; the lab extracts a complete terminal envelope and keeps the progress in private output evidence. Plain-text agents are also supported and recorded as such; malformed attempted JSON stays private. Intermediate chunks and thoughts are not published. Raw reasoning and tool-result content are not copied into the report. Completed drafts are published in a deterministic seeded order, after the concurrent round finishes. That batch publication is an experimental condition, not a claim to reproduce Slack's exact timing.

Limits bound turns, total observation time, individual turn time, prompt history, and output size. The client closes its connections when observation ends. This does not prove that a remote runtime has stopped background work.

## Resume and ambiguous outcomes

```sh
python3 -m experiment_lab run examples/workshop.json --bindings /private/lab-bindings.json --output /private/lab-runs/workshop-02 --max-steps 3
python3 -m experiment_lab inspect /private/lab-runs/workshop-02
python3 -m experiment_lab resume /private/lab-runs/workshop-02
```

The checkpoint contains the step cursor, room messages, sessions, turns, receipts, and exact prompt/output evidence. An advertised ACP `loadSession` restores existing sessions on resume. Without that capability the lab creates a new session, supplies the recorded room projection, and reports the recreation; it does not claim native session continuity.

Finished turns are not repeated. A crash, timeout, or dropped connection during a prompt leaves an uncertain outcome, because tools might already have run. Resume stops at `needs_resolution`. After inspecting the endpoint, record the decision to skip that turn without replaying it:

```sh
python3 -m experiment_lab resolve /private/lab-runs/workshop-02 --turn TURN_ID --reason 'Inspected the endpoint and recorded what occurred; continue without replaying this request.'
python3 -m experiment_lab resume /private/lab-runs/workshop-02
```

Delivery and its published message are saved in one atomic checkpoint. A stopped process may leave `.runner.lock`; `inspect` shows its recorded process ID. Only after confirming that process stopped, use `unlock RUN --reason ...`. Scenario or binding changes require a new run, preserving the meaning of a condition and avoiding accidental identity changes during resume.

## Repeat and compare

```sh
python3 -m experiment_lab compare /private/lab-runs/workshop-01 /private/lab-runs/workshop-02 --output /private/lab-comparison
```

For a matrix, create:

```json
{
  "schema": "agent-experiment-lab.batch/1",
  "max_parallel": 2,
  "cases": [
    {"id":"baseline", "scenario":"baseline.json", "bindings":"bindings.json", "repetitions":3},
    {"id":"intervention", "scenario":"intervention.json", "bindings":"bindings.json", "repetitions":3}
  ]
}
```

Run `python3 -m experiment_lab batch /private/matrix.json --output /private/matrix-results`. Each run gets a separate checkpoint and sessions; the batch emits a comparison. Resume a partial run individually. Agents may retain memory across sessions and simultaneous runs. Use separate installations when that is a confound you need to remove; the lab does not promise memory isolation it cannot enforce.

Comparisons show whether scenarios, endpoint configurations, rosters, experiences, and lab driver versions/source hashes match. Each execution and resume records its driver identity. Missing driver evidence from older runs or Slack imports remains unknown. Measurements remain descriptive even when these match. Different rosters, model versions, retained memories, timing, and profile changes can all confound an apparent improvement.

## Understand the evidence

| Category | Recorded | Not inferred |
| --- | --- | --- |
| Task | Exact delivered artifacts, SHA-256, source message, named evaluator checks, verifier program hashes | Completion from a participant's claim; quality beyond the evaluated cases |
| Social | Contributions, words, exact repeats, prompt opportunities, silence/pass counts, explicit human observations | Naturalness or human approval from a simulation's response |
| Technical | ACP initialization, sessions, prompt timing, permission callbacks, tool-update counts, cancellation, delivery outcomes | Unknown delivery as failure/success, missing observations as zero, remote work cancellation from client shutdown |

The report is ordinary HTML plus `summary.json`. All operations and underlying view content are available through CLI and JSON; there is no hidden UI-only control plane. Reports include visible transcripts, exact artifact links, and expandable delivery/evaluator receipts. Run files are private by default and contain conversation content. Publish reports only through an authenticated surface appropriate for that content.

Use `feedback RUN --observer NAME --source REFERENCE --text '...' --human-observation` only for an actual person's observation, including its source. This records operator-entered attribution, not independently verified identity. Simulated agreement never populates this collection automatically.

## Existing Slack recordings and optional fleet integration

```sh
python3 -m experiment_lab import-slack /private/persona-workshop-trials/RUN_ID --output /private/lab-runs/slack-import
python3 -m experiment_lab observe /private/lab-runs/workshop-01 --url https://agent.example:18449 --token-file /private/observe-token --path /api/v1/profile-use
python3 -m experiment_lab submit /private/lab-runs/workshop-01 --url https://fleet.example:18455 --token-file /private/manage-token --include-transcript
```

The importer reads the existing `persona-workshop.slack-trial/1` recording, preserves actual Slack message links, and performs no network calls. It does not import credentials, impersonate Slack, rerun a trial, or convert participant claims into human feedback. Transcript-only imports report unobserved ACP metrics as null. Existing Slack trial tooling remains the Slack execution driver.

`observe` captures a read-only `/api/v1/` management response as dated evidence without treating it as independent verification. `submit` explicitly posts a report to `/api/v1/experiments`, with `label`, `run_id`, `status`, `summary`, `measurements`, optional `report_url`, and participant IDs. Fleet access is optional. All network calls require verified HTTPS, read their bearer token from a file, and refuse redirects. Failed/ambiguous writes are not automatically retried.

## Protocol references

The client follows ACP v1 [initialization and session setup](https://agentclientprotocol.com/protocol/v1/session-setup), [prompt turns](https://agentclientprotocol.com/protocol/v1/prompt-turn), and [cancellation](https://agentclientprotocol.com/protocol/v1/cancellation). Plain ACP does not prescribe a multi-party participation policy, private memory boundary, or work-ownership model; those stay with the experience and endpoint.

With Observatory 0.3.1+, `--include-transcript` also attaches delivered room messages
for review inside the fleet UI. Human simulations, operator cues, and agents retain
their labels. Turn prompts, private drafts, tool results, and bindings are excluded.
The option is explicit because the receiving fleet may have its own observers.
Without it, submission retains the existing summary-and-measurements behavior.
An external HTTPS report remains optional through `--report-url`.

## Contributing

> [!NOTE]
> This project is not currently accepting external contributions, but we're actively working toward opening this up. We value community input and look forward to collaborating in the future. For now, feel free to fork and experiment!

Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit [Contributor License Agreements](https://cla.opensource.microsoft.com).

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.

See [harness experiments](docs/harness-experiments.md) for matched context, latency, compaction and delivery measurements.
