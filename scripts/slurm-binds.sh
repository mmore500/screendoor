#!/bin/sh
# Run on the HOST (not in the container): print an `export APPTAINER_BIND=...`
# line binding Slurm's binaries, libraries, config and munge socket.
#   eval "$(apptainer exec docker://ghcr.io/<owner>/screendoor:vX cat \
#     /opt/screendoor/slurm-binds.sh | sh)"
set -eu
binds=""
add() { case ",$binds," in *",$1,"*) ;; *) binds="${binds:+$binds,}$1" ;; esac; }
for cmd in sbatch squeue sacct scontrol scancel; do
  p="$(command -v "$cmd" 2>/dev/null || true)"
  [ -n "$p" ] || continue
  add "$p"
  ldd "$p" 2>/dev/null | awk '/=> \//{print $3}' | while read -r lib; do
    case "$lib" in */slurm*|*/munge*|*libslurm*|*libmunge*) echo "$lib" ;; esac
  done > /tmp/.sd-libs.$$ || true
  while read -r lib; do add "$lib"; done < /tmp/.sd-libs.$$
  rm -f /tmp/.sd-libs.$$
done
conf="${SLURM_CONF:-}"
if [ -z "$conf" ] && command -v scontrol >/dev/null 2>&1; then
  conf="$(scontrol show config 2>/dev/null | awk -F'= ' '/^SLURM_CONF/{print $2}')"
fi
[ -n "$conf" ] && [ -e "$conf" ] && add "$(dirname "$conf")"
sock=""
if command -v scontrol >/dev/null 2>&1; then
  sock="$(scontrol show config 2>/dev/null | sed -n 's/.*AuthInfo.*socket=\([^,]*\).*/\1/p')"
fi
for d in "$sock" /run/munge /var/run/munge; do
  [ -n "$d" ] && [ -e "$d" ] && { add "$(dirname "$d" | sed 's#/munge$##')/munge"; break; }
done
add /etc/passwd
add /etc/group
echo "export APPTAINER_BIND=\"${APPTAINER_BIND:+$APPTAINER_BIND,}$binds\""
