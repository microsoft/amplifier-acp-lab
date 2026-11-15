# Pilot-stage delivery rehearsal: checklist

Run once per pilot, before batch production. This checks whether a viewer can
actually watch the package. It does not judge story, voice, animation, caption
wording, or the presentation device.

## Result states (exactly three)
- passed: the check ran and met the expectation
- failed: the check ran and did not meet it
- not tested: the check did not run (always record why)

A failed prerequisite (e.g. browser won't launch) is recorded as such; every
check that depends on it is "not tested", never passed.

## Record for every run
- [ ] Package identity (file names + hashes)
- [ ] Browser name and exact version
- [ ] Video format under test (H.264 MP4, VP9 WebM, ...)
- [ ] Opening/serving method: HTTP with range support (206 to a range probe) /
      HTTP without range support (200, whole file) / direct file:// open
- [ ] Original package or extracted copy of the ZIP

## Checks
1. [ ] Prerequisite: browser launches
2. [ ] Decoded playback per format, forced individually: clock advances AND
       rendered pixels change (canPlayType alone is not evidence)
3. [ ] Seek to a known time (fixture: 4 s) lands there
4. [ ] Known caption cue (fixture: FIXTURE CUE ONE) is active and visibly
       changes the frame
5. [ ] Negative control: missing-caption package plays video but FAILS captions

## Worked examples (synthetic fixture, Chromium 156.0.8078.4)

| Serving method | WebM seek | External captions | Evidence |
|---|---|---|---|
| HTTP, no range support | failed (back to 0 s; [0,0]) | passed | [Simple results](evidence/simple-results.json) |
| HTTP, range support | passed (4 s) | passed | [Range results](evidence/range-results.json) |
| Direct file:// open | passed | failed (VTT blocked) | [Diagnosis](evidence/seek-diagnosis.json) |

- Remuxing with `-cues_to_front 1` did not fix seeking on the no-range server.
- No browser security flags were disabled.
- Direct-file diagnosis records active cues and console errors, not caption pixel
  comparison; HTTP checks include the rendering comparison.
- These observations concern this fixture and browser, not the guide's actual films.

## Labelling rule
An extracted ZIP checked over HTTP must not be reported as "double-click
offline viewing passed". Report the method actually used.

Run instructions: [RUN.md](RUN.md). Evidence and limits: [EVIDENCE.md](EVIDENCE.md).
