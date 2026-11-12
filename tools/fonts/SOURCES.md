# Bundled fonts: sources

FONT-1 (l, 2026-11-10 02:45Z; `docs/specs/2026-11-07-k-kit2.md` section 3e): Inter for chrome, JetBrains Mono for the
terminal and mono fields. The files are copied unchanged from the upstream release zips, the same bytes as
pennyleans/studio-assets `vendor/fonts/` on `l/daphnis-fonts` (`d27f614`). Both are OFL-1.1; neither license names a
Reserved Font Name. The coverage tables the kit draws are written from these files by an offline tool (F3).

| file | family, version, weight | sha256 |
| --- | --- | --- |
| `inter/Inter-Regular.ttf` | Inter 4.001, 400 | `40d692fce188e4471e2b3cba937be967878f631ad3ebbbdcd587687c7ebe0c82` |
| `inter/Inter-Medium.ttf` | Inter 4.001, 500 | `97ad806f526e41546d46365bb3a393145f75b7b1568913db74549ad8b8dba872` |
| `inter/Inter-SemiBold.ttf` | Inter 4.001, 600 | `78a843fade9d4612a5567302fb595b56976eb5fcebf4fea5a5912d638bafcde3` |
| `inter/LICENSE.txt` | Inter's copyright line and OFL-1.1 | `262481e844521b326f5ecd053e59b98c8b2da78c8ee1bdbb6e8174305e54935a` |
| `jetbrains-mono/JetBrainsMono-Regular.ttf` | JetBrains Mono 2.304, 400 | `a0bf60ef0f83c5ed4d7a75d45838548b1f6873372dfac88f71804491898d138f` |
| `jetbrains-mono/JetBrainsMono-SemiBold.ttf` | JetBrains Mono 2.304, 600 | `1b3bfa1ed5665a4ce3f9feb68d2d4e40e70bf8b4b7d9a3edd418f321b4e166a0` |
| `jetbrains-mono/OFL.txt` | JetBrains Mono's copyright line and OFL-1.1 | `30f0c136e3c88e422d0791acd97238870f9054a9729bc34cf2ff0d4ed8cac4ad` |

Upstream:

- Inter: `https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip`, zip sha256
  `9883fdd4a49d4fb66bd8177ba6625ef9a64aa45899767dde3d36aa425756b11e`, files from `extras/ttf/` and `LICENSE.txt`.
- JetBrains Mono: `https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip`,
  zip sha256 `6f6376c6ed2960ea8a963cd7387ec9d76e3f629125bc33d1fdcd7eb7012f7bbf`, files from `fonts/ttf/` and `OFL.txt`.

Coverage: JetBrains Mono maps every code point the terminal draws (ASCII, U+00A0 to U+00FF, the quotes, dashes,
euro, U+2500 to U+257F, U+FFFD). Inter maps ASCII and U+00A0 to U+00FF except U+00AD (soft hyphen) and has no
U+FFFD or box drawing; chrome needs neither.

`tools/fonts/OFL.txt` and the `daphnis_*` drawings are the Daphnis faces K-2 and K-4 built; they leave with the swap
(F5), after l accepts the proof sheet.
