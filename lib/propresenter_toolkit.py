"""
Safety-first helpers for reading and writing ProPresenter 7+ protobuf files.

This module intentionally makes the *safe* way to do something the *easy*
way. See skills/propresenter/SKILL.md for the full explanation of why each
of these exists.

Nothing in here will ever open a path in write mode that the caller marks
as a "live" file — see `save_new()` and `overwrite_shared_library()` below,
which are deliberately two different functions with two different risk
profiles.
"""

from __future__ import annotations

import datetime
import hashlib
import os
import shutil
import uuid as _uuid


class RoundTripError(RuntimeError):
    """Raised when a protobuf message doesn't survive parse->serialize->parse
    unchanged. This means the schema doesn't fully match the file — treat it
    as a hard stop, not a warning."""


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_copy(src: str, dst: str) -> str:
    """Copy src -> dst and verify the copy is byte-identical. Returns the
    sha256 of the copy. Use this instead of ever opening a real/live
    ProPresenter file directly."""
    shutil.copy2(src, dst)
    src_hash, dst_hash = sha256_of(src), sha256_of(dst)
    if src_hash != dst_hash:
        raise RoundTripError(f"copy verification failed: {src} != {dst}")
    return dst_hash


def load_and_verify(path: str, message_cls):
    """Parse `path` as `message_cls` and immediately re-serialize it,
    asserting the result is byte-identical to the original file. This is
    the mandatory first step before editing any real file's structure —
    if this raises, STOP: your proto schema doesn't fully match this file.
    """
    with open(path, "rb") as f:
        original = f.read()
    msg = message_cls()
    msg.ParseFromString(original)
    roundtrip = msg.SerializeToString()
    if roundtrip != original:
        raise RoundTripError(
            f"{path}: round-trip mismatch ({len(original)} vs {len(roundtrip)} "
            "bytes). The proto schema does not fully capture this file's "
            "structure -- do not edit it with this schema version."
        )
    return msg


def verify_message(msg, message_cls) -> bytes:
    """Serialize `msg`, re-parse those exact bytes, and confirm the
    round-trip is clean. Call this on anything you've built/edited, right
    before writing it out, as your last check. Returns the serialized
    bytes on success."""
    data = msg.SerializeToString()
    check = message_cls()
    check.ParseFromString(data)
    if check.SerializeToString() != data:
        raise RoundTripError(
            "post-edit message failed to round-trip cleanly -- refusing to write it"
        )
    return data


def save_new(path: str, data: bytes, overwrite_ok: bool = False) -> None:
    """Write `data` to a NEW file. Refuses to clobber an existing file
    unless overwrite_ok=True is explicitly passed -- and even then, this
    function is for files YOU created (like a previous draft output), not
    for the user's real ProPresenter documents. For those, see
    `overwrite_shared_library()`, which forces a backup first."""
    if os.path.exists(path) and not overwrite_ok:
        raise FileExistsError(
            f"{path} already exists. Pass overwrite_ok=True if you really "
            "mean to replace your own prior output -- never use this to "
            "overwrite a user's real ProPresenter file."
        )
    with open(path, "wb") as f:
        f.write(data)


def backup_and_overwrite_shared_library(real_path: str, new_data: bytes) -> str:
    """The ONLY sanctioned way to update a live, shared ProPresenter library
    file (e.g. Configuration/Props) in place. Always backs up the current
    real file with a timestamp first and verifies the backup is a perfect
    copy before touching the original. Returns the backup path.

    Only call this when the user has explicitly asked you to update the
    live file -- never as a default. Prefer `save_new()` to a review copy
    for anything that isn't a shared library referenced by UUID from
    elsewhere (like Props)."""
    if not os.path.exists(real_path):
        raise FileNotFoundError(real_path)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = f"{real_path}.BACKUP-{ts}"
    safe_copy(real_path, backup_path)  # raises if the backup isn't identical
    with open(real_path, "wb") as f:
        f.write(new_data)
    after_hash = sha256_of(real_path)
    expected_hash = hashlib.sha256(new_data).hexdigest()
    if after_hash != expected_hash:
        raise RoundTripError(
            f"write to {real_path} did not verify -- restore from {backup_path} immediately"
        )
    return backup_path


def new_uuid() -> str:
    """ProPresenter UUIDs are uppercase, standard-formatted."""
    return str(_uuid.uuid4()).upper()


def new_presentation_from_template(template_path: str, message_cls, name: str):
    """Load a REAL, known-working Presentation and strip it down to an empty
    shell you can build new content into -- this is the only safe way to
    start a brand-new Presentation document.

    Do NOT construct `presentation_pb2.Presentation()` from scratch. Confirmed
    by a real failure: a from-scratch Presentation was missing
    application_info/background/chord_chart/ccli/timeline (all silently
    default/absent), and even after those were restored the document still
    showed ZERO slides in ProPresenter, because a freshly-constructed
    CueGroup has an empty/default `group.uuid` -- ProPresenter appears to key
    slide-group registration off that UUID, and won't display a group that
    doesn't have a real one. The fix in both cases is the same: never build
    these wrapper messages from scratch, always clone them from a real file
    and only clear/replace the parts that actually need to change.

    This returns (presentation, cue_group) where cue_group is the template's
    OWN first CueGroup object (real group.uuid intact, cue_identifiers
    cleared) -- append new cues to `presentation.cues` and their UUIDs to
    `cue_group.cue_identifiers`, exactly as you would for any other edit.
    """
    pres = load_and_verify(template_path, message_cls)
    pres.name = name
    pres.uuid.string = new_uuid()
    del pres.cues[:]
    del pres.arrangements[:]
    pres.selected_arrangement.Clear()
    if len(pres.cue_groups) == 0:
        raise ValueError(f"{template_path} has no cue_groups to reuse -- pick a different template")
    cue_group = pres.cue_groups[0]
    del pres.cue_groups[1:]
    del cue_group.cue_identifiers[:]
    return pres, cue_group


# ---------------------------------------------------------------------------
# RTF text helpers
# ---------------------------------------------------------------------------

def rtf_escape_text(text: str) -> bytes:
    """Encode `text` for insertion into an existing RTF template's tail.
    Uses cp1252 (what real ProPresenter/Cocoa RTF declares via \\ansicpg1252)
    with \\uNNNN\\'3f fallback escapes for anything cp1252 can't represent.
    Also escapes RTF's own special characters (backslash, braces)."""
    out = bytearray()
    for ch in text:
        if ch in ("\\", "{", "}"):
            out += f"\\{ch}".encode("ascii")
            continue
        try:
            out += ch.encode("cp1252")
        except UnicodeEncodeError:
            out += f"\\u{ord(ch)}\\'3f".encode("ascii")
    return bytes(out)


def rtf_substitute(template_rtf: bytes, old_text: str, new_text: str) -> bytes:
    """Given a real rtf_data byte string extracted from a working element,
    replace the literal `old_text` (as it currently reads in that RTF, i.e.
    what you'd get back from a plain-text extraction) with `new_text`,
    preserving every font/color/paragraph control word untouched.

    This only works when `old_text`'s cp1252-encoded bytes appear exactly
    once in the template (which is true for the "one visible run of text at
    the end of the RTF" pattern ProPresenter's own editor produces). For
    anything more complex, extract the template's header/tail manually
    (see SKILL.md) instead of relying on this helper.
    """
    old_bytes = rtf_escape_text(old_text)
    new_bytes = rtf_escape_text(new_text)
    count = template_rtf.count(old_bytes)
    if count != 1:
        raise ValueError(
            f"expected exactly one occurrence of {old_text!r} in the RTF "
            f"template, found {count} -- build the RTF manually instead "
            "(see SKILL.md's RTF section)"
        )
    return template_rtf.replace(old_bytes, new_bytes, 1)


def build_rtf_from_template(header_and_tail_before_text: bytes, text: str) -> bytes:
    """For the common case where you've extracted everything up to and
    including the last control word before the visible text (e.g. ending in
    `\\CocoaLigature0 `), pass that prefix plus the new text; this appends
    the escaped text and the closing brace."""
    return header_and_tail_before_text + rtf_escape_text(text) + b"}"


def extract_rtf_prefix(template_rtf: bytes, marker: bytes = b"\\cf2 ") -> bytes:
    """Extract everything up to and including `marker` (default: the color
    switch that immediately precedes visible text in real Cocoa RTF) from a
    placeholder's existing rtf_data. Use this -- instead of rtf_substitute --
    whenever the placeholder's sample text is more than one plain run (e.g.
    a multi-verse sample with inline \\super verse-number superscripts, seen
    in a real Theme's "Text" placeholder). Pass the result to
    build_rtf_from_template() with your own plain text; you get the theme's
    exact font/size/color without needing to replicate whatever multi-run
    structure the sample happened to use."""
    idx = template_rtf.find(marker)
    if idx == -1:
        raise ValueError(f"marker {marker!r} not found in template RTF -- inspect it by eye instead")
    return template_rtf[: idx + len(marker)]


def build_rtf_with_underline(prefix: bytes, before: str, underlined: str, after: str = "") -> bytes:
    """Build RTF text with one substring underlined, using \\ul ... \\ulnone.
    Matches a real church's documented convention ("underlining used for
    emphasis instead of bolding" on live slides) -- when content gives you
    bolded/emphasized text, render the emphasis as underline in the RTF
    rather than dropping it or guessing at bold codes. `prefix` should come
    from extract_rtf_prefix() (or a manually-extracted "...\\CocoaLigature0 "
    style prefix)."""
    return (
        prefix
        + rtf_escape_text(before)
        + b"\\CocoaLigature0 \\ul "
        + rtf_escape_text(underlined)
        + b"\\ulnone "
        + rtf_escape_text(after)
        + b"}"
    )


# ---------------------------------------------------------------------------
# Media helpers
# ---------------------------------------------------------------------------

def set_media_file(media, absolute_path: str, show_relative_path: str, root_show_enum_value: int) -> None:
    """Populate BOTH url fields a Media message needs (see SKILL.md's "two
    URL gotcha"). `root_show_enum_value` is the integer value of
    URL.LocalRelativePath.Root.ROOT_SHOW from the compiled proto for your
    ProPresenter version (pass it in rather than hardcoding, since enum
    values should be read from the actual generated module you're using)."""
    file_url = f"file://{absolute_path}" if not absolute_path.startswith("file://") else absolute_path
    media.uuid.string = new_uuid()
    media.url.absolute_string = file_url
    media.url.local.root = root_show_enum_value
    media.url.local.path = show_relative_path
    media.image.file.local_url.absolute_string = file_url
    media.image.file.local_url.local.root = root_show_enum_value
    media.image.file.local_url.local.path = show_relative_path


ROOT_CURRENT_RESOURCE = 12  # URL.LocalRelativePath.Root -- same value across schema versions checked so far


def fix_cross_document_media(base_slide) -> int:
    """Clear any ROOT_CURRENT_RESOURCE-relative media path on a Slide cloned
    from a DIFFERENT document (most commonly: a Theme's own background/decor
    images, cloned as part of reusing one of its layouts).

    Confirmed by real failure: a Theme's own image element (e.g. a
    background texture) has media.url.local.root = ROOT_CURRENT_RESOURCE,
    meaning "relative to whatever document currently owns this resource."
    That resolves fine inside the Theme itself, but once the Slide is cloned
    into a DIFFERENT Presentation, ProPresenter tries to resolve the same
    relative path against the new document instead -- which has no matching
    folder -- and shows a broken-image icon, even though the element's
    absolute_string is completely correct and the file genuinely exists
    right where it always was. Clearing the relative `local` field (on both
    media.url and media.image.file.local_url) leaves nothing to resolve
    except the working absolute path. This does not move, copy, or touch the
    actual image file -- it stays wherever it already lives.

    Call this on every Slide you clone from a Theme (or from any file other
    than the one you're building into) before adding it to your output.
    Returns the number of media references fixed, for your own logging."""
    fixed = 0
    for el in base_slide.elements:
        if el.element.fill.WhichOneof("FillType") != "media":
            continue
        media = el.element.fill.media
        for url in (media.url, media.image.file.local_url):
            if url.WhichOneof("RelativeFilePath") == "local" and url.local.root == ROOT_CURRENT_RESOURCE:
                url.ClearField("local")
                fixed += 1
    return fixed


def pixel_dimensions(image_path: str) -> tuple[int, int]:
    """Get (width, height) in pixels. Uses macOS `sips`; if you're not on
    macOS, swap this for Pillow or another image library -- but get the
    *real* dimensions rather than guessing, since ProPresenter uses this
    for crop/fit math (DrawingProperties.natural_size)."""
    import subprocess

    out = subprocess.check_output(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", image_path],
        text=True,
    )
    width = height = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("pixelWidth:"):
            width = int(line.split(":")[1].strip())
        elif line.startswith("pixelHeight:"):
            height = int(line.split(":")[1].strip())
    if width is None or height is None:
        raise RuntimeError(f"could not read pixel dimensions of {image_path}")
    return width, height


# ---------------------------------------------------------------------------
# Cue ordering helpers
# ---------------------------------------------------------------------------

def cues_by_uuid(cues) -> dict:
    return {c.uuid.string: c for c in cues}


def playback_order(cue_group, uuid_to_cue: dict) -> list:
    """Resolve a CueGroup's cue_identifiers against a {uuid: cue} map to get
    the actual sequence a human sees in the editor / that plays live. Never
    assume `presentation.cues` list order matches this."""
    ordered = []
    for cid in cue_group.cue_identifiers:
        cue = uuid_to_cue.get(cid.string)
        if cue is None:
            raise KeyError(f"cue_identifiers references missing uuid {cid.string}")
        ordered.append(cue)
    return ordered


def insert_after(id_list, after_uuid: str, new_uuids: list):
    """Return a new list of UUID protobuf messages with `new_uuids`
    (strings) spliced in immediately after the entry matching `after_uuid`.
    Does not mutate `id_list` in place."""
    idx = next(i for i, cid in enumerate(id_list) if cid.string == after_uuid)
    # caller supplies the UUID message type via new_uuids being pre-built
    # UUID() messages, to avoid this module depending on a specific
    # compiled proto package.
    return list(id_list[: idx + 1]) + list(new_uuids) + list(id_list[idx + 1 :])
