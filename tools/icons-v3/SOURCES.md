# tools/icons-v3: the desk's icon sources

The app icons of draft 3 (DN-5; Finder redrawn and the hand-drawn 16 px drawings of DN-8) and the file icons (DN-9,
with the hand-drawn 16 px text and ci of DN-12), copied byte for byte from the design's sources (draft 3,
its icons-v3 and files-v1 folders). Each row gives the folder
the file came from, a note where one is due, and its sha256, which is the sum in that folder's ASSETS.json.
`tools/svgicons.py` draws them into `user/ci/kit/icons3.ci` (app icons) and `user/ci/kit/fileicons.ci` (file
icons); `tools/svgicons.py --check` holds every file to its sum here and the modules to what it writes.

The app icons share one 64 x 64 construction with a baked two-rect shadow (MS-R1: no runtime icon shadow) and no
cadmium; the file icons are pages with a folded corner and a folder, with a baked two-layer shadow. The reference
renders by librsvg are studio-assets' `reference/daphnis-desk/icons-v3/ref_daphnis_icons_v3_proof.png`.

## Files

| file | from | sha256 |
|---|---|---|
| `ui_daphnis_file_ci.svg` | `reference/daphnis-desk/files-v1/` | `6cfeea485ef06397dae7073cfde45eb0868f046a3e6496939105e956452c23a5` |
| `ui_daphnis_file_ci_16.svg` | `reference/daphnis-desk/files-v1/` | `c30bfd2fa929e6ffb2d13647d8f88ef62eff483ca211d4cb74fc5c6e9b3cf623` |
| `ui_daphnis_file_dir.svg` | `reference/daphnis-desk/files-v1/` | `15aafc17367d247bdb4e2053e398c24c20b7285d7394752d2e134006896a8c6d` |
| `ui_daphnis_file_image.svg` | `reference/daphnis-desk/files-v1/` | `747350f527a6c6609588cf1e84ba6cb3f36871543a4fa67d7db1b9cffde53c08` |
| `ui_daphnis_file_text.svg` | `reference/daphnis-desk/files-v1/` | `8a19ed6091f02c6ff19cb1b6da7107541d5f3e0a43b1210ed6cd83d4de6c05b1` |
| `ui_daphnis_file_text_16.svg` | `reference/daphnis-desk/files-v1/` | `fdef9fe38664571798a99f71cd9368c4b427cfddad7061af394ed0ea49d65d3a` |
| `ui_daphnis_file_wad.svg` | `reference/daphnis-desk/files-v1/` | `6637dd92d8e8e63811470b1f2403bf93d40f77ced322bfff4e55efb1a7e978e5` |
| `ui_daphnis_icon_allapps.svg` | `reference/daphnis-desk/icons-v3/` | `3ae8d35bbee59c399d4eaa03809fe8409dc933c6345ebfb2bfdca33efadf1953` |
| `ui_daphnis_icon_browser.svg` | `reference/daphnis-desk/icons-v3/` | `23545005f262abdfa7fff44a34ea0910ee7756e3de5bdd3439c11cd2ed2a114f` |
| `ui_daphnis_icon_trash.svg` | `reference/daphnis-desk/icons-v3/` (draft) | `5501f2ab5c520a6dc3650ff1ecfd2cf6c86c32b1889dd54e6d0af56f9311d185` |
| `ui_daphnis_icon_trash_full.svg` | `reference/daphnis-desk/icons-v3/` (accepted: the tipped lid keeps its handle) | `c6fda8c4569d682500fa03f0676d9c3d232dde6fb8d627bb7266c49c896c9dd3` |
| `ui_daphnis_icon_calculator.svg` | `reference/daphnis-desk/icons-v3/` | `0e4b2fe854379a965d0151bc73cd417b02aef315a9a99502cf0775ac3f578a0c` |
| `ui_daphnis_icon_calculator_16.svg` | `reference/daphnis-desk/icons-v3/` | `ca351122f9bf4c0eee85a840c717355d974f324735ccb10900bfc4d7673f0743` |
| `ui_daphnis_icon_cvim.svg` | `reference/daphnis-desk/icons-v3/` | `744f5818925efb8f1b077ac976f159f97706df688e29617e6274a541fcb2fac6` |
| `ui_daphnis_icon_editor.svg` | `reference/daphnis-desk/icons-v3/` | `f37f8cc1cf372d4d12b61f62d8d5f6918c195f121e145453759dff3ac5fdb38a` |
| `ui_daphnis_icon_editor_16.svg` | `reference/daphnis-desk/icons-v3/` | `1f592b0950ea913a6c88292f089ff9eeb12a5031340e619d5eb62d78f09a2b4c` |
| `ui_daphnis_icon_fetch.svg` | `reference/daphnis-desk/icons-v3/` | `deb95b19d5c86894da2009a6fd30fb2710bcc4f43d072d8d433518d34587701c` |
| `ui_daphnis_icon_finder.svg` | `reference/daphnis-desk/icons-v3/` | `27b2806da3c804555a5c83ec6d5fb3ae520fdfeee1177983154da9af1ac8408e` |
| `ui_daphnis_icon_finder_16.svg` | `reference/daphnis-desk/icons-v3/` | `2f37a3f12301054beaea75071d1148b9e0d65ad27295b789b7c3d980d5a050e5` |
| `ui_daphnis_icon_images.svg` | `reference/daphnis-desk/icons-v3/` | `3ab6ed88f5be7dd811b299608617b54f00f46c99edf43168c40e81792b36c1b5` |
| `ui_daphnis_icon_monitor.svg` | `reference/daphnis-desk/icons-v3/` (DN-59 C Gauge) | `094e8bc7ef3884dfa234711b0fed3f5bfe9389dbe0a997ffb9b58d63cea07a53` |
| `ui_daphnis_icon_program.svg` | `reference/daphnis-desk/icons-v3/` | `1d1748068288e836778e41fbb4ce6b0bd070de2d64db833efaed3f71808b3de3` |
| `ui_daphnis_icon_program_light.svg` | `reference/daphnis-desk/icons-v3/` | `605d2b66fd771eefd845d7a30c541cd451f436021aade9235aa8c4cda30fd923` |
| `ui_daphnis_icon_reader.svg` | `reference/daphnis-desk/icons-v3/` | `d0b0bed7886c5d18f6e300ba202571896f6f2f48ec14ac4f950316b747c09eb7` |
| `ui_daphnis_icon_settings.svg` | `reference/daphnis-desk/icons-v3/` | `ae1639be3679d4e9c7f7df59605abc8547c0afa97c3de14fd781295fb4ebfa60` |
| `ui_daphnis_icon_settings_16.svg` | `reference/daphnis-desk/icons-v3/` | `35a20ef9ad93d2933d2f9e61193edb1ffe892ec47076102b316d8a3826c6d152` |
| `ui_daphnis_icon_terminal.svg` | `reference/daphnis-desk/icons-v3/` | `16a037d016c527629ea0ca65c68058de30bb081cf62c41e3e9cb881817a00728` |

## Manifest

One row an icon, in the order of the kit's index: its name, its kind (`app` into icons3.ci, `file` into
fileicons.ci), its drawing and its sizes in px, each drawn at 1x and natively at 2x (FONT-2 A). The general rule of
DN-8 and DN-12: at 16 px a hand-drawn drawing beside the source, its name with `_16` before `.svg`, replaces the
scaled drawing, at 1x and at 2x (drawn at 32 device px). No code names those files: a new `_16` file listed under
Files is taken by the next run. CVim (DN-30), Web Browser (DN-31) and Monitor (DN-59) have no hand-drawn 16:
their 16 px is the 64 unit drawing scaled. A Finder or file icon redrawn later is a new sum in Files, nothing else.

| name | kind | drawing | sizes |
|---|---|---|---|
| finder | app | `ui_daphnis_icon_finder.svg` | 16 28 32 40 48 56 64 72 80 88 |
| terminal | app | `ui_daphnis_icon_terminal.svg` | 16 28 32 40 48 56 64 72 80 88 |
| editor | app | `ui_daphnis_icon_editor.svg` | 16 28 32 40 48 56 64 72 80 88 |
| settings | app | `ui_daphnis_icon_settings.svg` | 16 28 32 40 48 56 64 72 80 88 |
| images | app | `ui_daphnis_icon_images.svg` | 16 28 32 40 48 56 64 72 80 88 |
| calculator | app | `ui_daphnis_icon_calculator.svg` | 16 28 32 40 48 56 64 72 80 88 |
| reader | app | `ui_daphnis_icon_reader.svg` | 16 28 32 40 48 56 64 72 80 88 |
| fetch | app | `ui_daphnis_icon_fetch.svg` | 16 28 32 40 48 56 64 72 80 88 |
| program | app | `ui_daphnis_icon_program.svg` | 16 28 32 40 48 56 64 72 80 88 |
| program_light | app | `ui_daphnis_icon_program_light.svg` | 16 28 32 40 48 56 64 72 80 88 |
| allapps | app | `ui_daphnis_icon_allapps.svg` | 16 28 32 40 48 56 64 72 80 88 |
| cvim | app | `ui_daphnis_icon_cvim.svg` | 16 28 32 40 48 56 64 72 80 88 |
| browser | app | `ui_daphnis_icon_browser.svg` | 16 28 32 40 48 56 64 72 80 88 |
| trash | app | `ui_daphnis_icon_trash.svg` | 16 28 32 40 48 56 64 72 80 88 |
| trash_full | app | `ui_daphnis_icon_trash_full.svg` | 16 28 32 40 48 56 64 72 80 88 |
| monitor | app | `ui_daphnis_icon_monitor.svg` | 16 28 32 40 48 56 64 72 80 88 |
| dir | file | `ui_daphnis_file_dir.svg` | 16 28 32 40 48 64 |
| text | file | `ui_daphnis_file_text.svg` | 16 28 32 40 48 64 |
| ci | file | `ui_daphnis_file_ci.svg` | 16 28 32 40 48 64 |
| image | file | `ui_daphnis_file_image.svg` | 16 28 32 40 48 64 |
| wad | file | `ui_daphnis_file_wad.svg` | 16 28 32 40 48 64 |

Sizes (DN-5): 16, 32 and 64 for the bar, lists and the plane, 80 for the All Apps picker, 72 and 56 for hover and
press; the file icons (DN-9) at 64, 32 and 16. Doom takes the Program icon; program_light is the Program icon for a
light ground, which `icons3.icon_at` picks by itself when asked for `program` on a light ground.

## At

One size and scale drawn from another source than the rule above gives: name, size, scale, source. Empty now; a row
here is how a later drawing for one size alone comes in.

| name | size | z | source |
|---|---|---|---|
