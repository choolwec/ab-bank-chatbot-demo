#!/usr/bin/env bash
# Run an admin command on the VM with the service's environment (ticket P7).
#
# Usage:  sudo /opt/abz-chatbot/current/deploy/admin.sh <command> [args...]
#   e.g.  admin.sh report --days 7
#         admin.sh shadow_report --days 7
#         admin.sh rotate_reply_key --check
#
# Reads /etc/abz-chatbot/env (root-only), then runs `python -m admin.<command>`
# from the current release as the app user, so the command sees the same
# data directory and keys as the service.

set -Eeuo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=deploy/lib.sh
. "$here/lib.sh"

command=${1:-}
if [[ ! $command =~ ^[a-z_][a-z0-9_]*$ ]]; then
    echo "usage: $0 <admin command> [args...]" >&2
    exit 2
fi
shift
release=$ABZ_ROOT/current
[[ -f $release/admin/$command.py ]] || die "no admin command called $command in $(name_of "$(current_release)")"
load_env
cd "$release"
if [[ $EUID -eq 0 ]]; then
    exec runuser -u "$APP_USER" -- .venv/bin/python -m "admin.$command" "$@"
fi
exec .venv/bin/python -m "admin.$command" "$@"
