# ProPresenter + Claude skill

Give Claude the ability to safely read, generate, and bulk-edit
[ProPresenter](https://renewedvision.com/propresenter/) 7+ files — the
software most churches use to run slides on Sunday — without clicking
through the UI by hand, and without the risk of quietly corrupting a show
file a volunteer team depends on.

This came out of a real request: a church needed one hand-built "Home
Group" slide (photo + name + meeting time + a QR code overlay) turned into
eleven, each with different content. Doing that safely meant actually
understanding ProPresenter's file format — which turns out to be
[Protocol Buffers](https://protobuf.dev/), not XML or JSON — and building
real safeguards around editing it. This repo packages that up as a
[Claude Code skill](https://docs.claude.com/en/docs/claude-code) so it
doesn't have to be re-derived from scratch every time.

## What it can do

- **Duplicate a hand-built slide across a list of data** (names, photos,
  dates — anything you have as a CSV/spreadsheet), preserving its exact
  styling.
- **Generate brand-new slides directly from a Theme** plus raw text —
  paste content from a Notion page, a doc, an email, wherever — and Claude
  matches it to the Theme's own named placeholders (e.g. "Name 1", "Title
  1"), so the result is styled exactly like everything else built from
  that Theme.
- **Build and wire up Props** (the mechanism behind per-slide QR code
  overlays, among other things), including the separate shared Props
  library file and the "clear the prop before the next one" cue pattern.
- All of it **without ever risking your real show file** — see Safety
  model below.

## Quick start

```bash
git clone https://github.com/rainman80s/propresenter-claude-skill.git
cd propresenter-claude-skill
./setup.sh
```

Then, in a Claude Code session in this directory, just ask for what you
want — e.g. "I built one slide for our staff directory in ProPresenter,
here's the rest of the staff as a spreadsheet, can you build the other 20
slides in the same style?" Claude will follow `skills/propresenter/SKILL.md`
automatically.

If you're not using Claude Code, the `examples/` scripts are fully
standalone, runnable Python and can be adapted by hand.

## Safety model

ProPresenter's files are binary — there is no way to "peek" at one in a
text editor to sanity-check an edit before it's too late. So the whole
design here is built around never trusting a single edit blindly:

1. **Never open a real/live file in write mode.** Everything works off a
   copy, checksummed against the original.
2. **Round-trip validation, both directions.** Before editing: parse the
   real file, re-serialize it unchanged, and require the result to be
   byte-identical to the original — if it isn't, the schema doesn't fully
   match this file and editing stops right there. After editing: the same
   check on the new content, before it's ever written to disk.
3. **Clone-and-mutate, never build-from-scratch.** New slides/cues start
   as an exact copy of something real and working; only the specific
   fields that need to change are touched. Everything else — fonts,
   colors, layout, obscure fields nobody thought to document — comes along
   for free, correctly.
4. **New files, not overwrites.** Output goes to a new file for you to
   open and review in ProPresenter yourself. The one exception is a
   handful of shared library files (like Props) that other documents
   reference by ID — those get a timestamped backup before any in-place
   update, and only ever additive changes.

Full detail: [`skills/propresenter/SKILL.md`](skills/propresenter/SKILL.md).

## How the file format works (short version)

ProPresenter 7 switched from XML to Protocol Buffers. This repo vendors
the community-maintained, reverse-engineered schema from
[`greyshirtguy/ProPresenter7-Proto`](https://github.com/greyshirtguy/ProPresenter7-Proto)
(not an official Renewed Vision project — which is exactly why the
round-trip validation above matters) and compiles Python bindings for it
locally via `setup.sh`. Full schema notes, including the specific gotchas
found by testing against real files (dual media URL fields, the Props
library mechanism, RTF text encoding), live in
[`skills/propresenter/references/schema-notes.md`](skills/propresenter/references/schema-notes.md).

## Repo layout

```
skills/propresenter/SKILL.md          # the skill itself (what Claude reads)
skills/propresenter/references/       # detailed schema notes
lib/propresenter_toolkit.py           # reusable safety-first helper functions
examples/                             # three complete, runnable worked examples
setup.sh                              # one-time environment setup
```

## Contributing

Found a real ProPresenter file that doesn't round-trip cleanly against the
vendored schema? That almost certainly means either a newer ProPresenter
version added a field the community schema doesn't have yet, or a schema
version mismatch — open an issue with (redacted, if needed) details rather
than working around it silently.

## License

Code in this repo (everything outside `proto/`, which is a submodule with
[its own license](https://github.com/greyshirtguy/ProPresenter7-Proto)) is
MIT — see [`LICENSE`](LICENSE).
