#!/usr/bin/env bash
# ARC 038 heartbeat: elapsed is MEASURED from the recorded arc start, never derived from a plan.
S=$(cat /home/bbt/nix/scratchpad/arc038/.arc_start_epoch)
N=$(date +%s); E=$((N-S)); printf 'elapsed %dh%02dm (measured)  now %s\n' $((E/3600)) $(((E%3600)/60)) "$(date +%H:%M)"
