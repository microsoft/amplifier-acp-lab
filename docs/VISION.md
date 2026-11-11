# ACP Lab vision

People building agent systems need to know whether a change improves useful
work, not only whether an agent can produce a convincing answer. ACP Lab should
help them turn a question into a bounded experiment, observe what the participants
actually do, check the result independently, and use that evidence to decide what
to improve next.

The lab works with independently configured agents through Agent Client Protocol
(ACP). It can examine collaboration, communication, execution and context handling
without requiring a particular engine or fleet manager. Each experiment makes
its conditions explicit so differences in models, retained state, opportunities
or delivery are not mistaken for the effect being studied.

## Make evidence useful for judgment

A contributor should be able to follow a result from the original scenario to
the actual input, participant response, delivered artifact and named check. A
claim that work is complete is a subject for evaluation. It is not itself the
independent result. An uncertain observation should remain uncertain.

The lab should make repeated trials and comparisons practical while preserving
their limits. Protocol fixtures can establish a transport boundary. Model trials
can reveal behavior under stated conditions. Real people can judge whether the
experience helped them. These forms of evidence answer different questions and
should be easy to distinguish.

## Support independent work across the ecosystem

The lab is a consumer of agent and source interfaces, not the owner of the agents
or the systems they act in. Owners can investigate a complete journey or isolate
one boundary, then bring concrete findings to the people responsible for it.
The [family agreement](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/family.v1-candidate.md)
owns that division of responsibility.

A useful experiment can influence what the team chooses to build, not merely
produce another score. Reports should help people understand the result,
challenge the interpretation and make a consequential decision without requiring
them to inspect every event. Existing report pages are reference access to the
evidence, not a fixed future product UX.

## Judge the contribution

Success means that an owner can make a better-supported decision with less
repetition and rescue. Judge whether the scenario exposes a meaningful question,
the check can catch a plausible failure, and the conclusion stays within what was
observed. Inspect current behavior when designing the next trial; keep results
with that experiment rather than maintaining a general feature or gap inventory.

The [local contracts](contracts.md) define scenario execution, measurement and
recovery. The [attention](attention-experiments.md) and
[harness](harness-experiments.md) documents apply them to particular experiment
families.
