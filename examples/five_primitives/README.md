# A request becomes inspectable work

This example follows one fictional request through real components:

**Conversations' Experience API → its source-owned conversation and ACP connection
→ an Agent Instance → a Workshop tool → the original conversation.**

The request is to produce an evidence-linked communication brief for a fictional
team. The Instance records accepted work. Workshop owns its build job and saved
profile. The result returns to the source conversation with the work ID and
artifact link. Two saved browser views can inspect that same conversation.
A separately launched local inspector reads the same records and renders them in
`inspect.html`, without sending another prompt.

This is a deterministic composition check, not an autonomous-model evaluation.
The actual Native Runtime executes MCP tools; a local model fixture supplies a
bounded sequence of decisions. Workshop runs its real build pipeline with its
existing synthetic extractor fixture. No paid provider or live installation is
used. Companion remains outside this example.

The exercised input set is below. These are reproducibility inputs, not a claim
that every component is a published release or that later versions are qualified.
Both engine profiles exercise the same 16 checks on Linux ARM64.

| Component | Exercised input |
| --- | --- |
| Instance | Published 0.22.6, source `2347b8d98fe518a1adea7f007202878319c98791` |
| Native engine | Candidate build `0bec7308acafbd56a6e6b2b87d49d3a79e6c33c9`; same source tree as merged Runtime PR42 |
| Conversations | Candidate build `f9e58ea4e8a0229bfd0c3b1d4eef4168ab078207` |
| Workshop | Candidate build `d09bfaec8e739e44e2fda624b6e3a54667943957` |
| Unified substitution | Published 0.95.0 wheel; Core 2.0.2, ACP SDK 1.0.0, MCP SDK 2.3.0 |
| Unified worker modules | Foundation `7526bb55842a5ec558d3bf2a3e8d8bdaea9e84e4`, loop-live `7828753b7f46c6da8f81ca13e97ee02beab30108`, context-simple `67b3170c47e63f490f5524a2a0ebd500cfd3a73c` |
| Unified MCP adapter | Candidate `cf5bc7cffcf62f484e3836e77022bb0ab1f50e75`, preserving MCP error status |

Each run captures its own binary and fixture hashes, installed Unified graph,
actual records, tool trace and oracle outcomes. Candidate build qualification is
separate from upstream acceptance, packaging and installed-product rollout.

## Run it

Supply built binaries from the component repositories and Workshop's existing
`tests/fixture_acp.py`. The selected versions must support Instance source-delivery
work references, Conversations' exact submission inspection, Workshop's advertised
`job-submission-recovery`, and Native's explicit MCP certificate trust.

```sh
python3 examples/five_primitives/run.py \
  --instance /absolute/path/to/agent-instance \
  --runtime /absolute/path/to/agent-runtime \
  --conversations /absolute/path/to/agent-conversations \
  --workshop /absolute/path/to/persona-workshop \
  --extractor-fixture /absolute/path/to/amplifier-persona-workshop/tests/fixture_acp.py \
  --output /absolute/path/to/new-private-reference-run
```

The output directory must be new. The runner creates disposable homes, binds only
loopback services, passes only its own credentials, and stops its child processes
when it finishes. The directory includes private test credentials and raw model
inputs; keep it private. Open `report.html` for the result and inspect `result.json`
for exact binary hashes and each assertion. This does not enroll, update, or start
any production installation.

### Substitute Unified's actual worker

Add `--unified-python /absolute/path/to/isolated-venv/bin/python` to run the same
journey through Unified's ACP client, host, RuntimeManager, Core and `loop-live`.
Prepare that interpreter from the selected published Unified wheel's
`amplifier_web/runtime_deps/pyproject.toml`, together with the wheel itself,
`pathspec`, and a qualified `amplifier-module-tool-mcp` revision. The MCP adapter
must preserve MCP tool errors as unsuccessful results. Keep the resolved lockfile
with the run. The runner also records installed versions and source revisions in
`unified/installed-graph.json`.

This uses an explicit MCP bundle and a local provider fixture. Supplying a prepared
worker bypasses Unified's automatic worker preparation and qualification; the
installed worker and tool loop still execute. It is a backend substitution check,
not a default Work-profile, installation, or real-model qualification. Native is
still supplied for the deliberately uninvoked peer used in the audience check.
Unified's separate bounded session-naming requests are recorded and receive a
fixture `defer` answer; they never consume foreground work decisions or stream
into the conversation.

## What the example checks

- A lost source acceptance reply is recovered by the original submission UUID.
- A creation retry finds the same work record; a separate authorized creation from
  the same input remains a separate responsibility.
- Workshop's submission HTTP reply is lost after acceptance. The Tool adapter
  returns an explicit MCP error with unknown acceptance; the agent reads the
  existing job by its caller key without submitting another build. This is not
  automatic recovery from an interrupted MCP transport.
- A separate oracle reads the saved artifact, checks content and manifest hashes
  **before** the work is marked verified and complete.
- The final message in the original conversation contains the actual work ID and
  artifact pointer. Two view records retain the same source conversation identity;
  this is not a claim of two separately implemented products.
- A second reference client reads the same authenticated Conversation and Instance
  APIs and renders the original result and work record for inspection.
- Amendment and Stop preserve the original responsibility. A later creation retry
  cannot restart it; a changed payload under the same key is refused.
- An unknown tool request stays unknown, without a mutating fallback.
- A conversation with a different audience cannot read the private work.
- Accepted work survives a failed final response. Exact receipt inspection finds
  that record while the source delivery remains unknown; nothing is replayed.

Refusals must retain explicit protocol failure status. The checks do not infer
failure from prose or accept a tool error disguised as a successful result.

The checks exercise authenticated APIs, not browser clicks. The second inspection
surface is a small reference client, not a second production product. Saved source
receipts still say `completion:not_established`; the Instance's recorded verification
remains an assertion. The separate artifact oracle is the bounded evidence here.

The MCP adapter translates two example tools to Workshop's existing HTTP build
and inspection APIs. It stores no jobs or authority. All authoritative state stays
in the component that owns it. The deliberate failure proxy and model fixtures
are test equipment, not additional ecosystem services.

## Build something different

The five roles do not prescribe five processes. This composition uses one of our
Instance implementations and Native Runtime; its external interface remains the
replaceable boundary. A different engine, Instance implementation, experience or
specialized tool can be substituted while retaining the source, work and result
relationships.

The [umbrella contracts](https://github.com/microsoft/amplifier-constellation/tree/main/contracts)
own shared promises. See the component mechanisms in
[Instance harness](https://github.com/microsoft/amplifier-constellation-instance/blob/main/docs/harness.md),
[accepted work](https://github.com/microsoft/amplifier-constellation-instance/blob/main/docs/responsibilities.md),
[Conversation APIs](https://github.com/microsoft/amplifier-constellation-conversations/blob/main/docs/api.md),
and [Workshop APIs](https://github.com/microsoft/amplifier-persona-workshop/blob/main/docs/ui-api-contract.md).

Run the local fixture checks with:

```sh
python3 examples/five_primitives/test_reference.py -v
```
