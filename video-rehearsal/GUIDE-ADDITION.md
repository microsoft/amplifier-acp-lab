# Proposed addition to the guide's pilot step (§6) and checklist (§14)

**Rehearse delivery before you scale.** A clean encode and correct metadata
don't show that your audience can watch the film. Before batch production,
run the [delivery rehearsal checklist](CHECKLIST.md) on the pilot's
actual viewer package, in the browser your audience will use.

Record the browser version, each video format, and how the files are opened.
In our [synthetic-fixture run](EVIDENCE.md) the same files behaved differently depending on
that last detail: served without HTTP range support, WebM seeking failed;
opened directly as files, the external caption track was blocked.

Report each check as passed, failed or not tested. A browser that won't
launch leaves dependent playback checks not tested, never passed. If the package ships as an offline ZIP,
test it the way recipients will open it. Testing over a local server doesn't
show that double-click viewing works.
