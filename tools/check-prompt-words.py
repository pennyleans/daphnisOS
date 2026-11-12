#!/usr/bin/env python3
"""tools/check-prompt-words.py [FILE]: the approval prompts draw the desk's record, not a program's bytes (AC-V).

Frame 8's KERNEL ELEVATION REQUEST and frame 17's PARENT APPROVAL name the window that asks. They drew the
window's variable beside the title: a terminal's OSC 2 title or a pixel client's FBIO_TILE_VAR, both written by the
program, so the program asking for approval put 32 bytes of its choosing in the desk's own prompt (plan call AC-R1:
nothing the desk presents as its own word comes from the program). In user/ci/hdesk.ci (or FILE) this check holds
docs/specs/2026-11-11-ac-v-prompt-words.md section 3 in place:

- the functions that gather the prompts' words (prompt_row, prompt_row_ac, kp_note_text, kp_icon_of) read no
  program-set source: no var_of, wvar, terms, window title or name (title[, win_name, label_of), no icon chosen by
  the program's name (win_icon3, prog_icon3), no FBIO_TILE_INFO record (ask[);
- in prompt_row_ac the variable handed to prompt_ac_at stays empty: v appears only in its declaration and that
  call, and vl is only ever set to 0;
- kp_icon is written by its declaration, its reset to icons3.TERMINAL and one call,
  prompttitle.icon(lx_app[kp_win] - 1, ask[0..64]), the same record AC-T's title reads (AC-T2: kind 13's).
AC-V-R1 A (l, 20:12Z; the spec's edition 2, section 6) on top:
- frame 17's subject is the desk's record: in prompt_row_ac the subject buffer sb is written by kp_subject(sb) in
  the parent's branch (if (kp_parent_hdr)), by the copy of the request text in its else branch (frame 8's command
  field, a parent's own kern), by acctask.subject (RS-AQ's operation, PR 333's wiring) and by deskask.subject
  (the desk's own ask, Date and Time's Set and zone: user/ci/kit/deskask.ci); kp_subject, like the other
  gatherers, reads no program-set source, and no request text;
- the request text kp_text is read in four places only: kern_next's log line, prompt_row's call of prompt_at
  (frame 8), that else branch, and nowhere else; it is written by one call, kp_len = reqtext.clean(...) in
  kern_next, so only printable ASCII reaches the prompt and the log (user/ci/kit/reqtext.ci,
  tests/ac/reqtext_test.ci); no byte of it is written elsewhere, and kp_len has that one writer.
GV-2 (frame 21, the design thread's answer of 2026-11-12 08:15Z): the Grants page's object is the request text
the desk said yes to: gr_asked copies those clean bytes once (GRANTS below), and the request text is read nowhere
else.
AC-T2 (the spec's edition 3): kp_exe, the asking process's image (FBIO_TILE_INFO kind 13 by kp_vp), is written
by its zeroing loop and one copy of that record in kern_next, taken only when the record's vpid is kp_vp, and
read by one call, prompttitle.subject(kp_exe, t), in kp_subject.
Exit 0 when all hold; each fault on its own line otherwise.
"""
import re
import sys

GATHER = ("prompt_row", "prompt_row_ac", "kp_note_text", "kp_icon_of", "kp_subject")
FORBID = {"var_of": r"\bvar_of\(", "wvar": r"\bwvar\b", "terms": r"\bterms\.", "title[": r"\btitle\[",
          "win_name": r"\bwin_name\(", "label_of": r"\blabel_of\(", "win_icon3": r"\bwin_icon3\(",
          "prog_icon3": r"\bprog_icon3\(", "ask[": r"\bask\["}
ICON_SET = {"kp_icon = icons3.TERMINAL;", "kp_icon = prompttitle.icon(lx_app[kp_win] - 1, ask[0..64]);"}
EXE_ZERO = "for k in 0..64 { kp_exe[k] = 0; }"
EXE_READ = ("if (kp_vp > 0 && hdeskctl.tile_ask(FBIO_TILE_INFO, 13, kp_vp, ask[0..64]) == 0"
            " && word_at(ask, 0) == kp_vp) {")
EXE_COPY = "for k in 0..64 { kp_exe[k] = ask[k]; }"
EXE_USE = "I64 n = prompttitle.subject(kp_exe, t);"
RECORD_ONLY = ("kp_note_text", "kp_icon_of", "kp_subject")   # gatherers that never read the request text
CLEAN = "kp_len = reqtext.clean(ask[8..64], word_at(ask, 1), kp_text);"
LOG = "I64 put = ptyctl.pty_write(1, kp_text[0..kp_len]);"
COPY = "for k in 0..kp_len { sb[k] = kp_text[k]; }"
GRANTS = "for k in 0..kp_len { g_req[56 * i + k] = kp_text[k]; }"
HEAD = re.compile(r"(?:void|I64|Bool|U32|U64) (\w+)\(")


def bodies(code):
    """{name: [(line number, code)]} for each function of GATHER, from its header to its closing brace."""
    out = {}
    for i, (n, l) in enumerate(code):
        m = re.match(r"(?:void|I64|Bool|U32) (\w+)\(", l)
        if not m or m.group(1) not in GATHER:
            continue
        body = []
        for n2, l2 in code[i + 1:]:
            if l2.rstrip() == "}":
                break
            body.append((n2, l2))
        out[m.group(1)] = body
    return out


def check(lines):
    bad = []
    code = [(n + 1, l.split("//")[0]) for n, l in enumerate(lines)]
    found = bodies(code)
    for name in GATHER:
        if name not in found:
            bad.append("%s is not in the file" % name)
    for name, body in found.items():
        for n, l in body:
            for word, f in FORBID.items():
                if re.search(f, l):
                    bad.append("%d: %s reads a program-set source (%s)" % (n, name, word))
    for n, l in found.get("prompt_row_ac", []):
        if re.search(r"\bv\b", l) and l.strip() != "U8[32] v;" and "prompt_ac_at(" not in l:
            bad.append("%d: prompt_row_ac uses the variable buffer v other than handing it, empty, to prompt_ac_at" % n)
        m = re.search(r"\bvl\s*=[^=]\s*(.*?);", l)
        if m and m.group(1).strip() != "0":
            bad.append("%d: prompt_row_ac sets vl to other than 0" % n)
    decl = 0
    sets = 0
    for n, l in code:
        if re.match(r"I64 kp_icon = icons3\.TERMINAL;", l):
            decl += 1
        elif re.search(r"\bkp_icon\s*=[^=]", l):
            if l.strip() not in ICON_SET:
                bad.append("%d: kp_icon written as other than the record's icon" % n)
            sets += 1
    if decl != 1:
        bad.append("kp_icon is not declared once as I64 kp_icon = icons3.TERMINAL")
    if sets != 2:
        bad.append("kp_icon is written %d times, not twice (its reset and the record's icon)" % sets)
    for name in RECORD_ONLY:
        for n, l in found.get(name, []):
            if re.search(r"\bkp_(?:text|len)\b", l):
                bad.append("%d: %s reads the request text" % (n, name))
    bad += subject(found.get("prompt_row_ac", []))
    bad += request(code)
    bad += image(code)
    return bad


def image(code):
    """AC-T2: kp_exe has its zeroing, one copy of kind 13's record of kp_vp, and one reader, kp_subject."""
    bad = []
    owner = None
    seen = {"decl": 0, "zero": 0, "copy": 0, "use": 0}
    for i, (n, l) in enumerate(code):
        m = HEAD.match(l)
        if m:
            owner = m.group(1)
        t = l.strip()
        if re.search(r"\bkp_exe\b", l):
            if owner is None and t.startswith("U8[64] kp_exe;"):
                seen["decl"] += 1
            elif owner == "kern_next" and t == EXE_ZERO:
                seen["zero"] += 1
            elif owner == "kern_next" and t == EXE_COPY and code[i - 1][1].strip() == EXE_READ:
                seen["copy"] += 1
            elif owner == "kp_subject" and t == EXE_USE:
                seen["use"] += 1
            else:
                bad.append("%d: %s uses kp_exe other than its zeroing, the copy of kind 13's record of kp_vp and"
                           " kp_subject's call" % (n, owner))
        if owner is not None and (l.rstrip() == "}" or (m and l.rstrip().endswith("}"))):
            owner = None
    for k in ("decl", "zero", "copy", "use"):
        if seen[k] != 1:
            bad.append("kp_exe: %s seen %d times, not once" % (k, seen[k]))
    return bad


def plain(l):
    """l with its string and character literals emptied, so their braces do not count."""
    l = re.sub(r'"(?:\\.|[^"\\])*"', '""', l)
    return re.sub(r"'(?:\\.|[^'\\])'", "''", l)


def subject(body):
    """AC-V-R1 A in prompt_row_ac: kp_subject(sb) in the then branch of if (kp_parent_hdr), the request text only
    in its else branch, sb written only by the record, that copy, acctask.subject and deskask.subject."""
    bad = []
    rows = []
    d = 0
    for n, l in body:
        rows.append((n, l, d))
        d += plain(l).count("{") - plain(l).count("}")
    at = [i for i, (n, l, d) in enumerate(rows) if "kp_subject(" in l]
    if len(at) != 1 or rows[at[0]][1].strip() != "sn = kp_subject(sb);":
        return ["prompt_row_ac does not take its subject once as sn = kp_subject(sb)"]
    s = at[0]
    inner = rows[s][2]
    opening = -1
    for i in range(s - 1, -1, -1):
        if rows[i][2] < inner:
            opening = i
            break
    if opening < 0 or rows[opening][1].strip() != "if (kp_parent_hdr) {" or rows[opening][2] != inner - 1:
        return ["%d: prompt_row_ac's kp_subject is not in the then branch of if (kp_parent_hdr)" % rows[s][0]]
    ends = [i for i in range(s + 1, len(rows)) if rows[i][2] == inner and rows[i][1].strip().startswith("}")]
    if len(ends) < 2 or rows[ends[0]][1].strip() != "} else {" or rows[ends[1]][1].strip() != "}":
        return ["%d: if (kp_parent_hdr) around kp_subject has no else branch" % rows[opening][0]]
    other = range(ends[0] + 1, ends[1])
    copies = 0
    for i, (n, l, d) in enumerate(rows):
        if re.search(r"\bkp_text\b", l):
            if i not in other or l.strip() != COPY:
                bad.append("%d: prompt_row_ac reads the request text outside frame 8's field (the else branch)" % n)
            copies += 1
        if re.search(r"\bsb\b", l):
            ok = (l.strip() in ("U8[64] sb;", "sn = kp_subject(sb);", "sn = acctask.subject(sb);",
                                "sn = deskask.subject(sb);")
                  or l.strip().startswith("prompt_ac_at(") or (i in other and l.strip() == COPY))
            if not ok:
                bad.append("%d: prompt_row_ac writes the subject sb from other than the desk's record" % n)
    if copies != 1:
        bad.append("prompt_row_ac copies the request text %d times, not once in its else branch" % copies)
    return bad


def request(code):
    """The request text: one writer through reqtext.clean, read by the log line, frame 8 and prompt_row_ac."""
    bad = []
    owner = None
    seen = {"clean": 0, "log": 0, "frame8": 0, "grants": 0, "decl": 0, "len": 0}
    for n, l in code:
        m = HEAD.match(l)
        if m:
            owner = m.group(1)
        t = l.strip()
        if re.search(r"\bkp_len\s*=[^=]", l) and not t.startswith("I64 kp_len = 0;"):
            if owner != "kern_next" or t != CLEAN:
                bad.append("%d: %s sets kp_len other than by reqtext.clean" % (n, owner))
            seen["len"] += 1
        if re.search(r"\bkp_text\b", l):
            if re.search(r"\bkp_text\s*\[[^\]]*\]\s*=[^=]", l):
                bad.append("%d: %s writes a byte of the request text other than through reqtext.clean" % (n, owner))
            if owner is None and t.startswith("U8[56] kp_text;"):
                seen["decl"] += 1
            elif owner == "kern_next" and t == CLEAN:
                seen["clean"] += 1
            elif owner == "kern_next" and t == LOG:
                seen["log"] += 1
            elif owner == "prompt_row" and t.startswith("prompt_at(x0, y0, kp_text, kp_len,"):
                seen["frame8"] += 1
            elif owner == "gr_asked" and t == GRANTS:
                seen["grants"] += 1
            elif owner != "prompt_row_ac":
                bad.append("%d: %s uses the request text beyond its writer, its log line, frame 8's field and"
                           " frame 21's object"
                           % (n, owner))
        if owner is not None and (l.rstrip() == "}" or (m and l.rstrip().endswith("}"))):
            owner = None
    for k, want in (("decl", 1), ("clean", 1), ("log", 1), ("frame8", 1), ("grants", 1), ("len", 1)):
        if seen[k] != want:
            bad.append("the request text: %s seen %d times, not %d" % (k, seen[k], want))
    return bad


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "user/ci/hdesk.ci"
    bad = check(open(path, encoding="utf-8").read().split("\n"))
    for b in bad:
        print(b)
    if bad:
        return 1
    print("the approval prompts draw the desk's record only: %s read no program-set source; frame 17's subject is"
          " the record; the request text, printable only, is drawn in frame 8's field and frame 21's object alone"
          % ", ".join(GATHER))
    return 0


if __name__ == "__main__":
    sys.exit(main())
