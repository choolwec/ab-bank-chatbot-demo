#!/usr/bin/env bash
# Roll back to the previous release (ticket P7).
#
# Usage:  sudo /opt/abz-chatbot/current/deploy/rollback.sh          the release deploy.sh replaced
#         sudo /opt/abz-chatbot/current/deploy/rollback.sh v1.3.0   any tested release still on disk
#
# Only switches symlinks and restarts: nothing is fetched, built or tested
# (every release on disk passed its tests when deploy.sh built it), so it
# takes seconds. Running it twice in a row returns to where you started.
# Databases are shared by all releases; migrations are additive (new columns,
# ignored by older code), so an older release reads today's data. A release
# whose notes say otherwise needs a restore instead (runbook-production.md).

set -Eeuo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=deploy/lib.sh
. "$here/lib.sh"

if [[ -n ${1:-} ]]; then
    target=$RELEASES/$1
else
    target=$(previous_release)
fi
[[ -n $target && -f $target/.abz-release-ok ]] || die "no tested release at ${target:-previous}"
current=$(current_release)
[[ $target != "$current" ]] || die "$(name_of "$target") is already the current release"
check_env

log "rollback from $(name_of "$current") to $(name_of "$target") requested by ${SUDO_USER:-${USER:-unknown}}"
switch_to "$target"
restart_and_check ||
    die "$(name_of "$target") failed its health check: journalctl -u $SERVICE (run rollback.sh again to return to $(name_of "$current"))"
log "now running $(name_of "$target"); rollback.sh returns to $(name_of "$current")"
