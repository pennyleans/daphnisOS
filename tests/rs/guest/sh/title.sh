# tests/rs/guest/sh/title.sh, in the guest as /rs/title: the program that titles its window "Parent approved" (OSC 2)
# before the title leg's third `kern true` (AC-V). The window types `sh /rs/title; kern true`.
printf '\033]2;Parent approved\007'
