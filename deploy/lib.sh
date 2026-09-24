# shellcheck shell=bash disable=SC2034  # variables used by the scripts that source it
# Shared by deploy.sh, rollback.sh, restore.sh and admin.sh (ticket P7).
# Not run directly. Every path can be overridden from the environment, which
# is how tests/test_deploy.py runs the scripts against a temporary tree.
#
# VM layout (docs/runbook-production.md):
#   /opt/abz-chatbot/repo.git          bare clone; only tags are deployed
#   /opt/abz-chatbot/releases/<tag>/   one tested release each, own .venv
#   /opt/abz-chatbot/current           symlink: the running release
#   /opt/abz-chatbot/previous          symlink: where rollback.sh goes
#   /etc/abz-chatbot/env               secrets and settings (root, 600)
#   /var/lib/abz-chatbot/data/         databases and keys (the abz user)

ABZ_ROOT=${ABZ_ROOT:-/opt/abz-chatbot}
APP_USER=${APP_USER:-abz}
SERVICE=${SERVICE:-abz-chatbot}
ENV_FILE=${ENV_FILE:-/etc/abz-chatbot/env}
HEALTH_URL=${HEALTH_URL:-http://127.0.0.1:8000/health}
HEALTH_TRIES=${HEALTH_TRIES:-60}
LOG_DIR=${LOG_DIR:-/var/log/abz-chatbot}
SYSTEMCTL=${SYSTEMCTL:-systemctl}
RELEASES=$ABZ_ROOT/releases
# Must be set in the env file; see deploy/env.example.
REQUIRED_ENV=(ABZ_DATA_DIR ABZ_FLAGS_FILE EMBED_MODEL_DIR PROXY_HOPS ALLOWED_ORIGINS USER_KEY_SECRET REPLY_KEY)

log() {
    local line
    line="$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"
    printf '%s\n' "$line" >&2
    if mkdir -p "$LOG_DIR" 2>/dev/null; then
        printf '%s\n' "$line" >>"$LOG_DIR/deploy.log" 2>/dev/null || true
    fi
}

die() {
    log "ERROR: $*"
    exit 1
}

# Run a command as the app user (a plain call when not root: tests, dev).
as_app() {
    if [[ $EUID -eq 0 ]]; then
        runuser -u "$APP_USER" -- "$@"
    else
        "$@"
    fi
}

# One value from the env file, without sourcing it (values are not shell).
env_value() {
    sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1
}

# Export every KEY=value line of the env file, taken literally.
load_env() {
    local line
    while IFS= read -r line || [[ -n $line ]]; do
        if [[ $line =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            export "${BASH_REMATCH[1]}=${BASH_REMATCH[2]}"
        fi
    done <"$ENV_FILE"
}

# The env file is private, complete, and has no blank KEY= line (a blank
# number crashes the app at import).
check_env() {
    local key blank perms
    local -a missing=()
    [[ -r $ENV_FILE ]] || die "cannot read $ENV_FILE"
    perms=$(stat -c '%a' "$ENV_FILE")
    [[ $perms == 600 ]] || die "$ENV_FILE must be chmod 600 (it is $perms)"
    if [[ $EUID -eq 0 && $(stat -c '%U' "$ENV_FILE") != root ]]; then
        die "$ENV_FILE must be owned by root"
    fi
    blank=$(grep -Eo '^[A-Za-z_][A-Za-z0-9_]*=[[:space:]]*$' "$ENV_FILE" | tr -d '=[:space:]' | tr '\n' ' ' || true)
    [[ -z $blank ]] || die "$ENV_FILE has blank lines for: $blank(set them or comment them out)"
    for key in "${REQUIRED_ENV[@]}"; do
        grep -Eq "^${key}=.+" "$ENV_FILE" || missing+=("$key")
    done
    ((${#missing[@]} == 0)) || die "$ENV_FILE is missing: ${missing[*]}"
}

current_release() {
    readlink -e "$ABZ_ROOT/current" 2>/dev/null || true
}

previous_release() {
    readlink -e "$ABZ_ROOT/previous" 2>/dev/null || true
}

# Point `current` at $1 atomically; `previous` takes the old `current`.
switch_to() {
    local target=$1 old
    old=$(current_release)
    ln -sfn "$target" "$ABZ_ROOT/current.new"
    mv -T "$ABZ_ROOT/current.new" "$ABZ_ROOT/current"
    if [[ -n $old && $old != "$target" ]]; then
        ln -sfn "$old" "$ABZ_ROOT/previous.new"
        mv -T "$ABZ_ROOT/previous.new" "$ABZ_ROOT/previous"
    fi
}

# /health answers "status": "ok" within HEALTH_TRIES seconds.
healthy() {
    local i
    for ((i = 1; i <= HEALTH_TRIES; i++)); do
        if curl -fsS --max-time 2 "$HEALTH_URL" 2>/dev/null | grep -Eq '"status": ?"ok"'; then
            return 0
        fi
        sleep 1
    done
    return 1
}

restart_and_check() {
    "$SYSTEMCTL" restart "$SERVICE" && healthy
}

name_of() {
    basename "${1:-none}"
}
