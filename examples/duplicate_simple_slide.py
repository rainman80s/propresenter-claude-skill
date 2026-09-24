#!/usr/bin/env python3
"""
Worked example: duplicate one hand-built ProPresenter slide N times, each
with different text + a different photo, from a CSV of data.

This is the pattern for things like: staff directory slides, event slides,
small-group slides, volunteer spotlight slides -- anything where you've
designed ONE slide's look by hand in ProPresenter and want it repeated
across a list of names/photos/data without doing it by hand N more times.

Read skills/propresenter/SKILL.md first. This script follows every
safeguard described there: it never opens a real ProPresenter file in
write mode, it round-trip validates before AND after editing, and it
writes its result to a brand new file for you to review in ProPresenter
yourself before bringing it into a real show.

--- Before running ---

1. Run ../setup.sh once.
2. Build ONE example slide by hand in ProPresenter with your real content
   (real text, real photo) -- this is your style template.
3. Save/export that presentation as its own .pro file (or note where your
   real show's .pro file lives -- either way, this script only ever reads
   a COPY of it).
4. Fill in the CONFIG section below:
   - PROTO_VERSION: match your ProPresenter version (see pygen/ after setup.sh)
   - SOURCE_PRO: path to the .pro file containing your template slide
   - TEMPLATE_CUE_UUID: the uuid of the cue you built by hand (open the
     file read-only with a quick inspection script to find it -- see
     skills/propresenter/SKILL.md's workflow section)
   - DATA_CSV: your list of items, one row per new slide
   - OUTPUT_PRO: where to write the result (a NEW file, never your source)
"""

import csv
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
import propresenter_toolkit as pt  # noqa: E402

# ============================== CONFIG ===================================

PROTO_VERSION = "Proto7.16.2"       # folder name under pygen/, matches your ProPresenter version
SOURCE_PRO = "./MyShow-COPY.pro"    # a COPY of your real file -- see step 3/4 above
TEMPLATE_CUE_UUID = "PUT-THE-TEMPLATE-CUE-UUID-HERE"
DATA_CSV = "./data.csv"             # columns: name, subtitle, photo_filename
MEDIA_DIR_ABS = "/Users/you/Documents/ProPresenter/Media/Assets"  # where photos live/will live
OUTPUT_PRO = "./OUTPUT-review-copy.pro"

# Index of the elements inside the template slide, in the order ProPresenter
# stores them -- inspect your real file once to confirm these indices match
# (see the inspect-slides snippet in SKILL.md's workflow section).
NAME_ELEMENT_INDEX = 0
SUBTITLE_ELEMENT_INDEX = 1
PHOTO_ELEMENT_INDEX = 2

# ===========================================================================

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pygen", PROTO_VERSION))
import presentation_pb2  # noqa: E402
import cue_pb2  # noqa: E402


def main():
    pres = pt.load_and_verify(SOURCE_PRO, presentation_pb2.Presentation)
    print(f"Loaded {SOURCE_PRO!r}: {pres.name!r}, {len(pres.cues)} cues (round-trip OK)")

    by_uuid = pt.cues_by_uuid(pres.cues)
    template_cue = by_uuid.get(TEMPLATE_CUE_UUID)
    if template_cue is None:
        raise SystemExit(f"TEMPLATE_CUE_UUID {TEMPLATE_CUE_UUID!r} not found in {SOURCE_PRO}")

    slide_action = next(a for a in template_cue.actions if a.type == 11)  # PRESENTATION_SLIDE
    template_elements = slide_action.slide.presentation.base_slide.elements

    # Extract the RTF "prefix" (everything up to the visible text) from the
    # template's name/subtitle elements, so new text keeps identical styling.
    name_rtf_template = template_elements[NAME_ELEMENT_INDEX].element.text.rtf_data
    subtitle_rtf_template = template_elements[SUBTITLE_ELEMENT_INDEX].element.text.rtf_data

    with open(DATA_CSV, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows)} rows from {DATA_CSV!r}")

    new_cues = []
    for row in rows:
        cue = cue_pb2.Cue()
        cue.CopyFrom(template_cue)
        cue.uuid.string = pt.new_uuid()
        cue.name = f"Generated - {row['name']}"

        action = cue.actions[0]
        action.uuid.string = pt.new_uuid()
        base_slide = action.slide.presentation.base_slide
        base_slide.uuid.string = pt.new_uuid()

        name_el = base_slide.elements[NAME_ELEMENT_INDEX]
        name_el.element.uuid.string = pt.new_uuid()
        # Use rtf_substitute if the template's visible text appears exactly
        # once and you know what it currently says; otherwise build the RTF
        # from a manually-extracted prefix (see SKILL.md).
        name_el.element.text.rtf_data = pt.rtf_substitute(
            name_rtf_template, OLD_NAME_TEXT_IN_TEMPLATE, row["name"]
        )

        subtitle_el = base_slide.elements[SUBTITLE_ELEMENT_INDEX]
        subtitle_el.element.uuid.string = pt.new_uuid()
        subtitle_el.element.text.rtf_data = pt.rtf_substitute(
            subtitle_rtf_template, OLD_SUBTITLE_TEXT_IN_TEMPLATE, row["subtitle"]
        )

        photo_el = base_slide.elements[PHOTO_ELEMENT_INDEX]
        photo_el.element.uuid.string = pt.new_uuid()
        photo_path = os.path.join(MEDIA_DIR_ABS, row["photo_filename"])
        pt.set_media_file(
            photo_el.element.fill.media,
            absolute_path=photo_path,
            show_relative_path=f"Media/Assets/{row['photo_filename']}",
            root_show_enum_value=10,  # ROOT_SHOW -- confirm against your compiled proto's enum
        )
        w, h = pt.pixel_dimensions(photo_path)
        photo_el.element.fill.media.image.drawing.natural_size.width = w
        photo_el.element.fill.media.image.drawing.natural_size.height = h

        new_cues.append(cue)

    for c in new_cues:
        pres.cues.append(c)

    # Append the new cues to the end of playback order in every cue group
    # that contains the template cue. Adjust this if you need a different
    # insertion point (see SKILL.md's ordering guidance).
    for cue_group in pres.cue_groups:
        ids = list(cue_group.cue_identifiers)
        if not any(cid.string == TEMPLATE_CUE_UUID for cid in ids):
            continue
        import uuid_pb2  # noqa: E402
        new_id_msgs = []
        for c in new_cues:
            u = uuid_pb2.UUID()
            u.string = c.uuid.string
            new_id_msgs.append(u)
        del cue_group.cue_identifiers[:]
        cue_group.cue_identifiers.extend(list(ids) + new_id_msgs)

    data = pt.verify_message(pres, presentation_pb2.Presentation)
    pt.save_new(OUTPUT_PRO, data)
    print(f"Wrote {OUTPUT_PRO} ({len(data)} bytes). Open it in ProPresenter to review.")
    print(f"Your source file {SOURCE_PRO!r} was never opened for writing.")


if __name__ == "__main__":
    # Fill these in based on what the template slide's text CURRENTLY says,
    # so rtf_substitute can find and replace it.
    OLD_NAME_TEXT_IN_TEMPLATE = "PUT THE TEMPLATE'S CURRENT NAME TEXT HERE"
    OLD_SUBTITLE_TEXT_IN_TEMPLATE = "PUT THE TEMPLATE'S CURRENT SUBTITLE TEXT HERE"
    main()
