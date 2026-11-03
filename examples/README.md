# Fictional experiment fixtures

All participants and setup messages here are authored test fiction. Alex, Robin
and Casey are generic roles; they are not profiles or proxies for real people.
Endpoint bindings are placeholders. Keep actual bindings, credentials, profiles,
transcripts and results outside the source repository.

Use new held-out scenarios and real human feedback when judging social quality.

## Shared workshop queue

`workshop-queue.json` exercises a different product domain: peers discuss a small queue card, a reviewer joins late, and a builder delivers an informational label function. The observer runs `evaluate_queue.py` against the exact final artifact. Its 128 combinations include missing and empty versions, changed scope, cancellation, busy state and readiness. These checks establish that narrow function only; simulated feedback and model reasoning are not execution or real-person endorsement.
