# Experiment execution reference

Exact bindings, scenarios, commands, recovery and evidence formats for the runner.
The [local agreement](contracts.md) explains the promises these interfaces serve.

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

Where the receiving Observatory supports transcript submission,
`--include-transcript` attaches delivered room messages
for review inside the fleet UI. Human simulations, operator cues, and agents retain
their labels. Turn prompts, private drafts, tool results, and bindings are excluded.
The option is explicit because the receiving fleet may have its own observers.
Without it, submission retains the existing summary-and-measurements behavior.
An external HTTPS report remains optional through `--report-url`.

## ACP SDK integration

The dependency declaration in [pyproject.toml](../pyproject.toml) owns the official
Python SDK pin. Inspect installed provenance when relying on its capabilities.
The [SDK-first contract](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/engine-compatibility.md)
owns shared integration policy.

A bounded application queue uses the SDK public observer and generated types to
preserve slow observation order and surface collection failures, because SDK
notification callbacks run independently and log their own exceptions. No custom
protocol framing or request-ID registry remains. Reevaluate this wrapper when
upgrading the SDK. Real SDK peers cover slow callbacks, replay, errors, limits
and transport loss.
