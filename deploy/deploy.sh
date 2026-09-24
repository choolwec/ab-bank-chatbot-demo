#!/usr/bin/env bash
# Deploy a release tag to the production VM (ticket P7).
#
# Usage:  sudo /opt/abz-chatbot/current/deploy/deploy.sh v1.4.0
#
#   1. fetches the tag into /opt/abz-chatbot/repo.git. Only vMAJOR.MINOR.PATCH
#      tags (optionally -rcN) are accepted: a branch is never deployed.
#   2. unpacks it into releases/<tag>, with its own virtualenv
#   3. pip install -r requirements.txt, python -m admin.fetch_model
#   4. runs the full test suite as the app user on a scratch data dir, with
#      none of the production environment (no real data, no real services)
#   5. only if the tests pass: checks the env file, points `current` at the
#      new release, restarts the service and waits for /health. If /health
#      fails it switches straight back to the release it replaced.
#
# The replaced release stays on disk for rollback.sh; the newest
# KEEP_RELEASES are kept. A tag already built and tested is not rebuilt.
# Step by step, with the first install: docs/runbook-production.md.

set -Eeuo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=deploy/lib.sh
. "$here/lib.sh"

KEEP_RELEASES=${KEEP_RELEASES:-5}
PYTHON=${PYTHON:-python3}
TEST_TIMEOUT=${TEST_TIMEOUT:-900}
REPO=$ABZ_ROOT/repo.git
TAG_PATTERN='^v[0-9]+\.[0-9]+\.[0-9]+(-rc\.?[0-9]+)?$'

tag=${1:-}
if [[ -z $tag ]]; then
    echo "usage: $0 <release tag, e.g. v1.4.0>" >&2
    exit 2
fi
[[ $tag =~ $TAG_PATTERN ]] || die "'$tag' is not a release tag (vMAJOR.MINOR.PATCH): branches are never deployed"
[[ -d $REPO ]] || die "no repository at $REPO (first install: docs/runbook-production.md)"
check_env
mkdir -p "$RELEASES" "$LOG_DIR"
log "deploy $tag requested by ${SUDO_USER:-${USER:-unknown}}"

# --- 1. the tag, and only a tag ---------------------------------------------------
# A moved tag makes this fetch fail ("would clobber existing tag"): good.
git --git-dir="$REPO" fetch --quiet --tags origin
if git --git-dir="$REPO" ls-remote --exit-code --heads origin "$tag" >/dev/null 2>&1; then
    die "origin has a branch called $tag as well; refusing an ambiguous name"
fi
commit=$(git --git-dir="$REPO" rev-parse --verify --quiet "refs/tags/$tag^{commit}") ||
    die "tag $tag not found on origin"
dest=$RELEASES/$tag

run_tests() {
    local build=$1 model_dir=$2 scratch rc=0
    scratch=$(mktemp -d "${TMPDIR:-/tmp}/abz-deploy-test.XXXXXX")
    [[ $EUID -ne 0 ]] || chown "$APP_USER" "$scratch"
    (cd "$build" && as_app timeout "$TEST_TIMEOUT" env -i \
        PATH=/usr/local/bin:/usr/bin:/bin HOME="$scratch" TMPDIR="$scratch" LANG=C.UTF-8 \
        ABZ_DATA_DIR="$scratch/data" EMBED_MODEL_DIR="$model_dir" PYTHONDONTWRITEBYTECODE=1 \
        .venv/bin/python -m pytest -q -p no:cacheprovider) >"$LOG_DIR/test-$tag.log" 2>&1 || rc=$?
    rm -rf "$scratch"
    log "tests: $(tail -n 1 "$LOG_DIR/test-$tag.log")"
    return "$rc"
}

# --- 2-4. build and test, unless this exact tag already passed ---------------------
if [[ -f $dest/.abz-release-ok ]]; then
    [[ $(cat "$dest/REVISION") == "$tag $commit" ]] ||
        die "$dest was built from another commit than $tag now names: the tag moved"
    log "$tag ($commit) is already built and tested"
else
    rm -rf "$dest"
    build=$(mktemp -d "$RELEASES/.build-$tag.XXXXXX")
    trap 'rm -rf "$build"' EXIT
    chmod 755 "$build"
    git --git-dir="$REPO" archive "$commit" | tar -x -C "$build"
    printf '%s %s\n' "$tag" "$commit" >"$build/REVISION"
    log "building $tag ($commit)"
    "$PYTHON" -m venv "$build/.venv"
    "$build/.venv/bin/pip" install --quiet --disable-pip-version-check --no-input -r "$build/requirements.txt"
    model_dir=$(env_value EMBED_MODEL_DIR)
    (cd "$build" && EMBED_MODEL_DIR="$model_dir" .venv/bin/python -m admin.fetch_model) ||
        die "the embedding model did not fetch and verify"
    run_tests "$build" "$model_dir" ||
        die "tests failed for $tag; the service was not touched (full log: $LOG_DIR/test-$tag.log)"
    "$build/.venv/bin/python" -m compileall -q "$build/app" "$build/admin" >/dev/null || true
    touch "$build/.abz-release-ok"
    chmod -R go-w "$build"
    mv -T "$build" "$dest"
    trap - EXIT
fi

# --- 5. switch, restart, check; straight back on failure ---------------------------
replaced=$(current_release)
replaced_previous=$(previous_release)
[[ $replaced != "$dest" ]] || log "$tag is already the current release; restarting only"
switch_to "$dest"
if restart_and_check; then
    log "deployed $tag ($commit); rollback.sh returns to $(name_of "$(previous_release)")"
else
    log "$tag failed its health check"
    if [[ -z $replaced || $replaced == "$dest" ]]; then
        die "$tag did not come up and there is nothing to switch back to: journalctl -u $SERVICE"
    fi
    switch_to "$replaced"
    # rollback.sh must not lead to the failed tag: put `previous` back too.
    if [[ -n $replaced_previous ]]; then
        ln -sfn "$replaced_previous" "$ABZ_ROOT/previous.new"
        mv -T "$ABZ_ROOT/previous.new" "$ABZ_ROOT/previous"
    else
        rm -f "$ABZ_ROOT/previous"
    fi
    restart_and_check || die "going back to $(name_of "$replaced") ALSO failed: journalctl -u $SERVICE"
    die "$tag did not come up; back on $(name_of "$replaced")"
fi

# --- keep the newest KEEP_RELEASES, never current or previous ----------------------
current=$(current_release)
previous=$(previous_release)
kept=0
while IFS= read -r dir; do
    [[ -n $dir ]] || continue
    if [[ $dir == "$current" || $dir == "$previous" ]]; then
        kept=$((kept + 1))
        continue
    fi
    if ((kept >= KEEP_RELEASES)); then
        rm -rf "$dir"
        log "pruned $(name_of "$dir")"
    else
        kept=$((kept + 1))
    fi
done < <(find "$RELEASES" -mindepth 1 -maxdepth 1 -type d -name 'v*' -printf '%T@ %p\n' | sort -rn | cut -d' ' -f2-)
