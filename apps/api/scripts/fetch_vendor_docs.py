from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


DEFAULT_SOURCES: list[dict[str, str]] = [
    {
        "id": "fmriprep_usage",
        "vendor_doc": "fmriprep_official_container_usage.md",
        "url": "https://fmriprep.org/en/stable/usage.html",
        "file": "fmriprep_usage.html",
        "source_type": "official_docs",
    },
    {
        "id": "fmriprep_installation",
        "vendor_doc": "fmriprep_official_container_usage.md",
        "url": "https://fmriprep.org/en/stable/installation.html",
        "file": "fmriprep_installation.html",
        "source_type": "official_docs",
    },
    {
        "id": "fmriprep_outputs",
        "vendor_doc": "fmriprep_official_outputs.md",
        "url": "https://fmriprep.org/en/stable/outputs.html",
        "file": "fmriprep_outputs.html",
        "source_type": "official_docs",
    },
    {
        "id": "xcp_d_usage",
        "vendor_doc": "xcp_d_official_container_usage.md",
        "url": "https://xcp-d.readthedocs.io/en/stable/usage.html",
        "file": "xcp_d_usage.html",
        "source_type": "official_docs",
    },
    {
        "id": "xcp_d_installation",
        "vendor_doc": "xcp_d_official_container_usage.md",
        "url": "https://xcp-d.readthedocs.io/en/stable/installation.html",
        "file": "xcp_d_installation.html",
        "source_type": "official_docs",
    },
    {
        "id": "xcp_d_outputs",
        "vendor_doc": "xcp_d_official_outputs.md",
        "url": "https://xcp-d.readthedocs.io/en/stable/outputs.html",
        "file": "xcp_d_outputs.html",
        "source_type": "official_docs",
    },
    {
        "id": "mriqc_usage",
        "vendor_doc": "mriqc_official_container_usage_outputs.md",
        "url": "https://mriqc.readthedocs.io/en/latest/usage.html",
        "file": "mriqc_usage.html",
        "source_type": "official_docs",
    },
    {
        "id": "mriqc_reports",
        "vendor_doc": "mriqc_official_container_usage_outputs.md",
        "url": "https://mriqc.readthedocs.io/en/latest/reports.html",
        "file": "mriqc_reports.html",
        "source_type": "official_docs",
    },
    {
        "id": "mriqc_installation",
        "vendor_doc": "mriqc_official_container_usage_outputs.md",
        "url": "https://mriqc.readthedocs.io/en/latest/install.html",
        "file": "mriqc_installation.html",
        "source_type": "official_docs",
    },
    {
        "id": "nipreps_docker_guidelines",
        "vendor_doc": "mriqc_official_container_usage_outputs.md",
        "url": "https://www.nipreps.org/apps/docker/",
        "file": "nipreps_docker_guidelines.html",
        "source_type": "official_docs",
    },
    {
        "id": "nipreps_singularity_guidelines",
        "vendor_doc": "mriqc_official_container_usage_outputs.md",
        "url": "https://www.nipreps.org/apps/singularity/",
        "file": "nipreps_singularity_guidelines.html",
        "source_type": "official_docs",
    },
    {
        "id": "qsiprep_usage",
        "vendor_doc": "qsiprep_official_container_usage_outputs.md",
        "url": "https://qsiprep.readthedocs.io/en/stable/usage.html",
        "file": "qsiprep_usage.html",
        "source_type": "official_docs",
    },
    {
        "id": "qsiprep_preprocessing_outputs",
        "vendor_doc": "qsiprep_official_container_usage_outputs.md",
        "url": "https://qsiprep.readthedocs.io/en/stable/preprocessing.html",
        "file": "qsiprep_preprocessing.html",
        "source_type": "official_docs",
    },
    {
        "id": "qsirecon_quickstart",
        "vendor_doc": "qsirecon_official_container_usage_workflows.md",
        "url": "https://qsirecon.readthedocs.io/en/stable/quickstart.html",
        "file": "qsirecon_quickstart.html",
        "source_type": "official_docs",
    },
    {
        "id": "qsirecon_builtin_workflows",
        "vendor_doc": "qsirecon_official_container_usage_workflows.md",
        "url": "https://qsirecon.readthedocs.io/en/stable/builtin_workflows.html",
        "file": "qsirecon_builtin_workflows.html",
        "source_type": "official_docs",
    },
    {
        "id": "qsirecon_custom_workflows",
        "vendor_doc": "qsirecon_official_container_usage_workflows.md",
        "url": "https://qsirecon.readthedocs.io/en/stable/building_workflows.html",
        "file": "qsirecon_custom_workflows.html",
        "source_type": "official_docs",
    },
    {
        "id": "fsl_eddy_users_guide",
        "vendor_doc": "fsl_official_fast_dti_tools.md",
        "url": "https://fsl.fmrib.ox.ac.uk/fsl/docs/diffusion/eddy/users_guide/index.html",
        "file": "fsl_eddy_users_guide.html",
        "source_type": "official_docs",
    },
    {
        "id": "fsl_dtifit",
        "vendor_doc": "fsl_official_fast_dti_tools.md",
        "url": "https://fsl.fmrib.ox.ac.uk/fsl/docs/diffusion/dtifit.html",
        "file": "fsl_dtifit.html",
        "source_type": "official_docs",
    },
    {
        "id": "fsl_flirt_user_guide",
        "vendor_doc": "fsl_official_fast_dti_tools.md",
        "url": "https://fsl.fmrib.ox.ac.uk/fsl/docs/registration/flirt/user_guide.html",
        "file": "fsl_flirt_user_guide.html",
        "source_type": "official_docs",
    },
    {
        "id": "fsl_fnirt_user_guide",
        "vendor_doc": "fsl_official_fast_dti_tools.md",
        "url": "https://fsl.fmrib.ox.ac.uk/fsl/docs/registration/fnirt/user_guide.html",
        "file": "fsl_fnirt_user_guide.html",
        "source_type": "official_docs",
    },
    {
        "id": "fsl_utils",
        "vendor_doc": "fsl_official_fast_dti_tools.md",
        "url": "https://fsl.fmrib.ox.ac.uk/fsl/docs/utilities/fslutils.html",
        "file": "fsl_utils.html",
        "source_type": "official_docs",
    },
    {
        "id": "mrtrix3_mrinfo",
        "vendor_doc": "mrtrix3_official_dti_toolbox.md",
        "url": "https://userdocs.mrtrix.org/en/latest/reference/commands/mrinfo.html",
        "file": "mrtrix3_mrinfo.html",
        "source_type": "official_docs",
    },
    {
        "id": "mrtrix3_dwi2mask",
        "vendor_doc": "mrtrix3_official_dti_toolbox.md",
        "url": "https://userdocs.mrtrix.org/en/latest/reference/commands/dwi2mask.html",
        "file": "mrtrix3_dwi2mask.html",
        "source_type": "official_docs",
    },
    {
        "id": "mrtrix3_mrconvert",
        "vendor_doc": "mrtrix3_official_dti_toolbox.md",
        "url": "https://userdocs.mrtrix.org/en/latest/reference/commands/mrconvert.html",
        "file": "mrtrix3_mrconvert.html",
        "source_type": "official_docs",
    },
    {
        "id": "mrtrix3_dwi2tensor",
        "vendor_doc": "mrtrix3_official_dti_toolbox.md",
        "url": "https://userdocs.mrtrix.org/en/latest/reference/commands/dwi2tensor.html",
        "file": "mrtrix3_dwi2tensor.html",
        "source_type": "official_docs",
    },
    {
        "id": "mrtrix3_tensor2metric",
        "vendor_doc": "mrtrix3_official_dti_toolbox.md",
        "url": "https://userdocs.mrtrix.org/en/latest/reference/commands/tensor2metric.html",
        "file": "mrtrix3_tensor2metric.html",
        "source_type": "official_docs",
    },
    {
        "id": "mrtrix3_mrstats",
        "vendor_doc": "mrtrix3_official_dti_toolbox.md",
        "url": "https://userdocs.mrtrix.org/en/latest/reference/commands/mrstats.html",
        "file": "mrtrix3_mrstats.html",
        "source_type": "official_docs",
    },
    {
        "id": "mrtrix3_mrcalc",
        "vendor_doc": "mrtrix3_official_dti_toolbox.md",
        "url": "https://userdocs.mrtrix.org/en/latest/reference/commands/mrcalc.html",
        "file": "mrtrix3_mrcalc.html",
        "source_type": "official_docs",
    },
    {
        "id": "deepprep_outputs",
        "vendor_doc": "deepprep_official_container_usage.md",
        "url": "https://deepprep.readthedocs.io/en/latest/outputs.html",
        "file": "deepprep_outputs.html",
        "source_type": "official_docs",
    },
    {
        "id": "deepprep_usage_local",
        "vendor_doc": "deepprep_official_container_usage.md",
        "url": "https://deepprep.readthedocs.io/en/24.1.0/usage_local.html",
        "file": "deepprep_usage_local.html",
        "source_type": "official_docs",
    },
    {
        "id": "deepprep_usage_cluster",
        "vendor_doc": "deepprep_official_container_usage.md",
        "url": "https://deepprep.readthedocs.io/en/latest/usage_cluster.html",
        "file": "deepprep_usage_cluster.html",
        "source_type": "official_docs",
    },
    {
        "id": "freesurfer_recon_all",
        "vendor_doc": "freesurfer_official_container_reconall.md",
        "url": "https://surfer.nmr.mgh.harvard.edu/fswiki/recon-all",
        "file": "freesurfer_recon_all.html",
        "source_type": "official_wiki",
    },
    {
        "id": "freesurfer_recon_all_outputs",
        "vendor_doc": "freesurfer_official_container_reconall.md",
        "url": "https://surfer.nmr.mgh.harvard.edu/fswiki/ReconAllOutputFiles",
        "file": "freesurfer_recon_all_outputs.html",
        "source_type": "official_wiki",
    },
    {
        "id": "freesurfer_license_registration",
        "vendor_doc": "freesurfer_official_license.md",
        "url": "https://surfer.nmr.mgh.harvard.edu/registration.html",
        "file": "freesurfer_license_registration.html",
        "source_type": "official_docs",
    },
    {
        "id": "bids_validator_cli",
        "vendor_doc": "bids_validator_official_cli_docker.md",
        "url": "https://bids-validator.readthedocs.io/en/latest/user_guide/command-line.html",
        "file": "bids_validator_cli.html",
        "source_type": "official_docs",
    },
    {
        "id": "bids_validator_docker",
        "vendor_doc": "bids_validator_official_cli_docker.md",
        "url": "https://hub.docker.com/r/bids/validator",
        "file": "bids_validator_docker.html",
        "source_type": "official_container_registry",
    },
    {
        "id": "dcm2niix_readme",
        "vendor_doc": "dcm2niix_official_conversion.md",
        "url": "https://raw.githubusercontent.com/rordenlab/dcm2niix/master/README.md",
        "file": "dcm2niix_readme.md",
        "source_type": "official_repository",
    },
    {
        "id": "dpabi_home",
        "vendor_doc": "dpabi_official_container_boundary.md",
        "url": "https://rfmri.org/DPABI",
        "file": "dpabi_home.html",
        "source_type": "official_docs",
    },
    {
        "id": "dpabi_standalone_docker",
        "vendor_doc": "dpabi_official_container_boundary.md",
        "url": "https://rfmri.org/content/dpabidpabisurfdparsf-stand-alone-version",
        "file": "dpabi_standalone_docker.html",
        "source_type": "official_docs",
    },
    {
        "id": "dpabisurfslurm_hpc_singularity",
        "vendor_doc": "dpabi_official_container_boundary.md",
        "url": "https://rfmri.org/DPABISurfSlurm",
        "file": "dpabisurfslurm_hpc_singularity.html",
        "source_type": "official_docs",
    },
    {
        "id": "dpabi_github_repo",
        "vendor_doc": "dpabi_official_container_boundary.md",
        "url": "https://github.com/Chaogan-Yan/DPABI",
        "file": "dpabi_github_repo.html",
        "source_type": "official_repository",
    },
    {
        "id": "dpabi_dockerfile",
        "vendor_doc": "dpabi_official_container_boundary.md",
        "url": "https://raw.githubusercontent.com/Chaogan-Yan/DPABI/master/Dockerfile",
        "file": "dpabi_dockerfile",
        "source_type": "official_repository",
    },
    {
        "id": "dpabi_docker_hub",
        "vendor_doc": "dpabi_official_container_boundary.md",
        "url": "https://hub.docker.com/v2/repositories/cgyan/dpabi/",
        "file": "dpabi_docker_hub.json",
        "source_type": "official_container_registry",
    },
    {
        "id": "bids_mri",
        "vendor_doc": "bids_official_mri_derivatives.md",
        "url": "https://bids-specification.readthedocs.io/en/stable/modality-specific-files/magnetic-resonance-imaging-data.html",
        "file": "bids_mri.html",
        "source_type": "official_docs",
    },
    {
        "id": "bids_derivatives",
        "vendor_doc": "bids_official_mri_derivatives.md",
        "url": "https://bids-specification.readthedocs.io/en/stable/derivatives/introduction.html",
        "file": "bids_derivatives.html",
        "source_type": "official_docs",
    },
    {
        "id": "templateflow_installation",
        "vendor_doc": "templateflow_official_cache_archive_client.md",
        "url": "https://www.templateflow.org/python-client/master/installation.html",
        "file": "templateflow_installation.html",
        "source_type": "official_docs",
    },
    {
        "id": "templateflow_archive",
        "vendor_doc": "templateflow_official_cache_archive_client.md",
        "url": "https://github.com/templateflow/templateflow",
        "file": "templateflow_archive.html",
        "source_type": "official_repository",
    },
    {
        "id": "docker_image_inspect",
        "vendor_doc": "docker_official_image_inspect.md",
        "url": "https://docs.docker.com/reference/cli/docker/image/inspect/",
        "file": "docker_image_inspect.html",
        "source_type": "official_docs",
    },
    {
        "id": "podman_image_inspect",
        "vendor_doc": "podman_official_image_inspect.md",
        "url": "https://docs.podman.io/en/latest/markdown/podman-image-inspect.1.html",
        "file": "podman_image_inspect.html",
        "source_type": "official_docs",
    },
    {
        "id": "singularityce_inspect",
        "vendor_doc": "singularity_apptainer_official_inspect.md",
        "url": "https://docs.sylabs.io/guides/latest/user-guide/cli/singularity_inspect.html",
        "file": "singularityce_inspect.html",
        "source_type": "official_docs",
    },
    {
        "id": "apptainer_inspect",
        "vendor_doc": "singularity_apptainer_official_inspect.md",
        "url": "https://apptainer.org/docs/user/latest/cli/apptainer_inspect.html",
        "file": "apptainer_inspect.html",
        "source_type": "official_docs",
    },
    {
        "id": "openai_function_calling_responses",
        "vendor_doc": "openai_official_responses_function_tools.md",
        "url": "https://platform.openai.com/docs/guides/function-calling?api-mode=responses",
        "file": "openai_function_calling_responses.html",
        "source_type": "official_docs",
    },
    {
        "id": "openai_tools_responses",
        "vendor_doc": "openai_official_responses_function_tools.md",
        "url": "https://platform.openai.com/docs/guides/tools?api-mode=responses",
        "file": "openai_tools_responses.html",
        "source_type": "official_docs",
    },
    {
        "id": "openai_python_sdk_readme",
        "vendor_doc": "openai_official_responses_function_tools.md",
        "url": "https://raw.githubusercontent.com/openai/openai-python/main/README.md",
        "file": "openai_python_sdk_readme.md",
        "source_type": "official_repository",
    },
    {
        "id": "openai_responses_api_reference",
        "vendor_doc": "openai_official_responses_function_tools.md",
        "url": "https://developers.openai.com/api/docs/api-reference/responses/create",
        "file": "openai_responses_api_reference.html",
        "source_type": "official_docs",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_url(url: str, *, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "image-agent-rag-curator/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_with_retries(
    url: str,
    *,
    fetcher: Callable[[str], bytes],
    retry_attempts: int,
    retry_delay_seconds: float,
) -> bytes:
    attempts = max(1, retry_attempts)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fetcher(url)
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                break
            if retry_delay_seconds > 0:
                time.sleep(retry_delay_seconds)
    raise RuntimeError(f"Could not download official source after {attempts} attempts: {url}: {last_error}") from last_error


def download_vendor_sources(
    *,
    raw_root: Path | str,
    sources: list[dict[str, str]] | None = None,
    fetch_bytes: Callable[[str], bytes] | None = None,
    generated_at: str | None = None,
    retrieved_at: str | None = None,
    fetch_timeout_seconds: int = 60,
    retry_attempts: int = 3,
    retry_delay_seconds: float = 2.0,
    use_existing_on_failure: bool = False,
    merge_existing_manifest: bool = False,
) -> dict[str, Any]:
    root = Path(raw_root)
    root.mkdir(parents=True, exist_ok=True)
    fetcher = fetch_bytes or (lambda url: fetch_url(url, timeout=fetch_timeout_seconds))
    manifest_sources = []
    generated = generated_at or utc_now()
    for source in sources or DEFAULT_SOURCES:
        target = root / source["file"]
        download_mode = "fresh_download"
        fetch_error = None
        try:
            data = fetch_with_retries(
                source["url"],
                fetcher=fetcher,
                retry_attempts=retry_attempts,
                retry_delay_seconds=retry_delay_seconds,
            )
            target.write_bytes(data)
        except Exception as exc:
            if not use_existing_on_failure or not target.exists():
                raise
            data = target.read_bytes()
            download_mode = "existing_snapshot_after_fetch_error"
            fetch_error = str(exc)
        manifest_sources.append(
            {
                "id": source["id"],
                "vendor_doc": source["vendor_doc"],
                "url": source["url"],
                "file": source["file"],
                "source_type": source["source_type"],
                "retrieved_at": retrieved_at or utc_now(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "status": "downloaded",
                "download_mode": download_mode,
                **({"fetch_error": fetch_error} if fetch_error else {}),
            }
        )
    if merge_existing_manifest:
        manifest_path = root / "manifest.json"
        if manifest_path.exists():
            existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            updated_ids = {source["id"] for source in manifest_sources}
            manifest_sources = [
                source for source in existing_manifest.get("sources", []) if source.get("id") not in updated_ids
            ] + manifest_sources
    manifest = {
        "schema_version": 1,
        "generated_at": generated,
        "note": "Raw official source snapshots for curated vendor RAG summaries. Do not index wholesale; use as traceable source evidence.",
        "sources": manifest_sources,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Download official vendor docs for Image Agent RAG traceability.")
    parser.add_argument(
        "--raw-root",
        default=str(Path(__file__).resolve().parents[3] / "docs" / "rag" / "vendor" / "raw-sources"),
        help="Directory for raw source snapshots and manifest.json.",
    )
    parser.add_argument("--retry-attempts", type=int, default=3, help="Attempts per official URL before failing.")
    parser.add_argument("--fetch-timeout-seconds", type=int, default=60, help="Timeout for each official URL fetch attempt.")
    parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=2.0,
        help="Delay between retry attempts for transient official-doc download errors.",
    )
    parser.add_argument(
        "--use-existing-on-failure",
        action="store_true",
        help="If all retry attempts fail for a source, preserve an existing raw snapshot and record the fetch error.",
    )
    parser.add_argument(
        "--merge-existing-manifest",
        action="store_true",
        help="Keep existing manifest entries for sources not downloaded in this invocation.",
    )
    parser.add_argument(
        "--source-id",
        action="append",
        default=[],
        help="Download only the selected source id. May be repeated.",
    )
    args = parser.parse_args()
    selected_sources = DEFAULT_SOURCES
    if args.source_id:
        selected_ids = set(args.source_id)
        selected_sources = [source for source in DEFAULT_SOURCES if source["id"] in selected_ids]
        missing_ids = selected_ids - {source["id"] for source in selected_sources}
        if missing_ids:
            parser.error(f"Unknown source id(s): {', '.join(sorted(missing_ids))}")
    manifest = download_vendor_sources(
        raw_root=args.raw_root,
        sources=selected_sources,
        fetch_timeout_seconds=args.fetch_timeout_seconds,
        retry_attempts=args.retry_attempts,
        retry_delay_seconds=args.retry_delay_seconds,
        use_existing_on_failure=args.use_existing_on_failure,
        merge_existing_manifest=args.merge_existing_manifest,
    )
    print(json.dumps({"raw_root": args.raw_root, "source_count": len(manifest["sources"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
