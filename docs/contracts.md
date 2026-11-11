# Experiments that support defensible conclusions

<a id="experiment-execution-and-evidence-contracts"></a>

For scenario authors, runners, evaluators and result consumers. The promise:
a result can be traced to the conditions, actual delivered contributions and
checks that support it, including uncertainty and limits.

**Example:** A new configuration appears better at following a correction.
The comparison shows which scenario, model, retained state and evaluator changed,
so a reviewer can decide whether the evidence supports that conclusion.

## Lab commitments

1. **Declare the experimental condition.** Capture the scenario, participant
   bindings, driver identity, limits and relevant hashes. Simulated humans,
   operators and protocol fixtures retain their labels. Direct ACP rounds,
   imported platform transcripts and live platform trials are distinct conditions.
2. **Preserve what was delivered.** Keep private drafts and intermediate reasoning
   separate from the conversation peers saw. Publication order and cancellation
   behavior are stated by the scenario. A delivery and its message enter the same
   checkpoint; interruptions never imply that earlier tool effects were undone.
3. **Resume the identified run honestly.** Completed turns do not repeat. Uncertain
   prompts stop at resolution rather than replay. Restore advertised saved
   sessions when possible; otherwise disclose recreated sessions and their bounded
   room projection. Scenario/binding changes create a new run. A stale runner
   lock can be released only after confirming the process stopped.
4. **Use an independent, fixed check.** An operator selects the evaluator, not the
   participant's proposed command. Bind it to the exact delivered artifact and
   captured scenario/program identity. Reject changed inputs. A narrow evaluator
   proves its tested cases, not general sandbox safety or product completion.
5. **Keep measurements within their coverage.** Task artifacts, social behavior,
   technical observations and actual human feedback stay distinct. Missing samples
   are unknown. Retained memories, roster, timing, models and profiles can confound
   comparisons even when other hashes match. Closing the observer's connection
   does not prove remote background work stopped.
6. **Publish deliberately.** Runs are private evidence. Reports expose delivered
   transcripts and checked artifacts, not credentials, bindings, private drafts
   or tool results. Optional fleet submission is an attributed report, not
   certification. Importing Slack recordings does not rerun or impersonate Slack;
   ambiguous external writes are not automatically retried.

The [execution reference](execution-reference.md) owns exact scenario schemas,
commands, binding rules, checkpoints and report fields. [Attention experiments](attention-experiments.md)
and [harness experiments](harness-experiments.md) describe specific investigations.
Shared [composition](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/composition.md),
[interaction](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/interaction.md),
[work continuity](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/work-continuity.md)
and [engine compatibility](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/engine-compatibility.md)
remain with the umbrella; a scenario does not redefine production promises.

**Check:** Deliver an artifact that falsely claims completion and verify that the
independent evaluator catches it. Interrupt before and after publication, restart
with uncertain work, alter a captured binding/evaluator, and compare confounded
runs. Verify honest labels, intact receipts and conclusions bounded by the check.

**Left open:** Scenario subject, evaluator design, provider choice and report UX.
The Lab does not guarantee model quality, remote memory isolation or that its
experimental timing reproduces another experience.

## Interface section links

Existing section links lead to their exact reference below.

<a id="connect-actual-agents"></a>
[Connect actual agents](execution-reference.md#connect-actual-agents)

<a id="scenario-contract"></a>
[Scenario contract](execution-reference.md#scenario-contract)

<a id="resume-and-ambiguous-outcomes"></a>
[Resume and ambiguous outcomes](execution-reference.md#resume-and-ambiguous-outcomes)

<a id="repeat-and-compare"></a>
[Repeat and compare](execution-reference.md#repeat-and-compare)

<a id="understand-the-evidence"></a>
[Understand the evidence](execution-reference.md#understand-the-evidence)

<a id="existing-slack-recordings-and-optional-fleet-integration"></a>
[Existing Slack recordings and optional fleet integration](execution-reference.md#existing-slack-recordings-and-optional-fleet-integration)

<a id="protocol-references"></a>
[Protocol references](execution-reference.md#protocol-references)

<a id="acp-sdk-integration"></a>
[ACP SDK integration](execution-reference.md#acp-sdk-integration)
