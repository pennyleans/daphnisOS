# user/cvim/scan: cint's lexer, vendored for cvim's highlighting gate

`scan.ci` and `limits.ci` are `compiler/scan.ci` and `compiler/limits.ci` of the public cint at the pin,
`v0.2.18` (`a14a03f`, the toolchain this tree is built with), byte for byte, with cint's `LICENSE`. cvim's
`user/ci/cvim/hl.ci` must give the same tokens (kind, start, length) as `scan.ci` on every `.ci` file of cint's
conformance corpus that `scan.ci` accepts (spec docs/specs/2026-11-07-cv-cvim.md section 7; `tests/cvim/hl_gate.py`).
`scan.ci` imports `limits` from its own source root, so the gate builds them in a root of their own. A new pin copies
them again and updates the sums below.

```
12fe2ab758968a7c988490be8b7e2e3a54ac5b33ec8eac2caeda96cfc13949e9  scan.ci
483e0ab1faa81ae6bc8c2fc396768a83acbaeeac669c4337399a495b7c99c1cd  limits.ci
```
