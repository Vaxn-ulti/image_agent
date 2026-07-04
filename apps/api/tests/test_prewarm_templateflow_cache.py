import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "prewarm_templateflow_cache.py"
PROXY_ENV_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "no_proxy", "all_proxy")


def _load_script():
    spec = importlib.util.spec_from_file_location("prewarm_templateflow_cache", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _clear_proxy_env(monkeypatch):
    for name in PROXY_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_prewarm_plan_uses_pinned_fmriprep_and_shared_templateflow_cache(tmp_path):
    script = _load_script()

    plan = script.build_prewarm_plan(
        templateflow_home=tmp_path / "templateflow",
        image="nipreps/fmriprep:25.2.5",
        templates=["MNI152NLin2009cAsym", "MNI152NLin6Asym"],
        env_file=tmp_path / ".env",
        apply_changes=False,
    )

    serialized = json.dumps(plan, sort_keys=True)
    assert plan["plan_id"] == "templateflow_cache_prewarm_v1"
    assert plan["mode"] == "dry_run"
    assert plan["image"] == "nipreps/fmriprep:25.2.5"
    assert "latest" not in serialized
    assert "MNI152NLin2009cAsym" in serialized
    assert "MNI152NLin6Asym" in serialized
    assert "IMAGE_AGENT_TEMPLATEFLOW_HOME" in serialized
    assert "TEMPLATEFLOW_HOME=/templateflow" in serialized
    assert "--entrypoint" in plan["command"]
    assert "python" in plan["command"]
    assert plan["command"].index("--entrypoint") < plan["command"].index("nipreps/fmriprep:25.2.5")
    assert "sk-" not in serialized


def test_prewarm_defaults_include_oasis_for_fmriprep_brain_extraction(tmp_path):
    script = _load_script()

    plan = script.build_prewarm_plan(
        templateflow_home=tmp_path / "templateflow",
        image="nipreps/fmriprep:25.2.5",
        templates=list(script.DEFAULT_TEMPLATES),
        env_file=tmp_path / ".env",
        apply_changes=False,
        download_method="curl",
    )

    serialized = json.dumps(plan, sort_keys=True)
    assert "OASIS30ANTs" in plan["templates"]
    assert "tpl-MNI152NLin2009cAsym_res-02_desc-fMRIPrep_boldref.nii.gz" in serialized
    assert "tpl-MNI152NLin2009cAsym_res-01_label-brain_probseg.nii.gz" in serialized
    assert "tpl-MNI152NLin2009cAsym_res-01_desc-carpet_dseg.nii.gz" in serialized
    assert "tpl-MNI152NLin2009cAsym_from-MNI152NLin6Asym_mode-image_xfm.h5" in serialized
    assert "tpl-MNI152NLin6Asym_from-MNI152NLin2009cAsym_mode-image_xfm.h5" in serialized
    assert "tpl-OASIS30ANTs_res-01_T1w.nii.gz" in serialized
    assert "tpl-OASIS30ANTs_res-01_desc-brain_T1w.nii.gz" in serialized
    assert "tpl-OASIS30ANTs_res-01_desc-brain_mask.nii.gz" in serialized
    assert "tpl-OASIS30ANTs_res-02_T1w.nii.gz" not in serialized


def test_prewarm_plan_uses_targeted_templateflow_queries_instead_of_whole_archive(tmp_path):
    script = _load_script()

    plan = script.build_prewarm_plan(
        templateflow_home=tmp_path / "templateflow",
        image="nipreps/fmriprep:25.2.5",
        templates=["MNI152NLin6Asym"],
        env_file=tmp_path / ".env",
        apply_changes=False,
    )

    python_snippet = plan["command"][-1]
    assert "tflow.get(template" in python_snippet
    assert "'suffix': 'T1w'" in python_snippet
    assert "'desc': 'brain'" in python_snippet
    assert "'suffix': 'mask'" in python_snippet
    assert "IMAGE_AGENT_TEMPLATEFLOW_REQUEST_TIMEOUT" in python_snippet
    assert "get([" not in python_snippet


def test_prewarm_apply_writes_env_and_runs_docker_without_secret_in_report(tmp_path, monkeypatch):
    script = _load_script()
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Proc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-token")

    report = script.prewarm_templateflow_cache(
        templateflow_home=tmp_path / "templateflow",
        image="nipreps/fmriprep:25.2.5",
        templates=["MNI152NLin2009cAsym"],
        env_file=tmp_path / ".env",
        apply_changes=True,
    )

    assert report["status"] == "completed"
    assert calls
    assert "docker" in calls[0]
    assert "nipreps/fmriprep:25.2.5" in calls[0]
    assert "MNI152NLin2009cAsym" in " ".join(calls[0])
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "IMAGE_AGENT_TEMPLATEFLOW_HOME=" in env_text
    assert "test-openai-token" not in json.dumps(report, sort_keys=True)


def test_prewarm_apply_retries_failed_downloads_without_proxy_values_in_report(tmp_path, monkeypatch):
    script = _load_script()
    calls = []
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:19081")

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))

        class Proc:
            stdout = ""
            stderr = "requests.exceptions.ReadTimeout: proxy http://127.0.0.1:19081"

            @property
            def returncode(self):
                return 1 if len(calls) == 1 else 0

        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)

    report = script.prewarm_templateflow_cache(
        templateflow_home=tmp_path / "templateflow",
        image="nipreps/fmriprep:25.2.5",
        templates=["MNI152NLin2009cAsym"],
        env_file=tmp_path / ".env",
        apply_changes=True,
        attempts=2,
    )

    assert report["status"] == "completed"
    assert len(calls) == 2
    assert "127.0.0.1:19081" not in json.dumps(report, sort_keys=True)


def test_prewarm_curl_method_uses_direct_resumable_template_downloads(tmp_path, monkeypatch):
    script = _load_script()
    _clear_proxy_env(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:19081")

    plan = script.build_prewarm_plan(
        templateflow_home=tmp_path / "templateflow",
        image="nipreps/fmriprep:25.2.5",
        templates=["MNI152NLin6Asym"],
        env_file=tmp_path / ".env",
        apply_changes=False,
        download_method="curl",
        direct_download=True,
    )

    serialized = json.dumps(plan, sort_keys=True)
    assert plan["download_method"] == "curl"
    assert plan["direct_download"] is True
    assert plan["curl_commands"]
    assert "templateflow.s3.amazonaws.com/tpl-MNI152NLin6Asym" in serialized
    assert "-C" in plan["curl_commands"][0]
    assert "127.0.0.1:19081" not in serialized


def test_prewarm_curl_method_apply_unsets_proxy_values_for_direct_download(tmp_path, monkeypatch):
    script = _load_script()
    _clear_proxy_env(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:19081")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))

        class Proc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)

    report = script.prewarm_templateflow_cache(
        templateflow_home=tmp_path / "templateflow",
        image="nipreps/fmriprep:25.2.5",
        templates=["MNI152NLin6Asym"],
        env_file=tmp_path / ".env",
        apply_changes=True,
        download_method="curl",
        direct_download=True,
    )

    assert report["status"] == "completed"
    assert calls
    assert all("HTTPS_PROXY" not in kwargs["env"] for _cmd, kwargs in calls)
    assert "127.0.0.1:19081" not in json.dumps(report, sort_keys=True)


def test_prewarm_curl_method_skips_existing_nonempty_files(tmp_path, monkeypatch):
    script = _load_script()
    calls = []
    existing = tmp_path / "templateflow" / "tpl-OASIS30ANTs" / "tpl-OASIS30ANTs_res-01_T1w.nii.gz"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"already-present")

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Proc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)

    report = script.prewarm_templateflow_cache(
        templateflow_home=tmp_path / "templateflow",
        image="nipreps/fmriprep:25.2.5",
        templates=["OASIS30ANTs"],
        env_file=tmp_path / ".env",
        apply_changes=True,
        download_method="curl",
        direct_download=True,
    )

    serialized_calls = json.dumps(calls, sort_keys=True)
    assert report["status"] == "completed"
    assert report["skipped_existing_files"] == 1
    assert "tpl-OASIS30ANTs_res-01_T1w.nii.gz" not in serialized_calls
    assert "tpl-OASIS30ANTs_res-01_desc-brain_T1w.nii.gz" in serialized_calls


def test_prewarm_apply_passes_sudo_password_to_configured_docker_command_without_report(tmp_path, monkeypatch):
    script = _load_script()
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("input")))

        class Proc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)
    monkeypatch.setenv("IMAGE_AGENT_DOCKER_COMMAND", "sudo -S docker")
    monkeypatch.setenv("IMAGE_AGENT_SUDO_PASSWORD", "test-sudo-password")

    report = script.prewarm_templateflow_cache(
        templateflow_home=tmp_path / "templateflow",
        image="nipreps/fmriprep:25.2.5",
        templates=["MNI152NLin2009cAsym"],
        env_file=tmp_path / ".env",
        apply_changes=True,
    )

    assert calls[0][0][:4] == ["sudo", "-S", "docker", "run"]
    assert calls[0][1] == "test-sudo-password\n"
    assert "test-sudo-password" not in json.dumps(report, sort_keys=True)


def test_prewarm_plan_respects_configured_docker_command_without_secret_values(tmp_path, monkeypatch):
    script = _load_script()
    monkeypatch.setenv("IMAGE_AGENT_DOCKER_COMMAND", "sudo -n docker")

    plan = script.build_prewarm_plan(
        templateflow_home=tmp_path / "templateflow",
        image="nipreps/fmriprep:25.2.5",
        templates=["MNI152NLin2009cAsym"],
        env_file=tmp_path / ".env",
        apply_changes=False,
    )

    assert plan["command"][:4] == ["sudo", "-n", "docker", "run"]
    assert "IMAGE_AGENT_DOCKER_COMMAND" in plan["runtime_configuration"]
    assert "password" not in json.dumps(plan, sort_keys=True).lower()


def test_prewarm_can_forward_runtime_proxy_env_names_without_values(tmp_path, monkeypatch):
    script = _load_script()
    _clear_proxy_env(monkeypatch)
    proxy_value = "http://127.0.0.1:19081"
    monkeypatch.setenv("HTTP_PROXY", proxy_value)

    plan = script.build_prewarm_plan(
        templateflow_home=tmp_path / "templateflow",
        image="nipreps/fmriprep:25.2.5",
        templates=["MNI152NLin2009cAsym"],
        env_file=tmp_path / ".env",
        apply_changes=False,
        forward_proxy_env=True,
    )

    serialized = json.dumps(plan, sort_keys=True)
    assert "-e HTTP_PROXY" in plan["command_preview"]
    assert proxy_value not in serialized
    assert plan["container_proxy_forwarding"]["enabled"] is True
    assert "HTTP_PROXY" in plan["container_proxy_forwarding"]["environment_names"]


def test_prewarm_bridge_rewrites_loopback_proxy_for_container_without_report_values(tmp_path, monkeypatch):
    script = _load_script()
    _clear_proxy_env(monkeypatch)
    proxy_value = "http://127.0.0.1:19081"
    monkeypatch.setenv("HTTP_PROXY", proxy_value)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))

        class Proc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)

    report = script.prewarm_templateflow_cache(
        templateflow_home=tmp_path / "templateflow",
        image="nipreps/fmriprep:25.2.5",
        templates=["MNI152NLin2009cAsym"],
        env_file=tmp_path / ".env",
        apply_changes=True,
        forward_proxy_env=True,
    )

    cmd, kwargs = calls[0]
    serialized = json.dumps(report, sort_keys=True)
    assert "--add-host" in cmd
    assert "host.docker.internal:host-gateway" in cmd
    assert "-e" in cmd
    assert "HTTP_PROXY" in cmd
    assert kwargs["env"]["HTTP_PROXY"] == "http://host.docker.internal:19081"
    assert proxy_value not in serialized
    assert "host.docker.internal:19081" not in serialized


def test_prewarm_host_network_keeps_proxy_env_values_out_of_reports(tmp_path, monkeypatch):
    script = _load_script()
    _clear_proxy_env(monkeypatch)
    proxy_value = "http://127.0.0.1:19081"
    monkeypatch.setenv("HTTP_PROXY", proxy_value)

    plan = script.build_prewarm_plan(
        templateflow_home=tmp_path / "templateflow",
        image="nipreps/fmriprep:25.2.5",
        templates=["MNI152NLin2009cAsym"],
        env_file=tmp_path / ".env",
        apply_changes=False,
        forward_proxy_env=True,
        network_mode="host",
    )

    serialized = json.dumps(plan, sort_keys=True)
    assert "--network host" in plan["command_preview"]
    assert "--add-host" not in plan["command"]
    assert proxy_value not in serialized
    assert plan["container_proxy_forwarding"]["uses_host_gateway"] is False


def test_prewarm_rejects_latest_or_unpinned_images(tmp_path):
    script = _load_script()

    for image in ["nipreps/fmriprep:latest", "nipreps/fmriprep"]:
        try:
            script.build_prewarm_plan(
                templateflow_home=tmp_path / "templateflow",
                image=image,
                templates=["MNI152NLin2009cAsym"],
                env_file=tmp_path / ".env",
                apply_changes=False,
            )
        except SystemExit as exc:
            assert "version-pinned" in str(exc)
        else:
            raise AssertionError(f"expected {image} to be rejected")
