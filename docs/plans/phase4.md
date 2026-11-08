# Phase 4 Plan: Photos and Scans

**Status: gate wording agreed by the owner, 8 November 2026,** with the real photo set changed to fit what the owner has (Stage 4.0, "The owner's answers"). One question on the real set's ground truth is still open (end of this plan). Drafted from the solution design (sections 2.6, 4.1, 4.2, 5.2 and 6), the requirements (IN-3, IN-5, ACC-3, OP-3), `docs/notes/phase2-report.md` and its known limits, `docs/notes/inspector-spec.md` (Types C and D), `docs/notes/raster-lines-spec.md` and `docs/notes/raster-labels-spec.md`. Plain headings and lists only. Model suggestions follow the earlier plans: Opus for design and judgement, Sonnet for implementation, escalate to Opus after two or three failed attempts. Phase 3 (braille) is parked until after this phase.

## Goal and gate

Goal: read photos and scans of printed music (Type D) to the accuracy ACC-3 asks, at least 93 to 95 percent of notes "in reasonable conditions", including open-book spreads, with the music separated from text blocks, pictures, the surface the book rests on and the centre of the spread (IN-3). A large share of users will be blind people photographing paper scores with a phone, who cannot see what the camera sees. So the converter must also **tell the user what is wrong with a photo** (part of the page cut off, too dark, blurred, too far away, two pages, upside down) in words, so they can take a better one. The solution design estimates 8 to 12 weeks.

ACC-3 leaves three things open: what "reasonable conditions" are, whether the target is 93 or 95, and what the photos are. **Agreed wording** (8 November 2026):

1. **Real photos, with ground truth.** Photos the owner takes with their phone (Stage 4.2) of printed music whose notes are known: pages from library music books whose pieces have a public-domain MusicXML edition, and, if the owner can print at the library, pages from the generated corpus. Phone scanning apps stand in for a flatbed scanner, which the owner does not have. A development photo set to work on, and a sealed check photo set scored only at milestones and at the gate.
2. **"Reasonable conditions" are defined by the capture check.** A photo is in reasonable conditions when the converter's own capture check (Stage 4.3) accepts it: the whole music area in the frame, staff lines sharp enough to measure, light enough to read, a staff space of at least about 8 pixels, and any curve or angle within limits the check states. The gate reports what share of real photos the check refuses, and that share must be small (proposed: no more than 1 in 5 of the photos taken by following the photo guide), or the check is just hiding the hard cases.
3. **95 percent of notes on scans and on flat photos; 93 percent on open-book and angled photos**, on the accepted photos of the check photo set, over all engravers.
4. **Synthetic photo sets reported, not gated.** The development and check sets with camera-style distortions added (Stage 4.1) are reported at mild, moderate and hard levels, with the clean 200 dpi figures beside them.
5. **No loss on clean input.** The vector and clean raster figures from the Phase 2 gate do not fall by more than 0.2 points.
6. **Reported, not gated:** ACC-4 on photos (flagged share and recall), structure, markings, lyrics and chord symbols, and speed against the 60 second target (OP-3).

Why these choices:

- **Real books, as users will photograph them.** Library music books give real paper, real bindings, real editions and real open-book curves, photographed by a blind user with no sighted help, which is exactly the use case. Their ground truth is a separate edition of the same piece, so it can differ from the printed page in small editorial ways (ornaments, cautionary accidentals, a repeat written out); such pairs are scored like the engraver-input pairs, with differences the printed page does not show set aside as the owner agrees, as in Phase 2. Corpus pages printed at the library, if possible, add pairs whose ground truth is exact. 50 to 100 images is enough for evaluation (design section 5.2), because the training data is synthetic.
- **The capture check as the definition.** "Reasonable conditions" otherwise means whatever the photographer happened to do. Tying it to a check the converter runs means the user is told when a photo is outside the conditions the accuracy figure covers, which is what a blind user needs, and the gate cannot quietly exclude hard photos because the refused share is reported.
- **Two targets.** The requirement's range fits two kinds of input: a flat page or a scan should lose little against the clean 97 percent; a curved, angled spread loses more.
- **Synthetic sets for the work loop.** Real photos are few and slow to make. Synthetic distortion of the 1,764 development pairs gives large figures and exact labels for every change, as the raster sets did in Phase 2. They are a guide, not the gate, because synthetic distortion is never quite real.

## What Phase 2 showed that shapes this plan

- **The raster path is strong on clean images:** 98.4 to 98.7 percent of notes at 300 and 200 dpi, with both engines combined. Phase 4's main job is to turn a photo into something close to a clean page, then reuse that path, rather than build a new reader.
- **It is weaker exactly where photos are hard:**
  - 150 dpi: half a point below 200 dpi in notes; LilyPond 93.5 percent; hairpins 70 percent. A distant phone photo or a two-page spread is nearer 150 dpi.
  - Black and white: Verovio falls to 84.4 percent, probably because its thin lines break up when the page is cut to one bit. Uneven light and a fixed threshold do the same to any engraver.
  - Ink is any pixel darker than 170 (`raster-lines-spec.md`). A shadow or a dim corner breaks that.
  - Tilt is corrected only within 2 degrees, and only as a single angle for the whole page. A photo's lines curve and converge.
- **The one real scan failed:** the Liszt "Carousel" file in the commercial sample found no staves. It is the first thing to look at, though it may be an older engraving (Phase 5).
- **The inspector's Type D test** (tilt, dark border, uneven background) is provisional and was written for the survey.
- **`omr convert` reads each image file as its own score.** A piece photographed as several pages needs the photos read as one score in order (IN-5).
- **The detector was trained on clean variations only** (`raster-labels-spec.md`: blur, JPEG, noise, black and white). Camera distortions were left to this phase.
- **Engine 2 (homr) was trained in part on camera-distorted staves,** and Camera-PrIMuS (CC BY 4.0) and Camera-GrandStaff (MIT) are in the licence register as usable. It may help more on photos than on clean pages, as Stage 2.7 expected.

## Rules for the whole phase

As in Phase 2:

- **An estimate before the bulk of each stage:** Claude sessions, the length of each long run and whether it runs overnight, CPU workers and GPU use, disk. Recorded in `phase4-progress.md` with actuals at the end of the stage.
- **CPU jobs use the shared worker pool, training uses the GPU,** one run at a time, and no evaluations alongside a training run.
- **The check sets stay sealed,** both the synthetic check photo set and the real check photo set.
- **Every fix needs a test.** Never edit `src` while a run is going; long runs use a frozen copy of the code; every run is pausable (`continue.txt`) and resumable.
- **No loss on clean input.** Every change to shared code is checked on the clean raster regression set and the vector regression set before it is committed.
- **Photos are personal.** The owner's photos may show their home, hands or desk. They stay on the corpus drive, never in the repository, and only derived figures are published. Test images in the repository are synthetic.

## Stage 4.0: Decisions and a first look at real photos

**Model: Opus.**

- **Gate wording.** Ask the owner to agree or change the wording above, including the two targets and the refused-share limit.
- **The owner's answers (8 November 2026):**
  - The owner has a phone only, an iPhone 13 mini: no printer, no scanner. iPhones save HEIC by default, which `omr convert` does not read yet, so HEIC support comes early (Stage 4.8 brings it forward if the pilot photos are HEIC). The phone's camera is 12 megapixels.
  - The owner will borrow music books from their local library and photograph pages from them. No sighted helper.
  - The owner has Be My Eyes, Seeing AI and Scribe Me, but has not used them for photographing music. The photo guide (Stage 4.2) works out how they can help.
  - Work goes ahead without waiting for the photos.
- **A pilot of real photos, when the owner has them,** not blocking anything: about ten photos of three or four library pages, taken as the owner would in real use (book open flat on a table, held open, a single page and a spread). Run today's `omr convert` on them, and write down what fails and where (orientation, page found, tilt, staves found, notes). Without ground truth this still shows which steps fail, and it checks that the synthetic distortions of Stage 4.1 look like real ones. The order of Stages 4.3 to 4.6 is revisited when the pilot is in.
- **The Liszt scan.** Find why no staves were found, and whether it is a modern print (Phase 4) or an older engraving (Phase 5).
- **Tool and model survey, with licences** (entered in the licence register before use):
  - classical tools in OpenCV and scikit-image for page edges, perspective, background flattening and thresholding (Sauvola, Otsu);
  - learned page-flattening models (UVDoc, DocTr, DewarpNet and any newer ones): licence of code and weights, size, CPU speed, and whether they run through ONNX Runtime;
  - small page or layout detectors (the YOLO family, already used, or RT-DETR);
  - HEIC reading (for example pillow-heif) and its licence;
  - camera-distortion training data already in the register (Camera-PrIMuS, Camera-GrandStaff).
- **Scope.** Confirm with the owner: older engravings stay in Phase 5 (IN-4); handwritten music is out of scope; percussion and tablature follow REC-9.

Done when: the gate wording is agreed (done), the tools are chosen with their licences entered, and the Liszt scan is explained. The pilot is read whenever its photos arrive, and its faults are listed in `phase4-progress.md`.

## Stage 4.1: Synthetic photos

**Model: Opus for the distortion model, Sonnet for the generator.** Builds on `scripts/make_raster_set.py` and the training-data generator of Stage 2.1.

- **A distortion generator,** `src/omr/corpus/camera.py`, that turns a clean rendered page into a photo-like one, step by step, each at a chosen strength:
  - the page placed on a background (desk, cloth, a second page, a hand at the edge), with the page edge visible or cut off;
  - perspective (the phone not square to the page) and rotation, including 90 and 180 degrees;
  - curl (a cylinder-like bend, strongest near the spine) and an open-book spread with a centre gutter and its shadow;
  - uneven light: a gradient, a lamp's bright spot, a hand or phone shadow, colour cast;
  - camera effects: defocus blur, a little motion blur, noise in the dark areas, JPEG at phone quality, phone-style sharpening and noise reduction;
  - resolution: a staff space from about 24 down to about 8 pixels;
  - paper: show-through from the other side, a faint texture, slight yellowing.
- **Labels move with the page.** Every distortion is a known geometric map, so the symbol boxes and the lines from the vector reader are carried through it exactly, and the ground truth MusicXML is unchanged.
- **Synthetic photo sets** at three levels (mild, moderate, hard), for the regression, development and check sets: `regression-photo-mild` and so on under `generated/raster` on the corpus drive. The check versions are made and sealed. Disk: perhaps 3 to 6 GB for the development set across the three levels, at phone resolution and JPEG.
- **Measure today's reader on them** before any Phase 4 code: notes, structure and staves found at each level. This is the starting line, and it shows which distortion costs most.

Done when: the generator makes all three levels for the three sets, the label carry-through is checked by numbers (as in Stage 2.1), and today's figures are recorded at each level.

## Stage 4.2: Real photos and scans

**Model: Sonnet for the scripts, Opus for the protocol.** Needs the owner's time, so it starts as soon as Stage 4.0 has the answers.

- **Which books.** The owner borrows library books and photographs pieces from them. Claude gives a short list of what to look for, for spread across REC-10 and for ground truth: public-domain pieces in modern prints (composers who died more than 70 years ago, in an edition set in the last few decades rather than a reprint of old plates, which are Phase 5): hymn and carol books, song albums for voice and piano, piano albums (Bach, Mozart, Beethoven, Schubert, Chopin, Schumann), folk and fiddle tune books, choral collections, easy instrumental books. The owner tells Claude the book's title and the pieces photographed, by voice note, typed list or a photo of the contents page; Claude looks for each piece's MusicXML in PDMX, OpenScore, CPDL and Mutopia.
- **Ground truth from another edition.** A piece found in those sources is matched to the photos bar by bar with the harness, after the reader has read them; differences the page does not show (an ornament written out, a cautionary accidental, an editorial slur, a different number of verses) are listed for the owner's decision, as the LilyPond faults were in Phase 2. A piece with no MusicXML to be found is still useful, reported by unflagged bars and by what the capture check and the page steps found, as the commercial files were.
- **Corpus pages printed at the library,** if the library offers printing: Claude writes a print list (a single PDF of about 20 to 40 pages from public-domain development and check scores, across engravers and textures) for the owner to print and photograph at home. These have exact ground truth and show how far the edition differences move the figures.
- **The photo guide,** written for a blind photographer, tried by the owner in the pilot and revised from what happens: how to lay a book open on a table and hold it flat, how far to hold the phone (about the length of a forearm above the page), how to centre it, where the light should be, holding still, one photo per page or per spread, and a slow count before moving on. Then how each app the owner has can help, to be tried in the pilot, since Claude cannot test them:
  - **Seeing AI** reads documents and, while framing, says which edges of the page it cannot see; whether it saves or shares the photo it takes is to check.
  - **The iPhone's own document scanner** (in the Notes and Files apps) finds a page's edges, crops and flattens it, and can capture by itself when the page is steady; its result stands in for a scan.
  - **Be My AI** (in Be My Eyes) can be asked about a photo just taken: "Is the whole page in the photo? Is it sharp? Is any part in shadow?"
  - **A Be My Eyes volunteer** can guide the framing live, which is sighted help on request if the owner wants it for a few photos.
  - Scribe Me is checked for anything it adds.
  The converter's own capture check (Stage 4.3) is the final word: the guide ends with running `omr convert` and retaking any photo it refuses. The guide becomes part of the user documentation.
- **Conditions,** as many as a session allows, each page more than once:
  - book open on a table, phone held level above it, single page and two-page spread;
  - book held open by hand;
  - phone held at an angle;
  - dim or uneven light (one lamp, a window to one side);
  - the iPhone document scanner, as the scan condition.
- **Getting the photos to Claude.** The owner copies them to a folder on the corpus drive (`E:/OMAIRCorpus/sources/photos/<book>`), keeping the phone's file names and original files (HEIC or JPEG, with their orientation tags). A short text file per book gives the title and the pieces in the order photographed. The photos are private, may show copyrighted editions, and never go into the repository (C-4).
- **The sets on the corpus drive:** `generated/photo/development` and `generated/photo/check`, each with an index giving the piece, its ground truth (if any), the condition and the photo files, read by `omr evaluate` like any other set. Photos are split between the two sets by book, so the check set holds books never looked at during the work. A photo of a spread or a partial page is scored against the bars it shows.
- **Real scans without ground truth,** reported by unflagged bars: the Liszt scan, and IMSLP scans of modern prints if some are found.

Done when: both photo sets exist with indexes, every photo with ground truth is matched to its piece, and today's reader has been run on the development photos.

## Stage 4.3: Finding the page, and the capture check

**Model: Opus for the design, Sonnet for the code.**

- **Orientation.** Honour the phone's orientation tag (EXIF). Then find the staff lines' direction to correct a page on its side, and use clefs and noteheads (which are not symmetric) to tell upright from upside down.
- **Page and spread.** Find the paper against its background (the paper is usually the largest bright area with four corners, or two pages with a gutter). Split a spread at the gutter into left and right pages, read in that order. Where the page edge is out of frame, work from the staff area instead.
- **The music area.** The staves found decide the music area; this also guards against a page edge found wrongly.
- **The capture check,** `src/omr/raster/capture.py`, run on every image before reading. It says in words what is wrong, where, and what to try, for example:
  - "The bottom of the page is cut off: the last staff runs off the edge of the photo. Move the phone back or down a little."
  - "The photo is blurred: the staff lines are not sharp. Hold the phone still and let it focus."
  - "The page is too small in the photo: a staff space is 6 pixels. Hold the phone closer."
  - "The left side of the page is much darker than the right. Turn so the light falls evenly."
  - "This looks like two pages; they will be read as the left page, then the right."
  Every message is one line, says what was found in measurable terms, and suggests one action. The check decides whether a photo is in reasonable conditions (gate item 2), and its findings go at the top of the confidence report. The thresholds are set on the synthetic sets, where the true conditions are known, and then checked on the real photos.
- **Inspector.** The Type C and D split in `inspector-spec.md` is revised with what this stage measures, so the converter knows when page preparation is needed. A clean page image must never go through page preparation and lose accuracy.

Done when: orientation, page and spread finding are right on every synthetic regression photo and every real development photo where a sighted check is not needed (judged by staves found and notes read), and the capture check's messages are agreed with the owner, who reads them as a user would.

## Stage 4.4: Flattening the page

**Model: Opus.** The step that matters most.

- **Perspective first.** From the page corners, or from the staff lines where corners are not seen, map the page to a flat rectangle.
- **Then the curve, from the staff lines.** Staff lines must be straight, level and evenly spaced, which no text document offers. Trace each staff line as a curve across the page (a sweep across the columns, following the line from the staff's middle outwards), then fit a smooth map that makes every staff line straight and every staff evenly spaced, and resample the image through it. Gaps between staves are filled by the map's smoothness; text above and below follows the nearest staff.
- **A learned flattener as a second method,** if the survey found one with a usable licence and CPU speed: compare it with the staff-line method on the synthetic sets, and use whichever is better, or the learned one first and the staff lines to finish.
- **Measure flatness by numbers:** after flattening, how far each staff line strays from a straight level line, in staff spaces, and how even the staff spaces are. On synthetic pages the true map is known, so the remaining error can be measured exactly.
- **Carry the map.** Keep the map from the photo to the flattened page, so the report can still say where things are, and so the self-check (Stage 2.8) compares against the flattened page.

Done when: on the moderate synthetic development set, staff lines after flattening stay within 0.1 staff spaces of straight on at least 95 percent of staves, and note accuracy on the moderate set is within a few points of the clean 200 dpi figure (the exact figure set after Stage 4.1).

## Stage 4.5: Light, contrast and low resolution

**Model: Opus for the design, Sonnet for the code.**

- **Even out the background** before anything else: estimate the paper's brightness across the page (a large blur or closing of the image) and divide it out, so a shadow or a dim corner becomes white paper again. Then set the ink level from the page itself rather than the fixed 170, keeping greyscale for the readers, which read greyscale better than black and white.
- **Show-through and paper texture:** faint ink from the other side of the paper must not become symbols. Test on the synthetic show-through pages.
- **The black and white weakness** from Phase 2 (Verovio at 84 percent): find whether thin lines break when cut to one bit, and fix it here, because scans are often black and white.
- **Low resolution.** A distant photo or a spread gives staff spaces of 8 to 12 pixels. Try enlarging the flattened page to a staff space the detector reads well (the Phase 2 render-scale test found the range it was trained on), and compare the time it costs.
- **Measure** on the synthetic light and resolution distortions, and on the real dim-light photos.

Done when: on the synthetic sets, the light distortions cost no more than half a point beyond the same pages without them, and the clean black and white regression figure for Verovio is within 2 points of greyscale.

## Stage 4.6: Music, text and background

**Model: Opus for the design, Sonnet for the code.**

- **Keep the music and the text that belongs to it,** and drop the rest: a book's printed text, pictures, a hand, the desk, the next page's edge, page numbers.
- **Start with rules:** the staves found define the systems; text within a set distance of a system (titles, tempo, lyrics, chord symbols, dynamics) is kept, as on clean pages; ink far from any system is ignored. Measure on synthetic pages with text blocks and pictures added, and on the real photos.
- **A small learned layout detector only if the rules fall short,** trained as the design describes, on composites of rendered music on page and desk backgrounds with text blocks. YOLO nano, as the symbol detector; a training run of about a day.
- **OCR on photos:** the text reader (Stage 2.5) on flattened, evened pages. Measure lyrics, chord symbols and words on the synthetic sets beside the clean figures.

Done when: on the synthetic sets with text blocks and pictures, no false staff or part is found, and the notes are within half a point of the same pages without them.

## Stage 4.7: Training the engines on camera-style pages

**Model: Sonnet to train and run, Opus to read the results.**

- **What is left after preparation.** Train on pages that have been distorted (Stage 4.1) and then prepared (Stages 4.3 to 4.5), so the detector learns what a prepared photo really looks like: slight remaining curve, softer edges, uneven ink, JPEG, low resolution. Not raw photos, which the preparation removes.
- **Detector fine-tune** from the Phase 2 weights, with the clean training data mixed in so clean pages do not get worse. The same model size and settings as Stage 2.3; one experiment run (under a day) then a full run (1.5 to 2 days). Score it on its own, as `check_detector.py` does, on clean and photo pages.
- **The detector faults parked in Stage 2.9** (collision rests, augmentation dots, time-signature digits; `raster-triage.md`) are added to this training run, since a run is being made anyway.
- **Engine 2:** measure it on prepared photo pages first. Fine-tune it (with the encoder frozen, as in Stage 2.6) on prepared photo staves, and on Camera-GrandStaff and Camera-PrIMuS if they help, only if it falls behind Engine 1 there or the combination gains from it.
- **ONNX export and INT8,** as before; CPU time a page recorded.

Done when: the retrained detector is no worse on the clean raster development set and better on the synthetic photo sets, and Engine 2's photo figures are recorded with the decision on fine-tuning it.

## Stage 4.8: Several photos as one score, and the report for photos

**Model: Sonnet, Opus to review the wording.**

- **Several images, one score (IN-5).** `omr convert page1.jpg page2.jpg page3.jpg --out piece` (or a folder of photos, read in name order, or a multi-page TIFF or PDF of photos) reads the photos as one score, with bar numbers, parts and repeats continuing across them, as a multi-page PDF does today. A spread counts as two pages.
- **HEIC and other phone formats,** if the owner's phone needs them.
- **The report for photos:** the capture check's findings first, then the summary, with each flag located by photo and page as well as system and bar ("Photo 2, right-hand page, system 3, bar 14"). Bars on a part of the page the check found doubtful (blurred, dark, strongly curved) get lower confidence.
- **Flag rules on photos:** check that ACC-4's rules still find the errors on photos (`check_flags.py` on the photo sets) and adjust their precision figures for photos, as was done for images in Phase 2.

Done when: a piece photographed as several photos converts to one score with continuous bars, and the report gives photo, page, system and bar for every flag.

## Stage 4.9: Accuracy push

**Model: Opus for triage, Sonnet for implementation, tests and runs.** As in Stage 2.9.

- **Triage the photo penalty.** Extend `scripts/triage_raster.py` to read each photo pair in steps (the clean page; the photo prepared with the true map; the photo prepared by the converter) so each error is put down to page finding, flattening, light, layout, or the engines on prepared pages. Write the ranking in `docs/notes/photo-triage.md`.
- **The work loop:** take the top cause, fix it with a test, run the synthetic development photos, re-check the clean regression sets, then the real development photos at the end of each session. Full synthetic and real development runs after large fixes.
- **Grow the confidence rules alongside,** as in every earlier phase.

Done when: the gate figures are met on the development photo set, or the owner stops the stage.

## Stage 4.10: CI, speed and the gate review

**Model: Opus.**

- **CI:** a photo job on the synthetic regression photo set at the moderate level (made in the job, since the generator is in the repository), Engine 1 alone, with a floor, alongside the clean raster job once the detector release is published.
- **Speed:** seconds a photo on the CPU alone, one at a time, with page preparation shown on its own, against the 60 second target (OP-3).
- **Gate runs:** the real development and check photo sets, the synthetic development and check sets at each level, and the clean raster and vector sets (no loss).
- Write `docs/notes/phase4-report.md` and ask the owner for sign-off. Update the photo guide in the user documentation, the inspector spec, and the design and requirements where they changed.

Done when: the gate (as agreed) is met and the report is signed off.

## Order and dependencies

1. Stage 4.0 first, with the real-photo pilot early in it, because it decides where the work is.
2. Stage 4.1 (synthetic photos) straight away. Stage 4.2 (real photos) whenever the owner has library books to photograph; nothing before Stage 4.9 waits for it, though the pilot photos are wanted before Stage 4.4 settles its method.
3. Stages 4.3, 4.4 and 4.5 in that order, each measured on the synthetic sets as it lands. They are the core of the phase.
4. Stage 4.6 alongside 4.5.
5. Stage 4.7 once preparation is stable enough that its output will not change much, because a training run takes days. Training runs overnight while the CPU work waits.
6. Stage 4.8 can start any time after 4.3.
7. Stage 4.9, then Stage 4.10.

## Rough effort, for the stage estimates

First guesses, to be replaced by each stage's estimate.

- Stage 4.0: 1 to 2 sessions, plus the owner's time for the pilot photos.
- Stage 4.1: 2 to 3 sessions; generating the synthetic sets a few hours overnight.
- Stage 4.2: 1 to 2 sessions of scripts, plus the owner's printing and photographing (perhaps two or three sittings of an hour or two).
- Stages 4.3 to 4.5: 6 to 10 sessions together.
- Stage 4.6: 2 to 4 sessions, more if a layout detector must be trained (about a day's GPU run).
- Stage 4.7: 2 to 3 sessions, with a 1-day and a 2-day training run.
- Stage 4.8: 2 to 3 sessions.
- Stage 4.9: 4 to 8 sessions, as the owner decides.
- Stage 4.10: 1 to 2 sessions, with gate runs of perhaps a day.
- Disk: the synthetic sets and training data perhaps 20 to 40 GB on the corpus drive, which has about 500 GB free. Nothing large on C:.

## Risks specific to Phase 4

- **Synthetic photos are not real photos.** Accuracy on them may be better than on real ones. The real photo sets are the gate, and the pilot checks the synthetic distortions against real ones early.
- **Too few real photos.** 60 to 100 pages, each in a few conditions, gives a few hundred images; a single bad photo session could skew them. The conditions are spread across sittings, and figures are reported by condition.
- **Ground truth from another edition is not exact.** Editorial differences count as errors until the owner sets them aside, which lowers the figure and takes the owner's time. Corpus pages printed at the library, if possible, give exact pairs to compare with; library books whose pieces have no MusicXML are reported without note figures.
- **The library's books may be mostly old plates or copyrighted.** Old plates are Phase 5 and are reported apart; copyrighted editions are fine for private testing but their photos stay on the corpus drive.
- **The capture check could hide hard cases.** The refused share is reported and limited in the gate.
- **The owner cannot see whether a photo is good.** That is the use case, not a problem to work round: the capture check and the photo guide are tested by the owner taking the photos.
- **Flattening can make things worse.** A wrong map bends straight lines. Flattening is applied only where the staff lines show a curve, and the clean sets guard against loss.
- **Learned flatteners may have unusable licences or be too slow on the CPU.** The staff-line method needs no model.
- **Retraining could cost clean accuracy.** Clean data stays in the training mix; the clean sets are checked before a new model is adopted.
- **Speed:** flattening and enlarging add time to a raster path already at 18 seconds a page. Measured from Stage 4.4 onwards; a dense spread may pass 60 seconds.
- **Older engravings creep in.** Many scans on IMSLP are of old plates, which are Phase 5. Real scans are sorted into modern print and older engraving, and only modern print counts here.

## Open question for the owner

1. Does your library offer printing? If so, printing about 20 to 40 corpus pages there would give photos with exact ground truth beside the library books. If not, the real set is the library books alone.
