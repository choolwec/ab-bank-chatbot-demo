#!/usr/bin/env bash
# Nightly backup of the chatbot's data and keys (ticket P7).
# Run by cron as root (deploy/crontab.example); settings in
# /etc/abz-chatbot/backup.conf (plain KEY=value lines, root-only).
#
# One archive per night, abz-<UTC time>.tar.gz[.age], in BACKUP_DIR:
#   data/audit.db, sessions.db, inbox.db  consistent copies taken while the
#                                        service runs (sqlite3 .backup), each
#                                        checked with PRAGMA integrity_check
#   data/audit.jsonl                     the append-only audit copy
#   data/user_key_secret, reply_key      when the app generated them into data/
#   etc/env, etc/flags.json              the env file holds USER_KEY_SECRET and
#                                        REPLY_KEY. Without REPLY_KEY every sealed
#                                        reply address is unreadable; without
#                                        USER_KEY_SECRET reports lose continuity.
# The archive is encrypted with age to BACKUP_AGE_RECIPIENT (a public key;
# the private key never sits on this VM), kept RETENTION_DAYS days here, and
# copied off the VM to OFFSITE_DEST, which must be inside Zambia: a host:path
# reached over SSH, or a mounted path. Old copies there are pruned by the
# destination, not from here, so a compromised VM cannot delete them.
# Exit status is non-zero on any failure, including a missing off-VM copy.

set -Eeuo pipefail
umask 077

BACKUP_CONF=${BACKUP_CONF:-/etc/abz-chatbot/backup.conf}
SETTINGS=" DATA_DIR ENV_FILE FLAGS_FILE BACKUP_DIR RETENTION_DAYS BACKUP_AGE_RECIPIENT OFFSITE_DEST OFFSITE_SSH_KEY "
if [[ -r $BACKUP_CONF ]]; then
    while IFS= read -r line || [[ -n $line ]]; do
        if [[ $line =~ ^([A-Z_][A-Z0-9_]*)=(.*)$ && $SETTINGS == *" ${BASH_REMATCH[1]} "* ]]; then
            declare "${BASH_REMATCH[1]}=${BASH_REMATCH[2]}"
        fi
    done <"$BACKUP_CONF"
fi
DATA_DIR=${DATA_DIR:-/var/lib/abz-chatbot/data}
ENV_FILE=${ENV_FILE:-/etc/abz-chatbot/env}
FLAGS_FILE=${FLAGS_FILE:-/etc/abz-chatbot/flags.json}
BACKUP_DIR=${BACKUP_DIR:-/var/backups/abz-chatbot}
RETENTION_DAYS=${RETENTION_DAYS:-14}
BACKUP_AGE_RECIPIENT=${BACKUP_AGE_RECIPIENT:-}  # age1... public key [CONFIRM: key custodian]
OFFSITE_DEST=${OFFSITE_DEST:-}                  # [CONFIRM: destination inside Zambia, IT]
OFFSITE_SSH_KEY=${OFFSITE_SSH_KEY:-/root/.ssh/abz_backup}
DATABASES=(audit.db sessions.db inbox.db)
KEY_FILES=(user_key_secret reply_key)

say() {
    printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
    logger -t abz-backup -- "$*" 2>/dev/null || true
}

die() {
    say "FAILED: $*"
    exit 1
}

command -v sqlite3 >/dev/null || die "sqlite3 is not installed (apt install sqlite3)"
[[ -d $DATA_DIR ]] || die "no data directory at $DATA_DIR"
mkdir -p "$BACKUP_DIR"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
work=$(mktemp -d "$BACKUP_DIR/.work-$stamp.XXXXXX")
trap 'rm -rf "$work"' EXIT
snap=$work/abz-$stamp
mkdir -p "$snap/data" "$snap/etc"

for db in "${DATABASES[@]}"; do
    if [[ ! -f $DATA_DIR/$db ]]; then
        say "note: $db does not exist yet; skipped"
        continue
    fi
    sqlite3 -cmd ".timeout 10000" "$DATA_DIR/$db" ".backup '$snap/data/$db'" || die "could not copy $db"
    check=$(sqlite3 "$snap/data/$db" "PRAGMA integrity_check;")
    [[ $check == ok ]] || die "the copy of $db failed its integrity check: $check"
done
if [[ -f $DATA_DIR/audit.jsonl ]]; then
    cp -p "$DATA_DIR/audit.jsonl" "$snap/data/"
fi

# The two secrets: from data/ if the app generated them there, else the env
# file must hold them. A backup without them is not a usable backup.
for key in "${KEY_FILES[@]}"; do
    if [[ -f $DATA_DIR/$key ]]; then
        cp -p "$DATA_DIR/$key" "$snap/data/"
    fi
done
if [[ -f $ENV_FILE ]]; then
    cp -p "$ENV_FILE" "$snap/etc/env"
fi
if [[ -f $FLAGS_FILE ]]; then
    cp -p "$FLAGS_FILE" "$snap/etc/flags.json"
fi
require_secret() {  # $1: env variable, $2: the file the app generates instead
    if [[ ! -f $snap/data/$2 ]] && ! grep -Eq "^$1=.+" "$snap/etc/env" 2>/dev/null; then
        die "$1 is neither in $ENV_FILE nor in $DATA_DIR/$2: this backup could not be restored"
    fi
}
require_secret USER_KEY_SECRET user_key_secret
require_secret REPLY_KEY reply_key

tar -czf "$work/abz-$stamp.tar.gz" -C "$work" "abz-$stamp"
archive=$work/abz-$stamp.tar.gz
if [[ -n $BACKUP_AGE_RECIPIENT ]]; then
    command -v age >/dev/null || die "age is not installed (apt install age)"
    age -r "$BACKUP_AGE_RECIPIENT" -o "$archive.age" "$archive" || die "encryption failed"
    rm -f "$archive"
    archive=$archive.age
else
    say "WARNING: BACKUP_AGE_RECIPIENT is not set, so this backup is NOT encrypted"
fi
name=$(basename "$archive")
(cd "$work" && sha256sum "$name" >"$name.sha256")
mv "$archive" "$work/$name.sha256" "$BACKUP_DIR/"
final=$BACKUP_DIR/$name
say "written $final ($(du -h "$final" | cut -f1))"

find "$BACKUP_DIR" -maxdepth 1 -type f -name 'abz-*' -mtime +"$((RETENTION_DAYS - 1))" -print -delete |
    while IFS= read -r old; do say "pruned $old"; done
find "$BACKUP_DIR" -maxdepth 1 -type d -name '.work-*' -mtime +1 -exec rm -rf {} + 2>/dev/null || true

[[ -n $OFFSITE_DEST ]] || die "local backup written, but OFFSITE_DEST is not set: there is no off-VM copy"
rsync -a --chmod=F600 -e "ssh -i $OFFSITE_SSH_KEY -o BatchMode=yes -o StrictHostKeyChecking=yes" \
    "$final" "$final.sha256" "$OFFSITE_DEST/" || die "the off-VM copy to $OFFSITE_DEST failed"
say "copied off the VM to $OFFSITE_DEST"
