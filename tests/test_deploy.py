"""P7: production hosting -- deploy/ files and the settings they rely on."""

import json
import os
import subprocess
import sys
from pathlib import Path

from app import config

ROOT = Path(__file__).resolve().parent.parent


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
