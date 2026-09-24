#!/usr/bin/env python3
"""
Worked example: build brand-new ProPresenter slides directly from a Theme
plus raw content -- no hand-built example slide required.

This is the "drop in text from a Notion page/doc/spreadsheet and reference
a Theme, and it just works" pattern. It works because a Theme file
(Themes/<Name>/Theme, parsed as Template.Document) contains a set of
named, already-styled layouts, and each layout's elements are themselves
named placeholders (e.g. "Name 1", "Title 1", "SOURCE", "TEXT"). Match
your content to those names and the Theme's exact styling comes along for
free -- no guessing at fonts/colors/positions.

Read skills/propresenter/SKILL.md first, especially the Themes section in
references/schema-notes.md.

--- Before running ---

1. Run ../setup.sh once.
2. Pick which Theme + which of its named layouts you want
   (STEP_A below shows you how to list them).
3. Fill in CONFIG, including CONTENT_ITEMS -- in real use, this is where
   you'd drop in whatever the user gave you (pasted Notion text, a CSV,
   a spreadsheet export, etc.), turned into a list of dicts keyed by the
   layout's placeholder element names.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
import propresenter_toolkit as pt  # noqa: E402

# ============================== CONFIG ===================================

PROTO_VERSION = "Proto7.16.2"
THEME_FILE = "/Users/you/Documents/ProPresenter/Themes/One Table/Theme"  # read-only source
LAYOUT_NAME = "SLIDES - Speaker Title"   # must match a Template.Slide.name exactly

# One dict per slide you want to generate. Keys must match the layout's
# placeholder element names exactly (see STEP_A's printed list below).
# In a real Claude session, this is where content extracted from wherever
# the user gave it to you (a Notion page, pasted text, a spreadsheet) ends
# up, already split into per-placeholder fields.
CONTENT_ITEMS = [
    {"Title 1": "Lead Pastor", "Name 1": "Jane Smith"},
    {"Title 1": "Worship Pastor", "Name 1": "Alex Rivera"},
]

OUTPUT_PRO = "./OUTPUT-from-theme.pro"

# ===========================================================================

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pygen", PROTO_VERSION))
import template_pb2  # noqa: E402
import presentation_pb2  # noqa: E402
import cue_pb2  # noqa: E402


def main():
    theme = pt.load_and_verify(THEME_FILE, template_pb2.Template.Document)
    print(f"Loaded theme {THEME_FILE!r}: {len(theme.slides)} layouts")

    # ---- STEP A: discover layouts + their placeholder names -------------
    # Run this once (or whenever unsure) to see what's available. Comment
    # the `return` out to continue past discovery once you know what you want.
    print("\nAvailable layouts:")
    for s in theme.slides:
        names = [el.element.name for el in s.base_slide.elements if el.element.name]
        print(f"  {s.name!r}: placeholders = {names}")

    layout = next((s for s in theme.slides if s.name == LAYOUT_NAME), None)
    if layout is None:
        raise SystemExit(f"Layout {LAYOUT_NAME!r} not found in this theme.")

    elements_by_name = {
        el.element.name: el for el in layout.base_slide.elements if el.element.name
    }
    print(f"\nUsing layout {LAYOUT_NAME!r} with placeholders: {list(elements_by_name)}")

    # ---- STEP B: build one new Cue per content item ----------------------
    pres = presentation_pb2.Presentation()
    pres.name = "Generated from Theme"
    pres.uuid.string = pt.new_uuid()
    cue_group = pres.cue_groups.add()

    for item in CONTENT_ITEMS:
        base_slide = layout.base_slide.__class__()
        base_slide.CopyFrom(layout.base_slide)
        base_slide.uuid.string = pt.new_uuid()

        for placeholder_name, new_text in item.items():
            el = next(
                (e for e in base_slide.elements if e.element.name == placeholder_name),
                None,
            )
            if el is None:
                print(f"  [!] no placeholder named {placeholder_name!r} in this layout, skipping")
                continue
            el.element.uuid.string = pt.new_uuid()
            template_rtf = el.element.text.rtf_data
            # The layout's placeholder text is itself the "old text" to
            # replace -- extract it once (print template_rtf to see it) if
            # rtf_substitute can't find a unique match, and build the RTF
            # from the known prefix instead (see SKILL.md's RTF section).
            try:
                old_text = extract_placeholder_plaintext(template_rtf)
                el.element.text.rtf_data = pt.rtf_substitute(template_rtf, old_text, new_text)
            except ValueError:
                print(
                    f"  [!] couldn't cleanly substitute into {placeholder_name!r}; "
                    "build its RTF manually from the template (see SKILL.md)"
                )

        cue = cue_pb2.Cue()
        cue.uuid.string = pt.new_uuid()
        cue.name = f"Generated - {item.get('Name 1', item.get('Title 1', 'slide'))}"
        cue.isEnabled = True
        action = cue.actions.add()
        action.uuid.string = pt.new_uuid()
        action.type = 11  # ACTION_TYPE_PRESENTATION_SLIDE
        action.slide.presentation.base_slide.CopyFrom(base_slide)

        pres.cues.append(cue)
        cid = cue_group.cue_identifiers.add()
        cid.string = cue.uuid.string

    data = pt.verify_message(pres, presentation_pb2.Presentation)
    pt.save_new(OUTPUT_PRO, data)
    print(f"\nWrote {OUTPUT_PRO} ({len(data)} bytes, {len(pres.cues)} slides). "
          "Open it in ProPresenter to review.")


def extract_placeholder_plaintext(rtf_data: bytes) -> str:
    """Best-effort extraction of the single visible text run at the end of
    a simple RTF blob, for use as the `old_text` argument to
    rtf_substitute(). Real placeholder text does NOT always end in
    \\CocoaLigature0 (verified against a real theme: some runs end in
    plain \\cf2, others in \\kerning.../\\CocoaLigature0) so this finds
    the LAST RTF control word anywhere in the blob and takes everything
    after it, up to the closing brace, as the visible text. Works for the
    common single-run placeholder text ProPresenter's own editor produces;
    for anything more complex (multiple text runs, inline formatting
    changes), extract the real text by eye instead of trusting this
    blindly."""
    import re

    text = rtf_data.decode("cp1252", errors="strict")
    if text.endswith("}"):
        text = text[:-1]
    matches = list(re.finditer(r"\\[A-Za-z]+-?\d*", text))
    if not matches:
        raise ValueError("no RTF control words found -- unexpected shape")
    tail = text[matches[-1].end():]
    return tail.lstrip(" ").strip()


if __name__ == "__main__":
    main()
