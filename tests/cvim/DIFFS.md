# cvim vs. Vim 9.1: Intentional Differences

| Feature / Key | Vim 9.1 Behavior | cvim Behavior | Reason |
| :--- | :--- | :--- | :--- |
| `=` re-indent | C indenting (`cindent` rules, as `=` uses with no `indentexpr`) | section 6's brace rules: a `}` line takes its `{` line's indent; after a line ending in `{`, one shiftwidth more; after a `}` line, that block's `{` line's indent; else the previous non-blank line's; blank lines lose their blanks | spec section 6; Vim's continuation, label, comment and parenthesis rules are not cvim's. `edit_cases.py` uses brace code with `;` ends, where the two agree |
| `p` of a block register, Visual `p` | puts the block / replaces the selection | rings the bell (`not in cvim: p`) | not in CV-2b's scope; a later unit |
| `is` `as` `i"` `a"` (and the other quotes) on a Visual selection of more than one character | extends the selection | rings the bell | CV-2b extends words, paragraphs and brackets; sentence and quote extension are a later unit |
| wide unicode vertical goal | `a文z\nabcdef\n`, `llj`: byte cursor `[2,4]` | byte cursor `[2,3]` | spec section 3 requires one cell per code point; the terminal draws UTF-8 as `?` |

`motion_cases.py` asserts the pinned Vim result and the distinct cvim result separately. This policy case is excluded from Vim equality counts. Tabs retain the specified tabstop; byte cursor columns remain one-based.
