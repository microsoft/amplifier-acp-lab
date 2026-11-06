# Recorded browser evidence

Recorded 2026-11-06 by Probe, using synthetic media only. This is author-executed evidence, not independent review. Browser: Chromium 156.0.8078.4, headless, Linux ARM64. Scripts launch with Playwright's normal defaults and no browser security-bypass flags.

## Working route

[Range HTTP results](evidence/range-results.json): six rows (good, missing-caption, ZIP-extracted good, each forced to MP4 and WebM). All six decoded-picture and clock checks passed, and all seeks landed at 4 seconds. The four good/extracted rows displayed `FIXTURE CUE ONE`; hiding the track changed the captured video pixels. Both missing-caption rows failed captions as intended while video and seek passed. A deliberately broken package has NOT been relabeled a passing product.

Picture change is measured from two canvas captures of decoded video frames, along with advancing time and nonzero decoded-frame count. Caption rendering is checked at a paused frame by active cue text and a screenshot difference with captions showing versus hidden. Native video controls are removed for this comparison to avoid control-animation differences. This is a mechanical rendering check, not a subjective legibility or synchronization review. Screenshots are regenerated into the run directory; the checked-in JSON records outcomes, not human visual inspection of those images.

## Retained failures

[Simple HTTP results](evidence/simple-results.json): decoded picture and clock passed in all six rows; captions distinguished good from missing-caption as above. MP4 seek passed; WebM seek failed for all three package locations, returning to 0 seconds.

[Controlled diagnosis](evidence/seek-diagnosis.json): two repetitions per condition in the same browser. The original WebM hash is recorded. A `Range: bytes=0-15` probe returned HTTP 200 and the entire file under Python SimpleHTTPRequestHandler, versus HTTP 206 and 16 bytes under the range-capable handler. Browser WebM requests also received 206 under that handler. Seeking changed from failure (0 seconds, seekable [0,0]) to success (4 seconds, seekable [0,6.008]) without changing media bytes. Moving WebM cues to the front alone did not fix seeking on the simple server.

Direct-file WebM seeking passed twice, but the existing external caption track failed twice. Chromium's console explicitly reported that file URLs have unique security origins. Local private filesystem prefixes in the checked-in diagnosis were replaced with `file://<FIXTURE_ROOT>`; the rest of the observations are retained. This failure is not solved by the HTTP seek fix; HTTP is a different opening route.

## Boundaries

- `canPlayType` returned `probably` for the supplied H.264 and VP9 probes; actual forced playback was tested separately. The probe codec string is not an inspection of the encoded stream's exact profile.
- A ZIP extracted and served over HTTP is not a double-click/offline pass. The direct-file diagnosis is separate and fails captions.
- Audio was muted. Audibility, intelligibility, speech production, animation/story quality, caption completeness/timing/readability, real films, other browsers and presentation devices are not tested.
- Reality Check's model-backed investigation was not run by this example. No finding here proves a fault in another project's files, the guide's historical fallback, or a teammate's host.
- No general cross-browser compatibility claim is made. Re-run the fixture on the intended viewing setup before using it as a prerequisite for real media checks.

## Reproduction and review

Follow [RUN.md](RUN.md). Inspect individual result fields: a completed script is not a passing package. Reviewers should distinguish rerunning these checks from inspecting this author's recorded JSON. Expected negative cases are teaching examples, not permission to suppress failures in a real package.
