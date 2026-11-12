# tests/core/session.sh: the core session (docs/specs/2026-11-06-c-core.md section 6), run by cish on Linux and under
# Daphnis in the core image: /bin holds the native tools and no busybox; the fixture tree is /t, CT-3's /s. Only what is the
# same on both appears: names, contents and sizes, not modes, owners, times or blocks.
cd t
cat text.txt
cat nonl.txt; echo
cat text.txt nonl.txt | wc
wc text.txt long.txt bin.dat
wc -l < long.txt
cat long.txt | cat | wc -c
cat missing; echo cat status $?
wc -L text.txt; echo wc status $?
cat utf8.txt | wc -m -w
ls -1 ../bin
ls -1 -R look
ls -C look look/sub
ls -d look look/a.txt; ls missing; echo ls status $?
head -3 text.txt; head -n 2 look/b.txt look/a.txt
head -c 300 long.txt | wc -c
tail -n 2 text.txt; tail -c 10 nonl.txt; echo
cat long.txt | tail -n 3 | wc -c
tail -n +29 look/b.txt
stat -c '%n %s %F' text.txt empty look/sub/c.txt; stat -c '%n %F' look
stat missing; echo stat status $?
du missing; echo du status $?
du -h look; echo du status $?
mkdir -p made/a/b; echo mkdir $?
tee made/t1 < text.txt | wc -l
cp text.txt nonl.txt made/a/b; cat made/a/b/nonl.txt; echo
cp -R box made/box2; cat made/box2/in/deep/c.txt
cp made/box2 made/x; echo cp status $?
mv made/t1 made/t2; wc -c made/t2
mv made/t1 made/t3; echo mv status $?
f=$(mktemp -p made m.XXXXXX); test -f "$f" && echo mktemp file
d=$(mktemp -d -p made); test -d "$d" && echo mktemp dir
rmdir "$d" made/a; echo rmdir status $?
rm "$f"; cp text.txt made/q; rm -i made/q < yes.txt; echo; test -e made/q || echo q gone
rm made/box2; echo rm status $?
rm -r made/box2 made/a; test -e made/box2 || echo box2 gone
rmdir -p made/t2; echo rmdir status $?
rm made/t2; rmdir -p made; test -e made || echo made gone
/bin/echo native echo:  a   b
env -i A=1 B=2 C=x=y
env -i A=1 /bin/env
find f/a
find f -name c.txt -exec /bin/echo found {} \;
find f -type f -size +2 -exec /bin/echo {} +
find f/a -type d -print0 | xargs -0 /bin/echo dirs:
cat x/quote.txt | xargs -n 2
xargs -I {} /bin/echo [{}] < x/repl.txt
xargs -L 2 < x/lines.txt
date -u -d @1767225600
date -d @0 '+%F %T %Z %s %j %V'
sleep 1; echo sleep status $?
find missing; echo find status $?
xargs nosuch < text.txt; echo xargs status $?
cd ../s
grep -n apple words.txt; grep -c -E 'fig|Date' words.txt; grep -q zzz words.txt; echo grep status $?
grep -r -l -i apple dir
sort -t: -k3,3n cols.txt | cut -d: -f1
sort words.txt | uniq -c | sort -rn | head -n 3
tr a-z A-Z < text.txt | tr -s ' '
cut -c1-9 long.txt | head -n 2
cmp text.txt text3.txt; echo cmp status $?
sha256sum text.txt empty; sha256sum -c sums.txt
sort -o out.txt words.txt; head -n 2 out.txt
md5sum text.txt empty; md5sum -c sums.md5
cd ../t
# CT-5: ../bin names the image's tools on Linux and under Daphnis alike (cish's builtins would answer test, [, printf,
# true and false, and /bin on Linux is the host's)
../bin/test -f text.txt; echo test $?; ../bin/[ -d look ]; echo bracket $?; ../bin/[ -d look; echo bracket $?
../bin/printf '%s=%d|%5s|\n' x 5 ab; ../bin/true; echo true $?; ../bin/false; echo false $?
basename /a/b/c.txt .txt; dirname /a/b/c.txt; dirname c.txt
seq -s , 1 5; seq -w 8 10; seq 1 0 3; echo seq status $?
rev nonl.txt; echo; rev < text.txt | head -n 2
cp text.txt cut.txt; truncate -s 5 cut.txt; cat cut.txt; echo; truncate -s 1k cut.txt; wc -c cut.txt; rm cut.txt
sync; echo sync $?
# BU-2b: tier C-2 (docs/specs/2026-11-07-bu2-meta.md section 6): links, modes and set times read alike on both
mkdir m; cd m
echo x > a; ln a b; ln -s a c; ln -s ../text.txt t; ln b ../m/d; echo ln $?
stat -c '%n %h %s %F' a b c d; cat c t | wc -c; ls
chmod 640 a; chmod u+x,o+r d; chmod -R go-r . ; stat -c '%n %a' a b c d t
touch -d '2020-01-02 03:04:05' a; touch -t 200001010000.30 n; touch -m -d @86400 n; stat -c '%n %X %Y' a b n
touch -c none; ln missing x; echo ln status $?; chmod 9 a; echo chmod status $?
uname -m; uname -x; echo uname status $?
cd ..; rm -r m; test -e m || echo m gone
echo done
