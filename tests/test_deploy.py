"""P7: production hosting -- deploy/ files and the settings they rely on.

The shell scripts run here against a temporary tree (a fake /opt/abz-chatbot,
a local git "origin", a stand-in for systemctl and a file:// health check),
so no test needs root, systemd, nginx or the network.
"""

import getpass
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from app import config

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"


def _config_in_subprocess(env_extra: dict) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("ABZ_DATA_DIR", "ABZ_FLAGS_FILE")}
    env.update(env_extra)
    code = ("import json; from app import config; "
            "print(json.dumps([str(config.DATA_DIR), str(config.FLAGS_FILE)]))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True,
                         text=True, check=True).stdout
    return json.loads(out.strip().splitlines()[-1])


def test_data_dir_and_flags_file_can_live_outside_the_release(tmp_path):
    data, flags = tmp_path / "state" / "data", tmp_path / "flags.json"
    assert _config_in_subprocess({"ABZ_DATA_DIR": str(data), "ABZ_FLAGS_FILE": str(flags)}) == [
        str(data), str(flags)]
    assert data.is_dir()  # created, parents included


def test_unset_they_stay_in_the_repo(tmp_path):
    assert _config_in_subprocess({"ABZ_DATA_DIR": "", "ABZ_FLAGS_FILE": ""}) == [
        str(ROOT / "data"), str(ROOT / "flags.json")]


def test_kill_switches_follow_the_flags_file(tmp_path, monkeypatch):
    flags = tmp_path / "flags.json"
    flags.write_text(json.dumps({"FREE_TEXT_ENABLED": False}), encoding="utf-8")
    monkeypatch.delenv("FREE_TEXT_ENABLED", raising=False)
    monkeypatch.setattr(config, "FLAGS_FILE", flags)
    assert config.free_text_enabled() is False


def test_the_suite_never_writes_to_the_real_data_dir():
    assert config.DATA_DIR != ROOT / "data"


# --- deploy/ holds no secrets, and env.example is complete -----------------------

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bEAA[A-Za-z0-9]{30,}"),            # Meta access tokens
    re.compile(r"\bATATT[A-Za-z0-9_=-]{20,}"),        # Atlassian API tokens
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAGE-SECRET-KEY-1[0-9A-Z]{20,}"),
    re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{43}=(?![A-Za-z0-9_=-])"),  # a Fernet key
    re.compile(r"\b[0-9a-fA-F]{32,}\b"),              # hex secrets (USER_KEY_SECRET)
]
# NAME=value or NAME: value, where NAME looks secret and the value is literal.
ASSIGNMENT = re.compile(
    r"(?i)\b([\w.-]*(?:secret|token|passw(?:or)?d|api[_-]?key|private[_-]?key)[\w.-]*)[ \t]*[:=][ \t]*(\S+)")
PLACEHOLDER = re.compile(r"""^(?:["']?\$|["']?<|\[|\(|\{|/|true$|false$|["']{2}$)""")


def secret_findings(text: str) -> list[str]:
    found = [m.group(0) for p in SECRET_PATTERNS for m in p.finditer(text)]
    for m in ASSIGNMENT.finditer(text):
        value = m.group(2)
        if len(value) >= 8 and not PLACEHOLDER.match(value) and "example" not in value:
            found.append(m.group(0))
    return found


def test_the_secret_scanner_catches_real_looking_values():
    fernet = "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
    assert secret_findings(f"REPLY_KEY={fernet}")
    assert secret_findings("WA_APP_SECRET=4f1c2a9be07d")
    assert secret_findings("ADMIN_PASSWORD: hunter2hunter2")
    assert secret_findings("USER_KEY_SECRET=" + "ab" * 32)
    assert not secret_findings("REPLY_KEY=\n# ADMIN_PASSWORD=\nKEY=${OFFSITE_SSH_KEY:-/root/.ssh/abz_backup}")


def test_deploy_files_contain_no_secret_looking_values():
    scanned = sorted(p for p in DEPLOY.iterdir() if p.is_file()) + [ROOT / "render.yaml"]
    for path in scanned:
        findings = secret_findings(path.read_text(encoding="utf-8"))
        assert not findings, f"{path.name}: {findings}"


def _app_env_vars() -> set[str]:
    names = set()
    call = re.compile(r"""(?:os\.environ\.get|os\.getenv|(?<![\w.])flag|config\.flag)\(\s*["']([A-Z][A-Z0-9_]*)["']""")
    index = re.compile(r"""os\.environ\[\s*["']([A-Z][A-Z0-9_]*)["']\s*\]""")
    for folder in ("app", "admin"):
        for path in (ROOT / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            names.update(call.findall(text) + index.findall(text))
            if 'f"HANDOFF_MODE_{' in text:
                names.update(f"HANDOFF_MODE_{c}" for c in ("WEB", "WHATSAPP", "MESSENGER"))
    return names


def _env_example() -> tuple[set[str], list[str]]:
    listed, with_values = set(), []
    for line in (DEPLOY / "env.example").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^#?\s?([A-Z][A-Z0-9_]*)=(.*)$", line)
        if m:
            listed.add(m.group(1))
            if m.group(2).strip():
                with_values.append(line)
    return listed, with_values


def test_env_example_lists_every_variable_the_app_reads():
    read = _app_env_vars()
    assert {"REPLY_KEY", "USER_KEY_SECRET", "PROXY_HOPS", "ABZ_DATA_DIR", "SHADOW_MATCHER",
            "ABZ_EMERGENCY_PHONE", "HANDOFF_MODE_WHATSAPP"} <= read
    listed, _ = _env_example()
    assert not read - listed, f"add to deploy/env.example: {sorted(read - listed)}"


def test_env_example_carries_no_values():
    _, with_values = _env_example()
    assert not with_values


def test_the_scripts_require_what_env_example_marks_required():
    text = (DEPLOY / "env.example").read_text(encoding="utf-8")
    required = text.split("# --- Required", 1)[1].split("# ---", 1)[0]
    in_example = re.findall(r"^([A-Z][A-Z0-9_]*)=$", required, re.M)
    lib = (DEPLOY / "lib.sh").read_text(encoding="utf-8")
    in_lib = re.search(r"REQUIRED_ENV=\(([^)]*)\)", lib).group(1).split()
    assert in_example == in_lib


# --- the systemd unit and nginx site -------------------------------------------------

def test_the_service_runs_one_worker_as_a_non_root_user():
    unit = (DEPLOY / "abz-chatbot.service").read_text(encoding="utf-8")
    exec_start = re.search(r"^ExecStart=((?:.*\\\n)*.*)$", unit, re.M).group(1)
    assert "--workers 1" in exec_start and "--reload" not in exec_start
    assert re.search(r"^User=abz$", unit, re.M)
    assert re.search(r"^EnvironmentFile=/etc/abz-chatbot/env$", unit, re.M)
    assert re.search(r"^Restart=always$", unit, re.M)
    assert re.search(r"^ProtectSystem=strict$", unit, re.M) and re.search(r"^NoNewPrivileges=yes$", unit, re.M)


def test_nginx_forwards_the_client_address_and_leaves_webhook_bodies_alone():
    site = (DEPLOY / "nginx.conf").read_text(encoding="utf-8")
    site = "\n".join(line for line in site.splitlines() if not line.lstrip().startswith("#"))
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in site
    webhooks = re.search(r"location /webhooks/ \{(.*?)\n    \}", site, re.S).group(1)
    assert "proxy_pass http://abz_chatbot;" in webhooks
    for rewrite in ("proxy_set_body", "gunzip", "sub_filter", "proxy_pass_request_body off"):
        assert rewrite not in site
    assert re.search(r"^\s*client_max_body_size 64k;", site, re.M)
    assert not re.search(r"add_header\s+Access-Control-", site)  # CORS is the app's job
    assert re.search(r"~\^/widget/\s+cross-origin;", site)
    admin = re.search(r"location /admin/ \{(.*?)\n    \}", site, re.S).group(1)
    assert "deny all;" in admin


def test_staging_fetches_the_model_and_shadows_without_switching_over():
    import yaml

    service = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))["services"][0]
    assert "python -m admin.fetch_model" in service["buildCommand"]
    env = {v["key"]: v.get("value") for v in service["envVars"]}
    assert env["SHADOW_MATCHER"] == "true" and env["EMBEDDINGS_ENABLED"] == "false"
    assert env["PROXY_HOPS"] == "1"
    assert "--workers" not in service["startCommand"]


# --- the scripts, run against a temporary tree ---------------------------------------

# The scripts target the Linux VM; on Windows they are covered by CI.
_linux = sys.platform.startswith("linux")
needs_bash = pytest.mark.skipif(not (_linux and all(map(shutil.which, ("bash", "git", "curl")))),
                                reason="Linux with bash, git and curl")
needs_sqlite = pytest.mark.skipif(not (_linux and all(map(shutil.which, ("bash", "sqlite3", "curl")))),
                                  reason="Linux with bash, sqlite3 and curl")
REQUIRED_ENV = {
    "ABZ_DATA_DIR": "/srv/data", "ABZ_FLAGS_FILE": "/srv/flags.json", "EMBED_MODEL_DIR": "/srv/models",
    "PROXY_HOPS": "1", "ALLOWED_ORIGINS": "https://www.example.invalid",
    "USER_KEY_SECRET": "x" * 12, "REPLY_KEY": "y" * 12,
}


class Tree:
    """A fake /opt/abz-chatbot with two tagged, already-tested releases."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.root = tmp / "opt"
        self.health = tmp / "health.json"
        self.env_file = tmp / "env"
        self.write_env(REQUIRED_ENV)
        src = tmp / "src"
        src.mkdir()
        self.git(src, "init", "-q")
        self.commits = {}
        for tag in ("v0.0.1", "v0.0.2"):
            (src / "VERSION").write_text(tag, encoding="utf-8")
            self.git(src, "add", "VERSION")
            self.git(src, "commit", "-qm", tag)
            self.git(src, "tag", tag)
            self.commits[tag] = self.git(src, "rev-parse", "HEAD").strip()
        self.git(src, "branch", "hotfix")
        (self.root / "releases").mkdir(parents=True)
        self.git(tmp, "clone", "-q", "--bare", str(src), str(self.root / "repo.git"))
        for tag, commit in self.commits.items():
            release = self.root / "releases" / tag
            release.mkdir()
            (release / "REVISION").write_text(f"{tag} {commit}\n", encoding="utf-8")
            (release / ".abz-release-ok").touch()
        # A systemctl stand-in: the release named in BAD_RELEASE never gets healthy.
        self.systemctl = tmp / "systemctl"
        self.systemctl.write_text(
            "#!/usr/bin/env bash\n"
            f'echo "$@" >> "{tmp}/systemctl.log"\n'
            f'if [[ $(readlink -e "{self.root}/current") == */"${{BAD_RELEASE:-none}}" ]]; then\n'
            f"  echo '{{\"status\": \"down\"}}' > \"{self.health}\"\n"
            f"else echo '{{\"status\": \"ok\"}}' > \"{self.health}\"; fi\n",
            encoding="utf-8")
        self.systemctl.chmod(0o755)

    @staticmethod
    def git(cwd, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                              cwd=cwd, check=True, capture_output=True, text=True).stdout

    def write_env(self, values: dict, extra: str = ""):
        body = "".join(f"{k}={v}\n" for k, v in values.items()) + extra
        self.env_file.write_text(body, encoding="utf-8")
        self.env_file.chmod(0o600)

    def run(self, script, *args, **env):
        full = dict(os.environ, APP_USER=getpass.getuser(), ABZ_ROOT=str(self.root), ENV_FILE=str(self.env_file),
                    LOG_DIR=str(self.tmp / "log"), SYSTEMCTL=str(self.systemctl),
                    HEALTH_URL=f"file://{self.health}", HEALTH_TRIES="1", **env)
        return subprocess.run(["bash", str(DEPLOY / script), *args], env=full, capture_output=True, text=True)

    def link(self, name):
        target = self.root / name
        return os.path.basename(os.readlink(target)) if target.is_symlink() else None


@needs_bash
@pytest.mark.parametrize("ref", ["master", "hotfix", "v1.2", "1.2.3", "v1.2.3;id", "../v1.2.3"])
def test_deploy_refuses_anything_but_a_release_tag(tmp_path, ref):
    tree = Tree(tmp_path)
    done = tree.run("deploy.sh", ref)
    assert done.returncode != 0
    assert "not a release tag" in done.stderr
    assert tree.link("current") is None and not (tmp_path / "systemctl.log").exists()


@needs_bash
def test_deploy_switches_restarts_and_keeps_the_previous_release(tmp_path):
    tree = Tree(tmp_path)
    assert tree.run("deploy.sh", "v0.0.1").returncode == 0
    assert (tree.link("current"), tree.link("previous")) == ("v0.0.1", None)
    done = tree.run("deploy.sh", "v0.0.2")
    assert done.returncode == 0, done.stderr
    assert (tree.link("current"), tree.link("previous")) == ("v0.0.2", "v0.0.1")
    assert (tmp_path / "systemctl.log").read_text(encoding="utf-8").count("restart abz-chatbot") == 2
    assert "deployed v0.0.2" in (tmp_path / "log" / "deploy.log").read_text(encoding="utf-8")


@needs_bash
def test_a_release_that_fails_its_health_check_is_switched_straight_back(tmp_path):
    tree = Tree(tmp_path)
    assert tree.run("deploy.sh", "v0.0.1").returncode == 0
    done = tree.run("deploy.sh", "v0.0.2", BAD_RELEASE="v0.0.2")
    assert done.returncode != 0
    assert "back on v0.0.1" in done.stderr
    assert tree.link("current") == "v0.0.1"
    assert tree.link("previous") != "v0.0.2"  # rollback.sh must not lead to the failed tag


@needs_bash
def test_deploy_refuses_a_tag_that_moved(tmp_path):
    tree = Tree(tmp_path)
    (tree.root / "releases" / "v0.0.2" / "REVISION").write_text("v0.0.2 " + "0" * 40 + "\n", encoding="utf-8")
    done = tree.run("deploy.sh", "v0.0.2")
    assert done.returncode != 0 and "the tag moved" in done.stderr


@needs_bash
def test_rollback_returns_to_the_previous_release_and_back_again(tmp_path):
    tree = Tree(tmp_path)
    tree.run("deploy.sh", "v0.0.1")
    tree.run("deploy.sh", "v0.0.2")
    assert tree.run("rollback.sh").returncode == 0
    assert (tree.link("current"), tree.link("previous")) == ("v0.0.1", "v0.0.2")
    assert tree.run("rollback.sh").returncode == 0
    assert (tree.link("current"), tree.link("previous")) == ("v0.0.2", "v0.0.1")
    assert tree.run("rollback.sh", "v0.0.2").returncode != 0  # already current
    assert tree.run("rollback.sh", "v9.9.9").returncode != 0  # not on disk


@needs_bash
def test_rollback_takes_a_release_name_never_a_path(tmp_path):
    tree = Tree(tmp_path)
    tree.run("deploy.sh", "v0.0.2")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / ".abz-release-ok").touch()  # looks tested, but is not under releases/
    done = tree.run("rollback.sh", "../../elsewhere")
    assert done.returncode != 0 and "not a release tag" in done.stderr
    assert tree.link("current") == "v0.0.2"


@needs_bash
@pytest.mark.parametrize("problem, message", [
    ("blank", "blank lines for: WA_APP_SECRET"),
    ("missing", "missing: REPLY_KEY"),
    ("mode", "must be chmod 600"),
])
def test_nothing_restarts_with_a_broken_env_file(tmp_path, problem, message):
    tree = Tree(tmp_path)
    values = dict(REQUIRED_ENV)
    if problem == "missing":
        del values["REPLY_KEY"]
    tree.write_env(values, extra="WA_APP_SECRET=\n" if problem == "blank" else "")
    if problem == "mode":
        tree.env_file.chmod(0o644)
    done = tree.run("deploy.sh", "v0.0.1")
    assert done.returncode != 0 and message in done.stderr
    assert not (tmp_path / "systemctl.log").exists()


@needs_bash
def test_env_values_are_read_literally_never_run(tmp_path):
    marker = tmp_path / "ran"
    env_file = tmp_path / "env"
    value = f"a$(touch {marker})b;`touch {marker}`"
    env_file.write_text(f"ADMIN_PASSWORD={value}\n", encoding="utf-8")
    out = subprocess.run(["bash", "-c", f'. "{DEPLOY}/lib.sh"; load_env; printf %s "$ADMIN_PASSWORD"'],
                         env=dict(os.environ, ENV_FILE=str(env_file), LOG_DIR=str(tmp_path)),
                         capture_output=True, text=True, check=True).stdout
    assert out == value
    assert not marker.exists()


def _seed_data(data: Path):
    data.mkdir(parents=True)
    for name in ("audit.db", "sessions.db", "inbox.db"):
        con = sqlite3.connect(data / name)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE t (v TEXT)")
        con.execute("INSERT INTO t VALUES (?)", (name,))
        con.commit()
        con.close()
    (data / "audit.jsonl").write_text("{}\n", encoding="utf-8")
    (data / "reply_key").write_text("generated-by-the-app", encoding="utf-8")


def _backup(tmp_path, **settings):
    conf = tmp_path / "backup.conf"
    # An unknown setting (PATH) must be ignored, not applied.
    conf.write_text("".join(f"{k}={v}\n" for k, v in settings.items()) + "PATH=/nonexistent\n",
                    encoding="utf-8")
    return subprocess.run(["bash", str(DEPLOY / "backup.sh")], env=dict(os.environ, BACKUP_CONF=str(conf)),
                          capture_output=True, text=True)


@needs_sqlite
def test_backup_copies_databases_and_both_keys_off_the_vm(tmp_path):
    data, env_file = tmp_path / "data", tmp_path / "env"
    _seed_data(data)
    env_file.write_text("USER_KEY_SECRET=from-the-env-file\n", encoding="utf-8")
    offsite = tmp_path / "offsite"
    offsite.mkdir()
    done = _backup(tmp_path, DATA_DIR=data, ENV_FILE=env_file, FLAGS_FILE=tmp_path / "none.json",
                   BACKUP_DIR=tmp_path / "backups", OFFSITE_DEST=offsite)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "NOT encrypted" in done.stdout  # no BACKUP_AGE_RECIPIENT in this test
    archives = sorted((tmp_path / "backups").glob("abz-*.tar.gz"))
    assert len(archives) == 1 and (offsite / archives[0].name).exists()
    assert (offsite / (archives[0].name + ".sha256")).exists()
    with tarfile.open(archives[0]) as tar:
        names = {"/".join(Path(n).parts[1:]) for n in tar.getnames()}
    assert {"data/audit.db", "data/sessions.db", "data/inbox.db", "data/audit.jsonl",
            "data/reply_key", "etc/env"} <= names


@needs_sqlite
def test_backup_fails_loudly_without_an_off_vm_copy_or_a_key(tmp_path):
    data, env_file = tmp_path / "data", tmp_path / "env"
    _seed_data(data)
    env_file.write_text("USER_KEY_SECRET=from-the-env-file\n", encoding="utf-8")
    done = _backup(tmp_path, DATA_DIR=data, ENV_FILE=env_file, BACKUP_DIR=tmp_path / "b1")
    assert done.returncode != 0 and "no off-VM copy" in done.stdout
    assert list((tmp_path / "b1").glob("abz-*.tar.gz"))  # the local copy is still written
    (data / "reply_key").unlink()
    done = _backup(tmp_path, DATA_DIR=data, ENV_FILE=env_file, BACKUP_DIR=tmp_path / "b2",
                   OFFSITE_DEST=tmp_path)
    assert done.returncode != 0 and "REPLY_KEY is neither" in done.stdout


@needs_sqlite
def test_restore_puts_the_backup_back_and_keeps_the_live_data(tmp_path):
    tree = Tree(tmp_path)
    data = tmp_path / "live"
    _seed_data(data)
    tree.write_env(dict(REQUIRED_ENV, ABZ_DATA_DIR=str(data)))
    offsite = tmp_path / "offsite"
    offsite.mkdir()
    assert _backup(tmp_path, DATA_DIR=data, ENV_FILE=tree.env_file, BACKUP_DIR=tmp_path / "backups",
                   OFFSITE_DEST=offsite).returncode == 0
    archive = next((tmp_path / "backups").glob("abz-*.tar.gz"))
    con = sqlite3.connect(data / "audit.db")
    con.execute("DELETE FROM t")
    con.commit()
    con.close()
    done = tree.run("restore.sh", str(archive), RESTORE_KEEP_DIR=str(tmp_path))
    assert done.returncode == 0, done.stderr
    con = sqlite3.connect(data / "audit.db")
    assert con.execute("SELECT v FROM t").fetchall() == [("audit.db",)]
    con.close()
    assert list(tmp_path.glob("live.pre-restore-*"))  # never deleted
    assert list(tmp_path.glob("abz-restore-*/env"))   # kept aside, not applied
    log = (tmp_path / "systemctl.log").read_text(encoding="utf-8")
    assert "stop abz-chatbot" in log and "start abz-chatbot" in log

    archive.with_name(archive.name + ".sha256").write_text("0" * 64 + f"  {archive.name}\n", encoding="utf-8")
    done = tree.run("restore.sh", str(archive), RESTORE_KEEP_DIR=str(tmp_path))
    assert done.returncode != 0 and "checksum mismatch" in done.stderr
