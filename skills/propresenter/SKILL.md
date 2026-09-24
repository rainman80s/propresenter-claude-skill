---
name: propresenter
description: Safely read, generate, and bulk-edit ProPresenter 7+ files (.pro, .probundle, .proworkspace, and the Props/Themes/Playlists library files) by editing the underlying Protocol Buffers directly. Use this whenever the user wants to build/duplicate ProPresenter slides in bulk, generate new slides from a Theme plus raw content (e.g. text pasted from a Notion page/doc/spreadsheet, matched to a Theme's named placeholders), create Props (including QR-code-as-Prop setups), template a slide across a list of names/photos/data, or otherwise script something in their ProPresenter show/library rather than clicking through the UI by hand. Also use it if the user mentions ProPresenter, Themes, Props, .pro/.probundle files, or asks "can Claude edit my ProPresenter file."
---

# ProPresenter File Editing (via Protocol Buffers)

ProPresenter 7 and later store *everything* — presentations, Props, Themes,
Playlists, the Workspace — as **binary Protocol Buffer messages**, not XML,
not JSON, not anything human-editable by hand. This skill exists because
that fact makes naive editing (regex on the file, guessing at bytes)
actively dangerous: a malformed write can silently corrupt a file that a
church depends on for Sunday morning. Every instruction below exists to
prevent that.

Read this whole file before touching a real ProPresenter file. The
safeguards are not optional extras — they are the actual point of this
skill.

## The one rule that matters most

**Never write to a file the user's ProPresenter installation is actually
using until it has been proven, by round-trip test, that you fully
understand its structure — and even then, prefer writing to a *new* file
over overwriting a real one.**

Concretely, this means for every file you touch:

1. Copy it into a scratch/working location first. Never open the original
   file path in "write" mode, ever, for any reason.
2. Checksum the copy against the original (`shasum -a 256`) so you can
   prove later that the user's real file was never modified by your
   session.
3. **Read-before-write validation**: parse the copy with the generated
   protobuf bindings, then immediately re-serialize it with no changes and
   compare the bytes to the original. They must be byte-identical. If they
   are not, STOP — it means the proto schema you're using doesn't fully
   match this file's structure (wrong ProPresenter version, or a field the
   schema doesn't know about yet), and any edit you make risks silently
   dropping data. Fall back to a non-destructive approach (e.g. producing
   new media/slides as images instead of editing the document) and tell
   the user why.
4. **Write-then-validate**: after building your modified message, serialize
   it, then immediately re-parse those exact bytes and confirm the
   resulting structure looks right (right cue count, right text, right
   media paths). Do this before telling the user anything is done.
5. **Never overwrite the user's live show file.** Write your result to a
   new file (e.g. `MyShow - REVIEW COPY.pro`) and have the user open it as
   a *separate* document in ProPresenter to check it visually. The
   officially-supported way to bring reviewed content into a real show is
   for the user to copy/paste cues between documents inside ProPresenter's
   own UI — not for you to overwrite their working file.
6. **Shared library files are the one exception**, and only when the user
   explicitly asks you to update the live one (e.g. `Configuration/Props`,
   which many presentations reference by UUID, so a "review copy" isn't
   useful on its own). Even then: make a timestamped backup first
   (`Props.BACKUP-<timestamp>`), tell the user exactly where it is, and
   only ever make *additive* changes to these shared files (add new
   entries; don't remove or rewrite existing ones) unless explicitly told
   otherwise.
7. State clearly, in plain language, exactly which real files (if any) you
   touched, and where the backups are, every time.

If you cannot get a clean round-trip on the user's real file, say so
plainly rather than proceeding on a best-effort guess. A visible "I
couldn't safely parse this" beats a silent corruption discovered on Sunday
morning.

## One-time environment setup

Run `setup.sh` from this repo once per machine/session:

```bash
./setup.sh
```

This:
- Creates a local Python virtualenv (`.venv`) so nothing pollutes the
  user's system Python.
- Installs `protobuf` + `grpcio-tools` (official Google packages — this is
  the one dependency install this skill needs; it's a well-known package,
  not a random script, but still confirm with the user before running it
  if you're in an environment that gates package installs).
- Fetches the community-maintained, reverse-engineered proto schema from
  [`greyshirtguy/ProPresenter7-Proto`](https://github.com/greyshirtguy/ProPresenter7-Proto)
  as a git submodule under `proto/`. This is **not an official Renewed
  Vision project** — it's reverse-engineered by the community, which is
  exactly why the round-trip validation step above is non-negotiable: the
  schema can be incomplete or lag behind the newest ProPresenter release.
- Compiles Python bindings for every vendored schema version (currently
  `7.16`, `7.16.2`, and `19beta`) into `pygen/<version>/`.

**Ask the user their ProPresenter version first** (Help → About
ProPresenter in the app). Pick the matching (or closest) compiled schema
version. If none match closely, tell the user their version may not be
covered yet and proceed with extra caution (i.e. lean harder on round-trip
validation, and prefer read-only inspection over writing).

## Where ProPresenter's files actually live (macOS)

Not hidden — a normal visible folder:

```
~/Documents/ProPresenter/
├── Media/Assets/            # every imported media file, referenced by path
├── Libraries/               # presentation libraries (songs, sermons, etc.)
├── Playlists/                # playlists
├── Themes/                   # theme documents
└── Configuration/
    ├── Props                # <- ALL Props, one shared binary file, no extension
    ├── Workspace
    ├── Groups
    └── ...
```

A `.pro` file is one Presentation document. A `.probundle` is a zip
(`unzip -l` it) containing the `.pro` file plus copies of every media file
it references, named by their *original absolute path* — useful for
portability/inspection, since it tells you exactly which media a
presentation depends on without touching the live Media/Assets folder.

## The protobuf structure you need to know

Load `references/schema-notes.md` in this repo for the full write-up. The
essentials:

- **`Presentation`** (top-level message in a `.pro` file) has `cues`
  (flat list) and `cue_groups` (defines actual playback order — always
  read order from `cue_groups[].cue_identifiers`, never assume `cues`
  list order matches what you see in the ProPresenter editor).
- **`Cue.actions`** is where everything happens. Check `action.type`
  against the `ActionType` enum (`PRESENTATION_SLIDE = 11`, `PROP = 6`,
  `CLEAR = 5`, `AUDIENCE_LOOK = 18`, etc.) and read the matching
  `oneof ActionTypeData` field.
- **A slide's visual content** lives at
  `action.slide.presentation.base_slide.elements[]`, each with `.bounds`
  (position/size), `.fill` (`color` / `gradient` / `media`), and `.text`
  (RTF bytes in `rtf_data`).
- **Media is referenced by file URL, never embedded.** Every
  `Graphics.Element.fill.media` needs **two** URL fields kept in sync:
  `media.url` and `media.image.file.local_url` — both need the same
  `absolute_string` (`file:///Users/.../Media/Assets/name.png`) and
  `local.path` (`Media/Assets/name.png` with `root = ROOT_SHOW`). Also set
  `media.image.drawing.natural_size` to the image's *actual* pixel
  dimensions (`sips -g pixelWidth -g pixelHeight <file>` on macOS) — a
  wrong value here causes ProPresenter to mis-crop/scale it.
- **Props live in a separate shared library file**
  (`Configuration/Props`, parsed as `PropDocument`), not inside the
  presentation. A presentation's `PROP` action only stores a
  `CollectionElementType` (uuid + name) *pointing at* a Prop cue defined in
  that other file. This is the mechanism behind things like "QR code
  overlay per slide" setups — see `examples/duplicate_slide_with_prop.py`
  for the full worked pattern (find the two real UUIDs referenced by an
  existing working slide+prop pair, decode both files, clone the prop cue
  N times with new UUIDs pointing at new QR images, register each new UUID
  in the right `prop_collections[].items`, then reference those new UUIDs
  from new `PROP` actions in the presentation).
- **Text is RTF, not plain protobuf strings.** Never hand-author RTF from
  scratch. Instead: find an existing real text element with the styling
  you want, extract its exact `rtf_data` bytes, and only swap the literal
  text at the end while preserving every font-table/color-table/paragraph
  control word verbatim. `lib/propresenter_toolkit.py` has `rtf_encode()`
  for this — pass it a *template* RTF (from a real element) plus the new
  text, and it substitutes safely, cp1252-encoding the new text with
  `\uNNNN\'3f` fallback escapes for any character cp1252 can't represent.
- **"Clone a known-good message and mutate only what must change" beats
  "build a message from scratch" every time.** Every field you don't
  explicitly know about stays correct automatically. Use `CopyFrom()` on
  a real template `Cue`/`Slide`/`Action`, then only touch UUIDs (always
  regenerate — never reuse an existing UUID) and the specific
  text/media/identification fields that need new values.
- **Auto-fit long text** by setting
  `element.text.scale_behavior = SCALE_BEHAVIOR_SCALE_FONT_DOWN` (value
  `2`) on generated text elements when the input data has variable-length
  strings (e.g. names of very different lengths) — this lets ProPresenter
  shrink the font at render time instead of the text overflowing its box,
  which you can't reliably predict without real font metrics.

## Suggested workflow for "here's a Theme, here's some text, build the slide(s)"

This is the workflow that needs **no existing hand-built slide at all** —
just a Theme the user already has, and content from wherever (pasted from
a Notion page, a doc, an email, a spreadsheet row, typed directly in
chat).

1. Copy the Theme file (`Themes/<Name>/Theme`), round-trip validate it as
   `Template.Document`.
2. List its `slides[].name` values and show them to the user (or match
   against what they asked for, e.g. "the Speaker Title layout") — these
   are the named layouts visible in ProPresenter's own theme picker.
3. Clone the chosen `Template.Slide.base_slide`.
4. Match the user's content to elements **by `Graphics.Element.name`**
   (e.g. a layout's `"Name 1"` element is where a person's name goes,
   `"Title 1"` is their role/title) — inspect the layout once to learn its
   placeholder names, then map fields to them. Don't guess by position.
5. Substitute text using each placeholder's own existing `rtf_data` as the
   template (see the RTF section above) so the Theme's exact styling is
   preserved with zero hand-authored RTF.
6. Wrap the result in a new `Cue` + `PRESENTATION_SLIDE` action, add it to
   a `Presentation` document (a fresh one, or the user's real show — as a
   new file either way, per the safeguards above).
7. Round-trip validate, write to a new file, report what you built.

See `examples/build_slides_from_theme_and_text.py` for the full worked
version of this.

## Suggested workflow for "duplicate this slide N times with different data"

This is the most common request this skill handles (a church wants one
slide's style/layout applied across a list — group names, staff bios,
event dates, whatever).

1. Get the user's actual `.pro` file (or `.probundle` — unzip it) and a
   `.probundle`/direct copy of the Props library if Props are involved.
   Always copy first, checksum, round-trip validate (see above).
2. Find the 1-2 real slides the user already built by hand as templates —
   don't guess at layout; read their actual bounds/fonts/RTF/media
   structure.
3. Get the user's data (CSV, spreadsheet, pasted list — whatever they
   have) for the N items to generate.
4. For each item: clone the template `Cue` (and its Prop cue, if any),
   regenerate every UUID, substitute only the text/media that changes,
   using the real pixel dimensions of any new media files.
5. Splice the new cues into `cue_groups[].cue_identifiers` in the right
   playback position — check what interstitial/"blank" cues exist between
   items in the template and replicate that pattern too, not just the
   content slide.
6. Round-trip validate the final output, write it to a new file, and
   report exactly what you built and what (if anything) touched the user's
   real files.
7. Let the user review in ProPresenter before it goes anywhere near a live
   show.

See `examples/` for two complete, runnable worked examples.
