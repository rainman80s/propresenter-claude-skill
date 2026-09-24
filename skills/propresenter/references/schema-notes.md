# ProPresenter protobuf schema notes

These notes were reverse-engineered by inspecting real ProPresenter 19
files against the community proto definitions in
[`greyshirtguy/ProPresenter7-Proto`](https://github.com/greyshirtguy/ProPresenter7-Proto).
They are a map, not a spec — when in doubt, decode a real file and read
its actual field values rather than trusting this document blindly.

## Top-level documents

| File | Root message | Notes |
|---|---|---|
| `*.pro` | `rv.data.Presentation` | One presentation/show document |
| `*.proplaylist` | `rv.data.PlaylistDocument` | A playlist |
| `*.proworkspace` | `rv.data.Workspace` | App-wide workspace config |
| `Configuration/Props` (no extension) | `rv.data.PropDocument` | **Shared** Props library, referenced by every presentation |

## `Presentation`

```
Presentation {
  string name;
  UUID uuid;
  repeated Cue cues;                    // flat list, NOT necessarily playback order
  repeated CueGroup cue_groups;         // playback order lives here
  ...
}

CueGroup {
  Group group;                          // name/color metadata
  repeated UUID cue_identifiers;        // <-- the REAL order; look this up, not `cues`
}
```

Always resolve `cue_groups[].cue_identifiers` against a `{uuid: cue}` map
built from `presentation.cues` to get the actual sequence a human sees in
the ProPresenter editor / that plays back live.

## `Cue` and `Action`

```
Cue {
  UUID uuid;
  string name;                          // just a label, purely cosmetic
  repeated Action actions;
  bool isEnabled;
}

Action {
  UUID uuid;
  string name;
  Label label;                          // label.text shows in the editor, e.g. "CLICK ME"
  ActionType type;                      // see enum below
  oneof ActionTypeData { ... }          // the field matching `type` is populated
}
```

Key `ActionType` values seen in practice:

| Value | Enum | oneof field | What it does |
|---|---|---|---|
| 5 | `CLEAR` | `clear` | `clear.target_layer` (enum incl. `PROP`, `SLIDE`, `ALL`, ...) clears that output layer |
| 6 | `PROP` | `prop` | Triggers/clears a Prop; `prop.identification` (`CollectionElementType`: uuid + name) points at a Prop `Cue` in the separate Props library file |
| 11 | `PRESENTATION_SLIDE` | `slide` | `slide.presentation` is a `PresentationSlide` wrapping the actual visual `Slide` |
| 15 | `PROP_SLIDE` | `slide` (via `SlideType.prop`) | Used *inside* the Props library file for each Prop's own visual content |
| 18 | `AUDIENCE_LOOK` | `audience_look` | Switches the live "Look" (background/output config); `identification` again uuid+name |

`Action.PropType`:
```
PropType {
  CollectionElementType identification;   // uuid + name of the target Prop cue
  oneof TriggerType {
    PropTrigger trigger;                  // fire it
    PropClear clear;                      // clear it
  }
}
```
To trigger a prop, set the oneof to `trigger` (an otherwise-empty message —
in Python: `action.prop.trigger.SetInParent()`).

`Action.ClearType`:
```
ClearType {
  ClearTargetLayer target_layer;  // ALL=0, AUDIO=1, BACKGROUND=2, LIVE_VIDEO=3,
                                    // PROP=4, SLIDE=5, LOGO=6, MESSAGES=7, AUDIO_EFFECTS=8
}
```

## `Slide` / visual content

```
PresentationSlide {
  Slide base_slide;
  Notes notes;
  ...
}

Slide {
  repeated Element elements;
  Graphics.Size size;                  // e.g. 1920x880 or 1920x1080 depending on the show
  UUID uuid;
}

Slide.Element {
  Graphics.Element element;            // the actual visual node
  ...
}

Graphics.Element {
  UUID uuid;
  string name;
  Graphics.Rect bounds;                // { origin {x,y}, size {width,height} }
  Graphics.Fill fill;                  // oneof: color / gradient / media / backgroundEffect
  Graphics.Text text;                  // present on every element, even non-text ones (empty RTF)
  ...
}

Graphics.Fill {
  oneof FillType {
    Color color;
    Graphics.Gradient gradient;
    Media media;
    Graphics.BackgroundEffect backgroundEffect;
  }
}
```

## `Media` — the two-URL gotcha

```
Media {
  UUID uuid;
  URL url;                                        // <-- URL #1
  oneof TypeProperties {
    ImageTypeProperties image;
    VideoTypeProperties video;
    ...
  }
}

ImageTypeProperties {
  DrawingProperties drawing;   // scale_behavior, scale_alignment, natural_size, crop, ...
  FileProperties file;
}

FileProperties {
  URL local_url;                                  // <-- URL #2, must match URL #1
}
```

**Both `media.url` and `media.image.file.local_url` must be set and kept
identical** — every real file inspected had both populated with the same
`absolute_string` and `local` (root + relative path). Missing one may
still open fine in some ProPresenter versions but don't rely on that.

```
URL {
  oneof Storage {
    string absolute_string;    // "file:///Users/you/Documents/ProPresenter/Media/Assets/x.png"
    string relative_path;
  }
  oneof RelativeFilePath {
    LocalRelativePath local;   // { Root root; string path; }  e.g. root=ROOT_SHOW, path="Media/Assets/x.png"
    ExternalRelativePath external;
  }
}
```

`DrawingProperties.natural_size` should be set to the image file's actual
pixel width/height (`sips -g pixelWidth -g pixelHeight file.png` on
macOS) — this is what ProPresenter uses for fill/fit crop math. Getting it
wrong doesn't crash anything but can visibly mis-crop the image.

`scale_behavior` on `DrawingProperties`: `FIT=0`, `FILL=1` (crop to fill,
most common for photo/QR elements), `STRETCH=2`, `CUSTOM=3`.

## Text / RTF

```
Graphics.Text {
  Graphics.Text.Attributes attributes;
  bytes rtf_data;                      // the actual text, RTF-encoded
  VerticalAlignment vertical_alignment;
  ScaleBehavior scale_behavior;        // NONE=0, ADJUST_CONTAINER_HEIGHT=1,
                                        // SCALE_FONT_DOWN=2, SCALE_FONT_UP=3, SCALE_FONT_UP_DOWN=4
  ...
}
```

Real `rtf_data` observed (macOS Cocoa RTF, `\cocoartf2822`) looks like:

```
{\rtf1\ansi\ansicpg1252\cocoartf2822
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fnil\fcharset0 SomeFontName;}
{\colortbl;\red255\green255\blue255;\red255\green255\blue255;}
{\*\expandedcolortbl;;\csgray\c100000;}
\deftab1680
\pard\pardeftab1680\sl192\slmult1\pardirnatural\partightenfactor0

\f0\fs210 \cf2 \CocoaLigature0 The actual visible text here}
```

Treat everything except the literal trailing text as an opaque template
copied verbatim from a real element with the styling you want. The text
itself is `\ansicpg1252`-encoded (Windows-1252) — encode each character as
cp1252 where possible; for any character cp1252 can't represent, use the
RTF unicode-escape fallback `\uNNNN\'3f` (decimal code point, then a
literal `?` as the "best guess" fallback byte, per the RTF spec). Verified
against real accented characters (e.g. "í", the en-dash "–") — both are
representable directly in cp1252 (0xED and 0x96 respectively), so most
Western text needs no fallback at all.

## Props library (`Configuration/Props`, parsed as `PropDocument`)

```
PropDocument {
  repeated Cue cues;                         // one Cue per Prop, each a self-contained visual
  repeated PropCollection prop_collections;  // just organizes Props into named folders in the UI
}

PropCollection {
  UUID uuid;
  string name;                               // e.g. "Home Groups", "Default Collection"
  repeated Item items;                       // Item { UUID prop_cue_uuid; }
  bool single_prop_enabled;                  // true = only one Prop from this folder live at once
}
```

Each Prop `Cue` has exactly one `Action` of type `PROP_SLIDE` (15), whose
`slide.prop` is a `PropSlide` wrapping a `base_slide` — structurally
identical to a presentation slide's `Slide`, just usually much simpler
(often a single image element, e.g. one QR code).

**To add a new Prop:** clone an existing Prop `Cue` from this file,
regenerate its UUID, swap its image element's media (both URL fields +
natural_size), and add a new `Item` with that new UUID to the right
`PropCollection.items`. Then, in the *presentation* file, add a `PROP`
action whose `identification.parameter_uuid`/`parameter_name` match the
new Prop cue.

## Themes (`Themes/<Name>/Theme`, parsed as `Template.Document`)

A Theme folder on disk looks like:

```
Themes/<Name>/
├── Theme            # binary, root message rv.data.Template.Document
└── Assets/          # media used by the theme's own template slides
```

```
Template.Document {
  ApplicationInfo application_info;
  repeated Template.Slide slides;
}

Template.Slide {
  Slide base_slide;      // same Slide message as everywhere else
  string name;            // human label, e.g. "SLIDES - Speaker Title"
  repeated Action actions;
}
```

Verified against a real Theme file: round-trips byte-identical, and its
`slides` are exactly the set of named layouts you see in ProPresenter's
theme picker (e.g. `"Series"`, `"SLIDES/KEY - General Text"`,
`"SLIDES - Speaker Title"`, `"KEY - 2 Speakers"`, ...). Each layout's
elements are already-styled **named placeholders** — e.g. the "Speaker
Title" layout has elements literally named `"Title 1"` and `"Name 1"` in
`Graphics.Element.name`.

**This is the key to the "drop in text from a Notion page (or anywhere)
and reference a Theme, and it just works" workflow:**

1. Load the Theme's `Template.Document` (copy first, round-trip validate,
   as always).
2. Find the `Template.Slide` whose `.name` matches the layout you want
   (list all of them and show the user their names if unsure which fits).
3. Clone its `.base_slide` — this is a normal `Slide` message, so
   everything you already know about elements/bounds/fill/text applies
   unchanged.
4. Match your incoming content fields to elements **by `element.name`**
   (e.g. content's "speaker name" -> the element literally named `"Name
   1"`), not by position — placeholder names are stable and meaningful,
   position is not.
5. Substitute each matched element's `text.rtf_data` using the *existing*
   RTF in that placeholder as the template (see the RTF section above) —
   this preserves the Theme's exact font/size/color choices with zero
   guessing.
6. Wrap the filled slide in a new `Cue`/`Action` (type 11,
   `PRESENTATION_SLIDE`) the same way you would for any other new slide,
   and add it to a `Presentation` document.

This means Claude does not need a hand-built example slide to work from at
all when a Theme is available — the Theme *is* the style source of truth.
Given unstructured text (e.g. pasted from a Notion page, an email, a
spreadsheet row) plus "use the Theme called X, layout Y," Claude can
produce a correctly-styled new slide directly. See
`examples/build_slides_from_theme_and_text.py`.

## Practical gotchas encountered in the wild

- A `.probundle` exported by ProPresenter may extract its inner `.pro`
  file with `0000` (no) permissions. `chmod 644` your own copy before
  trying to read it — this is a quirk of the export, not a sign anything
  is wrong with the file.
- `cue.name` and `action.name`/`action.label.text` are purely cosmetic —
  don't rely on them for logic, but *do* set sensible names on cues you
  generate so a human skimming the ProPresenter editor later can tell
  what's what.
- ProPresenter's own numbering/naming conventions for repeated items (like
  Props) are simple increments — "Prop", "Prop 1", "Prop 2", ... — match
  that convention when generating more, so the result looks hand-made.
