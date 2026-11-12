#!/usr/bin/env python3
"""tools/check-image-apps.py [ROOT]: HW-17's guard, hosted: the release image holds what the desk opens.

The release image is hdesk/release.cpio, whose members the Makefile keeps in one list (`make -s
print-hdesk-release`, the recipe's own). It fails, one line a reason, when:
  - a program the desk's sources name as "/bin/NAME" in a string (user/ci: kit/apps.ci's table, host.c's /bin/shot,
    runas.h, every other literal) is not a member bin/NAME;
  - a path under /dev, /etc or /proc that the desk's sources name in a string (user/ci: runas.h's /dev/null, xargs's
    /dev/tty, every other literal; a printf form such as "/dev/pts/%u" names what comes before the %) is neither a
    member nor a name the kernel answers itself: src/fs.ci's device names (`name_at(w_raw, at, "dev/...")`, one
    ending in / a prefix) and src/proc.ci's (`same_text(raw, "/proc/self/exe")`), read from the kernel's source;
  - a member comes from anywhere but O/ubin (a program built from source at HEAD: the Makefile's RELEASE_PROGS),
    tests/image (the image's text files) or, for etc/daphnis and etc/notices.txt alone, O/hdesk/about
    (tools/mkabout.py's About files, made from the tree), so no spelling of the committed user/bin passes (RG-1); or
    a program of RELEASE_PROGS is no member;
  - a member is Doom's (l 2026-11-12 07:59Z: no Doom in 0.1.0's image), by the Makefile's DOOM_PROGS and DOOM_FILES;
  - src/main_hdesk.ci, the release kernel's main, does not bring up the network: net.init(), dhcp.boot_begin() and
    dhcp.report_boot() in its code;
  - tools/build-release-stick.sh, the stick's build, does not hand hdesk/release.cpio to tools/build-esp.sh in every
    call of it (a command that runs the script, never text that names it), or hands it hdesk/initrd.cpio (the gates'
    image, with Doom);
  - any image's recipe, not the release image's alone (every $(O)/NAME/initrd.cpio and release.cpio of the Makefile,
    with everything it is built from), reads or writes the committed user/bin: a word of a command `make -n -B` prints
    for it that names a path under user/bin, or a run of user/ci/build.sh or user/c/build.sh without CI_OUT, which
    would write there (RG-1, the export lane's read of l-3-recut: deskplay took monitor, setkey and bgread from
    user/bin, which has none);
  - a tracked script outside docs/ (a gate or leg check-*.sh, a tool, a test, the Makefile: *.sh, *.py, *.mk) names a
    program under user/bin in its code, not in a # comment: user/bin/NAME for any NAME but NOTICE, a join of
    "user" and "bin", or a shell default of user/bin (${CI_OUT:-user/bin}, which a hand run of a build.sh writes)
    (RG-1: the gates take their programs from O/ubin, and user/bin holds NOTICE alone). SCAN_EXEMPT names the
    files that may, each with its reason.
Exit 0 with one summary line when all hold, else 1."""
import os
import re
import subprocess
import sys

LITERAL = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
BIN = re.compile(r'(?<![A-Za-z0-9_.])/bin/([A-Za-z0-9_.-]+)')
SYSPATH = re.compile(r'^/((?:dev|etc|proc)/[^\s:%"]*)')
KNAME_FS = re.compile(r'name_at\(w_raw, at, "([^"]+)"\)')
KNAME_PROC = re.compile(r'same_text\(raw, "/([^"]+)"\)')


def code(path, text):
    """The text without comments: // in .ci, /* */ and // in C."""
    if path.endswith(".ci"):
        return "\n".join(line.split("//")[0] for line in text.splitlines())
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(line.split("//")[0] for line in text.splitlines())


def sources(root):
    """Each source of user/ci (.ci, .c, .h) and its text without comments."""
    for d, _, files in os.walk(os.path.join(root, "user", "ci")):
        for f in sorted(files):
            if f.endswith((".ci", ".c", ".h")):
                p = os.path.join(d, f)
                yield os.path.relpath(p, root), code(p, open(p, errors="replace").read())


def opened(root):
    """The paths under /dev, /etc and /proc the sources name, without the leading /: each with its files."""
    want = {}
    for rel, text in sources(root):
        for lit in LITERAL.findall(text):
            m = SYSPATH.match(lit)
            if m and not m.group(1).endswith("/"):
                want.setdefault(m.group(1), set()).add(rel)
            elif m and "%" in lit:
                want.setdefault(m.group(1), set()).add(rel)      # "/dev/pts/%u": the prefix
    return want


def kernel_names(root):
    """The names the kernel answers itself, read from its source: a name ending in / is a prefix."""
    names = set()
    for f, rx in (("fs.ci", KNAME_FS), ("proc.ci", KNAME_PROC)):
        names.update(rx.findall(code(f, open(os.path.join(root, "src", f)).read())))
    return names


def supplied(path, names, kernel):
    if path in names or path in kernel:
        return True
    return any(k.endswith("/") and path.startswith(k) for k in kernel)


def named(root):
    want = {}
    for d, _, files in os.walk(os.path.join(root, "user", "ci")):
        for f in sorted(files):
            if not f.endswith((".ci", ".c", ".h")):
                continue
            p = os.path.join(d, f)
            for lit in LITERAL.findall(code(p, open(p, errors="replace").read())):
                for m in BIN.finditer(lit):
                    want.setdefault(m.group(1), set()).add(os.path.relpath(p, root))
    return want


# A command that runs tools/build-esp.sh: at the start of a command (a line, or after ; & | ( then do), past any
# NAME=VALUE words, env and bash. A line that only names the script, as text in a printf or echo, is no call (PR 464's
# GRUB.txt says it was "made by tools/build-esp.sh").
ESP_CALL = re.compile(r"""(?:^|[;&|(]|\bthen\b|\bdo\b)\s*(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|'[^']*'|[^\s"']*)\s+)*"""
                      r"""(?:env\s+(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|[^\s"']*)\s+)*)?(?:bash\s+|sh\s+)?"""
                      r"""[^\s"';&|()]*tools/build-esp\.sh(?=\s|$)""")


def stick(root):
    """What is wrong with the image tools/build-release-stick.sh ships, one line a reason: every call of
    tools/build-esp.sh must hand it hdesk/release.cpio and none hdesk/initrd.cpio, the gates' image with Doom."""
    path = os.path.join(root, "tools", "build-release-stick.sh")
    text = re.sub(r"\\\n", " ", open(path).read())          # a command continued with \ is one line
    lines = [re.sub(r"\s#\s.*$", "", line) for line in text.splitlines() if not line.lstrip().startswith("#")]
    calls = [line for line in lines if ESP_CALL.search(line)]
    bad = []
    if not calls or any("hdesk/release.cpio" not in line for line in calls):
        bad.append("tools/build-release-stick.sh does not hand hdesk/release.cpio to tools/build-esp.sh: the stick "
                   "would not ship the release image")
    if any("hdesk/initrd.cpio" in line for line in calls):
        bad.append("tools/build-release-stick.sh hands hdesk/initrd.cpio, the gates' image with Doom, to "
                   "tools/build-esp.sh")
    return bad


UBIN = "/tmp/check-image-apps-o"     # the O this check gives make: the built programs' directory is O/ubin


def members(root):
    out = subprocess.run(["make", "-s", "--no-print-directory", "O=" + UBIN, "print-hdesk-release"], cwd=root,
                         check=True, capture_output=True, text=True).stdout.splitlines()
    names = [w.partition("=")[0] for w in out[0].split()]
    sources = dict(w.split("=", 1) for w in out[0].split() if "=" in w)
    return names, out[1].split(), sources, (out[2].split() if len(out) > 2 else [])


ALLOWED = (UBIN + "/ubin/", "tests/image/")   # the only places a member may come from
# and the two About files tools/mkabout.py makes from the tree at every make (frame 31, PR 477), each at its own
# member name only
ABOUT = {"etc/daphnis": UBIN + "/hdesk/about/daphnis", "etc/notices.txt": UBIN + "/hdesk/about/notices.txt"}


def from_source(names, sources, progs):
    """RG-1: every member is a program built from source at HEAD (O/ubin), a text file of tests/image or one of the two
    About files at its own name (ABOUT); nothing else, so no spelling of the committed user/bin (./user/bin/X,
    O/ubin/../../user/bin/X) passes."""
    bad = []
    for n in names:
        src = sources.get(n)
        if src is not None and ABOUT.get(n) != src and (os.path.normpath(src) != src or not src.startswith(ALLOWED)):
            bad.append("the release image takes %s from %s, not from O/ubin (built from source at HEAD) or "
                       "tests/image" % (n, src))
    built = {os.path.basename(src) for src in sources.values() if src.startswith(UBIN + "/ubin/")}
    for prog in progs:
        if prog not in built:
            bad.append("RELEASE_PROGS builds %s, which no member of the release image takes" % prog)
    return bad


IMAGE = re.compile(r"^\$\(O\)/([a-z0-9]+)/((?:initrd|release)\.cpio):", re.M)
BUILD = re.compile(r"(?:^|\s)(?:bash\s+)?(?:\./)?user/c(?:i)?/build\.sh(?=\s|$)")


def images(root):
    """Each image the Makefile builds, as NAME/initrd.cpio or NAME/release.cpio."""
    with open(os.path.join(root, "Makefile")) as f:
        return sorted({"%s/%s" % m for m in IMAGE.findall(f.read())})


def under_user_bin(root, word):
    """True when word, a path (relative to root, or absolute), names user/bin or a path under it, in any spelling."""
    if not word or word.startswith("-"):
        return False
    path = os.path.normpath(os.path.join(os.path.realpath(root), word))
    ubin = os.path.join(os.path.realpath(root), "user", "bin")
    return path == ubin or path.startswith(ubin + os.sep)


def every_image(root, tool=None):
    """RG-1 for every image: what is wrong with each image's commands, one line a reason, and the images' count."""
    toolchain = tool or os.environ.get("CINT_TOOLCHAIN") or os.devnull   # make -n runs no compiler: any file will do
    bad = []
    names = images(root)
    for name in names:
        run = subprocess.run(["make", "-n", "-B", "--no-print-directory", "O=" + UBIN, "CINT_TOOLCHAIN=" + toolchain,
                              "%s/%s" % (UBIN, name)], cwd=root, capture_output=True, text=True)
        if run.returncode != 0:
            bad.append("make -n cannot plan %s: %s" % (name, (run.stderr.strip().splitlines() or ["?"])[-1]))
            continue
        hits = set()
        for line in run.stdout.splitlines():
            words = [w for word in line.replace(";", " ").split() for w in word.split("=")]
            hits.update(w for w in words if under_user_bin(root, w.strip("'\"")))
            if BUILD.search(line) and "--deps" not in line and "CI_OUT=" not in line:
                bad.append("the %s image's recipe runs a build.sh without CI_OUT, which writes the committed user/bin"
                           % name)
        if hits:
            bad.append("the %s image's recipe takes %d files from the committed user/bin (%s), not from O/ubin "
                       "(built from source at HEAD)" % (name, len(hits), ", ".join(sorted(hits)[:3])))
    return sorted(set(bad)), len(names)


SCRIPT = re.compile(r"(?:^|/)(?:Makefile|[^/]+\.(?:sh|py|mk))$")
PROGRAM = re.compile(r"(?<![A-Za-z0-9_.-])user/bin/([A-Za-z0-9_.+-]+)")
JOIN = re.compile(r"""["']user["']\s*[,/]\s*["']bin["']""")
DEFAULT = re.compile(r":-\.?/?user/bin(?=[}\"'/\s]|$)")     # a shell default that writes or reads the tree's user/bin
SCAN_EXEMPT = {
    "tools/check-image-apps.py": "this check: it names user/bin to refuse it",
    "tests/tools/test_image_sources.py": "this check's tests: their fixtures name user/bin to see it refused",
    "tools/doom/mktree.sh": "history: it cuts the Doom port's tree from a commit before DS-3, which holds user/bin/doom",
}


def tracked(root):
    """The tracked files of root (git ls-files), or every file under it outside .git when it is no repository."""
    run = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True)
    if run.returncode == 0:
        return run.stdout.splitlines()
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x != ".git"]
        out += [os.path.relpath(os.path.join(d, f), root).replace(os.sep, "/") for f in files]
    return out


def scripts(root):
    """RG-1 for every gate, leg and tool: each tracked script outside docs/ whose code names a program under user/bin,
    one line a name; and the scripts' count."""
    files = [f for f in tracked(root) if SCRIPT.search(f) and not f.startswith(("docs/", "user/bin/"))
             and f not in SCAN_EXEMPT]
    bad = []
    for f in sorted(files):
        try:
            with open(os.path.join(root, f), encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue        # tracked, removed from the work tree: nothing here to run
        for n, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            names = [m.group(1) for m in PROGRAM.finditer(line) if m.group(1) != "NOTICE"]
            if JOIN.search(line):
                names.append('"user", "bin"')
            if DEFAULT.search(line):
                names.append('a default')
            for name in names:
                if name == 'a default':
                    bad.append("%s:%d defaults a path to user/bin: a build writes, and a gate reads, O/ubin (RG-1)"
                               % (f, n))
                elif name.startswith('"'):
                    bad.append("%s:%d joins %s, the committed user/bin: a gate, leg or tool takes its programs from "
                               "O/ubin (RG-1)" % (f, n, name))
                else:
                    bad.append("%s:%d names user/bin/%s, a program: a gate, leg or tool takes it from O/ubin, built "
                               "from source at HEAD (RG-1)" % (f, n, name))
    return bad, len(files)


def main(argv):
    root = argv[0] if argv else "."
    names, doom, sources, progs = members(root)
    bad = []
    want = named(root)
    for prog in sorted(want):
        if "bin/" + prog not in names:
            bad.append("the release image has no bin/%s, which %s names" % (prog, ", ".join(sorted(want[prog]))))
    kernel = kernel_names(root)
    paths = opened(root)
    for path in sorted(paths):
        if not supplied(path, names, kernel):
            bad.append("the release image has no /%s and the kernel answers no such name, which %s opens"
                       % (path, ", ".join(sorted(paths[path]))))
    for n in names:
        if os.path.basename(n) in doom:
            bad.append("the release image holds %s, one of Doom's files" % n)
    main_c = code("main_hdesk.ci", open(os.path.join(root, "src", "main_hdesk.ci")).read())
    for call in ("net.init()", "dhcp.boot_begin()", "dhcp.report_boot("):
        if call not in main_c:
            bad.append("src/main_hdesk.ci does not call %s: the release kernel brings up no network" % call)
    bad += from_source(names, sources, progs)
    bad += stick(root)
    wrong, count = every_image(root)
    bad += wrong
    wrong, nscripts = scripts(root)
    bad += wrong
    for b in bad:
        print("check-image-apps: " + b)
    if bad:
        return 1
    print("check-image-apps: the release image's %d members hold the %d programs the desk names, and they or the "
          "kernel's %d names the %d paths of /dev, /etc and /proc it opens; no Doom; main_hdesk brings up the "
          "network; the stick ships it; its %d programs are built from source at HEAD; the %d images' recipes take "
          "nothing from user/bin, nor does any of the %d scripts" % (len(names), len(want), len(kernel), len(paths),
                                                                len(progs), count, nscripts))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
