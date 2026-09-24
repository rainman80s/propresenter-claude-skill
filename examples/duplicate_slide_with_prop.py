#!/usr/bin/env python3
"""
Worked example: duplicate a slide that also triggers a Prop (e.g. a QR code
overlay), across a list of items, correctly wired up across BOTH the
presentation file AND the separate shared Props library file -- plus the
"blank" interstitial cue that clears the prop before the next one fires.

This is the exact pattern behind a "each item's slide shows its own QR
code as an overlay" setup (small groups, sign-up links, session codes,
whatever) -- adapted from a real one built and verified against a live
ProPresenter 19 show. See references/schema-notes.md's "Props library"
section for why Props live in a separate file at all.

Read skills/propresenter/SKILL.md first.

--- Before running ---

1. Run ../setup.sh once.
2. Build ONE example by hand in ProPresenter: a slide with your real
   content, PLUS a Prop (e.g. a QR code image) wired to trigger when that
   slide's cue plays, PLUS whatever "clear the prop" cue you use before
   moving to the next item (commonly: a blank/interstitial cue with a
   CLEAR action targeting the PROP layer).
3. Copy BOTH files this touches:
   - your presentation .pro file
   - Configuration/Props (the shared library -- every presentation's Prop
     actions point into this one file by UUID)
4. Find the UUIDs of your template cue, its matching Prop cue, the
   interstitial "clear" cue, and the Prop collection you want new Props
   filed under (a quick read-only inspection script -- see SKILL.md's
   workflow section -- will print these for you).
5. Fill in CONFIG below.
"""

import csv
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
import propresenter_toolkit as pt  # noqa: E402

# ============================== CONFIG ===================================

PROTO_VERSION = "Proto7.16.2"

SOURCE_PRO = "./MyShow-COPY.pro"          # a COPY of your real presentation
SOURCE_PROPS = "./Props-COPY.bin"         # a COPY of Configuration/Props
DATA_CSV = "./data.csv"                   # columns: name, subtitle, photo_filename, qr_filename

TEMPLATE_CUE_UUID = "PUT-THE-TEMPLATE-GROUP-SLIDE-CUE-UUID-HERE"
TEMPLATE_PROP_UUID = "PUT-THE-MATCHING-PROP-CUE-UUID-HERE"
INTERSTITIAL_CUE_UUID = "PUT-THE-BLANK-CLEAR-CUE-UUID-HERE"
INSERT_AFTER_CUE_UUID = "PUT-THE-CUE-UUID-TO-INSERT-NEW-ITEMS-AFTER-HERE"
PROP_COLLECTION_NAME = "PUT-THE-PROP-COLLECTION-NAME-HERE"   # e.g. "Home Groups"

MEDIA_DIR_ABS = "/Users/you/Documents/ProPresenter/Media/Assets"
OUTPUT_PRO = "./OUTPUT-review-copy.pro"
OUTPUT_PROPS = "./OUTPUT-Props-review-copy.bin"

NAME_ELEMENT_INDEX = 0
SUBTITLE_ELEMENT_INDEX = 1
PHOTO_ELEMENT_INDEX = 2

# The text currently on the template slide -- needed so rtf_substitute can
# find-and-replace it. Print the template's rtf_data once to confirm.
OLD_NAME_TEXT_IN_TEMPLATE = "PUT THE TEMPLATE'S CURRENT NAME TEXT HERE"
OLD_SUBTITLE_TEXT_IN_TEMPLATE = "PUT THE TEMPLATE'S CURRENT SUBTITLE TEXT HERE"

ROOT_SHOW = 10  # confirm this matches ROOT_SHOW in your compiled proto's URL.LocalRelativePath.Root enum

# ===========================================================================

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pygen", PROTO_VERSION))
import presentation_pb2  # noqa: E402
import propDocument_pb2  # noqa: E402
import cue_pb2  # noqa: E402
import uuid_pb2  # noqa: E402


def main():
    with open(DATA_CSV, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows)} rows from {DATA_CSV!r}")

    # ---- 1) load + validate both real files (read-only copies) ----------
    pres = pt.load_and_verify(SOURCE_PRO, presentation_pb2.Presentation)
    propdoc = pt.load_and_verify(SOURCE_PROPS, propDocument_pb2.PropDocument)
    print(f"Presentation OK: {len(pres.cues)} cues. Props OK: {len(propdoc.cues)} prop cues.")

    cues_by_uuid = pt.cues_by_uuid(pres.cues)
    props_by_uuid = pt.cues_by_uuid(propdoc.cues)

    template_cue = cues_by_uuid[TEMPLATE_CUE_UUID]
    template_prop_cue = props_by_uuid[TEMPLATE_PROP_UUID]
    template_interstitial_cue = cues_by_uuid[INTERSTITIAL_CUE_UUID]
    collection = next(pc for pc in propdoc.prop_collections if pc.name == PROP_COLLECTION_NAME)

    # figure out the next "Prop N" number by scanning existing prop names
    existing_prop_names = [c.name for c in propdoc.cues if c.name.startswith("Prop")]
    next_prop_num = len(existing_prop_names)  # "Prop" counts as 0, "Prop 1" as 1, etc.

    name_rtf_template = None
    subtitle_rtf_template = None
    for a in template_cue.actions:
        if a.type == 11:  # PRESENTATION_SLIDE
            els = a.slide.presentation.base_slide.elements
            name_rtf_template = els[NAME_ELEMENT_INDEX].element.text.rtf_data
            subtitle_rtf_template = els[SUBTITLE_ELEMENT_INDEX].element.text.rtf_data

    new_group_cues, new_interstitial_cues, new_prop_cues = [], [], []

    for i, row in enumerate(rows):
        prop_name = "Prop" if next_prop_num + i == 0 else f"Prop {next_prop_num + i}"
        prop_uuid = pt.new_uuid()

        # ---- clone the content slide + its prop-trigger action ----------
        cue = cue_pb2.Cue()
        cue.CopyFrom(template_cue)
        cue.uuid.string = pt.new_uuid()
        cue.name = f"Generated - {row['name']}"

        slide_action = next(a for a in cue.actions if a.type == 11)
        prop_action = next(a for a in cue.actions if a.type == 6)

        slide_action.uuid.string = pt.new_uuid()
        base_slide = slide_action.slide.presentation.base_slide
        base_slide.uuid.string = pt.new_uuid()

        name_el = base_slide.elements[NAME_ELEMENT_INDEX]
        name_el.element.uuid.string = pt.new_uuid()
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
            root_show_enum_value=ROOT_SHOW,
        )
        w, h = pt.pixel_dimensions(photo_path)
        photo_el.element.fill.media.image.drawing.natural_size.width = w
        photo_el.element.fill.media.image.drawing.natural_size.height = h

        prop_action.uuid.string = pt.new_uuid()
        prop_action.prop.identification.parameter_uuid.string = prop_uuid
        prop_action.prop.identification.parameter_name = prop_name

        new_group_cues.append(cue)

        # ---- clone the interstitial "clear the prop" cue -----------------
        icue = cue_pb2.Cue()
        icue.CopyFrom(template_interstitial_cue)
        icue.uuid.string = pt.new_uuid()
        for a in icue.actions:
            a.uuid.string = pt.new_uuid()
        new_interstitial_cues.append(icue)

        # ---- clone the Prop cue in the SEPARATE Props library -----------
        pcue = cue_pb2.Cue()
        pcue.CopyFrom(template_prop_cue)
        pcue.uuid.string = prop_uuid
        pcue.name = prop_name
        p_action = pcue.actions[0]
        p_action.uuid.string = pt.new_uuid()
        p_slide = p_action.slide.prop.base_slide
        p_slide.uuid.string = pt.new_uuid()
        p_el = p_slide.elements[0]
        p_el.element.uuid.string = pt.new_uuid()
        qr_path = os.path.join(MEDIA_DIR_ABS, row["qr_filename"])
        pt.set_media_file(
            p_el.element.fill.media,
            absolute_path=qr_path,
            show_relative_path=f"Media/Assets/{row['qr_filename']}",
            root_show_enum_value=ROOT_SHOW,
        )
        qw, qh = pt.pixel_dimensions(qr_path)
        p_el.element.fill.media.image.drawing.natural_size.width = qw
        p_el.element.fill.media.image.drawing.natural_size.height = qh
        new_prop_cues.append(pcue)

    # ---- 2) splice into presentation playback order ----------------------
    for c in new_group_cues + new_interstitial_cues:
        pres.cues.append(c)

    for cue_group in pres.cue_groups:
        ids = list(cue_group.cue_identifiers)
        if not any(cid.string == INSERT_AFTER_CUE_UUID for cid in ids):
            continue
        insertion = []
        for gcue, icue in zip(new_group_cues, new_interstitial_cues):
            u1, u2 = uuid_pb2.UUID(), uuid_pb2.UUID()
            u1.string, u2.string = gcue.uuid.string, icue.uuid.string
            insertion += [u1, u2]
        new_ids = pt.insert_after(ids, INSERT_AFTER_CUE_UUID, insertion)
        del cue_group.cue_identifiers[:]
        cue_group.cue_identifiers.extend(new_ids)

    # ---- 3) register new Props in the library + its collection ----------
    for pcue in new_prop_cues:
        propdoc.cues.append(pcue)
        item = collection.items.add()
        item.prop_cue_uuid.string = pcue.uuid.string

    # ---- 4) validate + write BOTH outputs as NEW files -------------------
    pres_data = pt.verify_message(pres, presentation_pb2.Presentation)
    props_data = pt.verify_message(propdoc, propDocument_pb2.PropDocument)

    pt.save_new(OUTPUT_PRO, pres_data)
    pt.save_new(OUTPUT_PROPS, props_data)

    print(f"\nWrote {OUTPUT_PRO} ({len(pres_data)} bytes)")
    print(f"Wrote {OUTPUT_PROPS} ({len(props_data)} bytes)")
    print(
        "\nNeither of your SOURCE files was opened for writing. To actually use "
        "this: review OUTPUT_PRO in ProPresenter as a separate document, and if "
        "you're happy with it, use propresenter_toolkit.backup_and_overwrite_shared_library() "
        "to update the REAL Configuration/Props (only Props is safe to swap in-place, "
        "since it's additive; bring the new presentation cues into your real show "
        "via copy/paste inside ProPresenter itself)."
    )


if __name__ == "__main__":
    main()
