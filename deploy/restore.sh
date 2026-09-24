#!/usr/bin/env bash
# Restore a backup made by backup.sh (ticket P7).
#
# Usage:  sudo /opt/abz-chatbot/current/deploy/restore.sh <archive> [age identity file]
#   e.g.  restore.sh /var/backups/abz-chatbot/abz-20261201T233000Z.tar.gz.age /root/abz-backup-key.txt
#
# Checks the archive's sha256 and every database's integrity BEFORE touching
# anything, then stops the service, moves the live data directory aside
# (renamed, never deleted), puts the backup's databases and key files in
# place, starts the service and waits for /health.
# The backup's env file and flags.json are NOT copied over the live ones:
# they are left in a root-only folder for you to compare, and matter when
# rebuilding a VM (runbook-production.md, "Restore a backup").

set -Eeuo pipefail
umask 077
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=deploy/lib.sh
. "$here/lib.sh"

RESTORE_KEEP_DIR=${RESTORE_KEEP_DIR:-/root}
archive=${1:-}
identity=${2:-}
if [[ -z $archive ]]; then
    echo "usage: $0 <archive> [age identity file]" >&2
    exit 2
fi
[[ -f $archive ]] || die "no such archive: $archive"
command -v sqlite3 >/dev/null || die "sqlite3 is not installed (apt install sqlite3)"
data_dir=$(env_value ABZ_DATA_DIR)
[[ -n $data_dir ]] || die "ABZ_DATA_DIR is not set in $ENV_FILE"

if [[ -f $archive.sha256 ]]; then
    (cd "$(dirname "$archive")" && sha256sum --quiet -c "$(basename "$archive").sha256") ||
        die "checksum mismatch: $archive is damaged"
else
    log "warning: no $archive.sha256 next to the archive, so it was not verified"
fi

work=$(mktemp -d "${TMPDIR:-/tmp}/abz-restore.XXXXXX")
trap 'rm -rf "$work"' EXIT
tarball=$archive
if [[ $archive == *.age ]]; then
    [[ -n $identity ]] || die "the archive is encrypted: pass the age identity (private key) file"
    age -d -i "$identity" -o "$work/backup.tar.gz" "$archive" || die "could not decrypt $archive"
    tarball=$work/backup.tar.gz
fi
tar -xzf "$tarball" -C "$work"
snap=$(find "$work" -mindepth 1 -maxdepth 1 -type d -name 'abz-*' | head -n 1)
[[ -n $snap && -d $snap/data ]] || die "$archive is not a backup.sh archive"
for db in "$snap"/data/*.db; do
    [[ -f $db ]] || continue
    check=$(sqlite3 "$db" "PRAGMA integrity_check;")
    [[ $check == ok ]] || die "$(basename "$db") in the backup failed its integrity check: $check"
done

stamp=$(date -u +%Y%m%dT%H%M%SZ)
aside=$data_dir.pre-restore-$stamp
log "restore $(basename "$archive") requested by ${SUDO_USER:-${USER:-unknown}}; the live data moves to $aside"
"$SYSTEMCTL" stop "$SERVICE"
if [[ -d $data_dir ]]; then
    mv -T "$data_dir" "$aside"
fi
mkdir -p "$data_dir"
cp -p "$snap"/data/* "$data_dir"/
if [[ $EUID -eq 0 ]]; then
    chown -R "$APP_USER:$APP_USER" "$data_dir"
fi
chmod 700 "$data_dir"
if [[ -d $snap/etc ]]; then
    keep=$RESTORE_KEEP_DIR/abz-restore-$stamp
    mkdir -p "$keep"
    cp -p "$snap"/etc/* "$keep"/ 2>/dev/null || true
    log "the backup's env file and flags.json are in $keep (not applied)"
fi
"$SYSTEMCTL" start "$SERVICE"
healthy || die "the service did not come up on the restored data: journalctl -u $SERVICE. To undo: stop it, mv $aside $data_dir, start it"
log "restored $(basename "$archive"); the previous data is in $aside"
