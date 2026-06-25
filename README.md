# Image Agent

Image Agent is a first usable release of an agent-assisted neuroimaging
workflow platform. It combines a FastAPI control plane, a React console,
LangGraph-based agent orchestration, curated RAG, workflow preflight checks,
human confirmation, remote Docker execution, task observation, QC review, and
downloadable result bundles for medical imaging research workflows.

The project is designed for local or private-network deployments where the API
server can inspect its Docker runtime, prepare pinned workflow images, run
registered pipelines, and serve structured results to a browser console. It is
research software and is not intended to provide clinical diagnosis.

## Core Capabilities

- Upload and organize DICOM archives, NIfTI files, BIDS sidecars, and related
  imaging inputs.
- Detect project series and expose workflow eligibility for T1, BOLD/fMRI, and
  DWI processing paths.
- Use an Agent workflow path for request understanding, RAG grounding, workflow
  selection, preflight, human confirmation, fingerprint verification, and
  task creation.
- Keep unknown workflow requests in an incubation/proposal lane instead of
  creating production tasks.
- Execute registered workflows with pinned Docker images and deployment-local
  runtime checks.
- Observe long-running tasks through status, events, logs, result summaries,
  artifact manifests, QC artifacts, reports, and export bundles.
- Support Elasticsearch hybrid RAG when configured, combining lexical search,
  dense vector retrieval, and rank fusion over curated workflow and vendor
  references.

## Registered Workflow Families

- **T1 anatomical processing** with the DeepPrep-based fixed workflow.
- **BOLD/fMRI processing** with fMRIPrep and XCP-D report/QC outputs.
- **DWI processing** with the fast GPU DTI workflow and diffusion-derived
  metrics, maps, tables, QC, and report artifacts.

Each registered workflow is represented by structured metadata, including
stable workflow IDs, expected modality, runtime dependencies, primary outputs,
QC outputs, report outputs, limitations, and Agent-selection aliases.

## Architecture

```text
User / Console
    -> FastAPI control plane
    -> LangGraph Agent state machine
    -> RAG and workflow registry
    -> Preflight and confirmation gate
    -> Task service
    -> Docker workflow runner
    -> Result summary, artifact manifest, QC, and reports
```

The Agent is intentionally separated from direct execution. The model can
recommend, explain, and prepare a workflow confirmation, but production task
creation is routed through server-side schema validation, workflow registry
checks, preflight, confirmation fingerprint verification, and the task service.

## Repository Layout

- `apps/api`: FastAPI backend, LangGraph Agent runtime, workflow registry,
  upload handling, task services, runtime probes, artifact manifests, result
  APIs, and runtime helpers.
- `apps/console`: React/Vite console for project upload, Agent interaction,
  workflow approval, task observation, reports, results, and exports.
- `apps/desktop`: desktop-oriented client shell.
- `scripts`: bootstrap, repository hygiene, Docker access, and RAG setup
  utilities.
- `docs/rag`: curated RAG documents, workflow contracts, and vendor references.
- `docs/skills`: Image Agent skill and workflow-runner references.
- `docs/workflows`: selected workflow design notes and public contracts.

Local logs, deployment-specific evidence, `.env` files, databases, generated
outputs, patient data, proxy URLs, credentials, and private server paths are
intentionally excluded from the public repository.

## Quick Start

### Backend

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Console

```bash
cd apps/console
npm install
npm run dev -- --host 0.0.0.0 --port 5180
```

The console defaults to an API on the same host at port `8000`. Configure the
API base through deployment settings or browser-local development settings when
the API runs elsewhere.

## Git-Based Deployment

The repository includes a bootstrap entrypoint for deployment machines. Start
with a dry run:

```bash
python3 scripts/bootstrap_image_agent.py
```

After reviewing the emitted plan, add `--apply` when ready. The bootstrap path
can install dependencies, probe Docker, prepare pinned workflow images,
configure non-secret deployment values, set up a local embedding service, and
configure Elasticsearch hybrid RAG.

For production-style private-network deployment, make the deployment scope and
origins explicit:

```bash
python3 scripts/bootstrap_image_agent.py \
  --production \
  --production-cors-origins https://console.example.org \
  --production-public-base-url https://api.example.org
```

If the API service user cannot access Docker directly, configure host policy
outside the repository, such as Docker group membership or a narrow
non-interactive Docker rule, then point Image Agent at the approved Docker
command through environment configuration.

## RAG and Model Configuration

Image Agent can use an OpenAI-compatible model endpoint for Agent planning and
structured responses:

```bash
IMAGE_AGENT_MODEL_PROVIDER=openai
IMAGE_AGENT_MODEL_BASE_URL=https://api.openai.com/v1
IMAGE_AGENT_MODEL_NAME=<model-name>
IMAGE_AGENT_MODEL_API_KEY=<secret-from-env-or-secret-manager>
IMAGE_AGENT_MODEL_WIRE_API=responses
```

The RAG layer can run with local fallback retrieval for development or with
Elasticsearch hybrid search for deployment. External embedding and model
secrets should be supplied through environment variables, secret managers, or
untracked deployment files.

## Safety Boundaries

- Image Agent is research workflow automation software, not a diagnostic
  medical device.
- Production task creation must go through registered workflow metadata,
  preflight, confirmation, and fingerprint verification.
- Unknown workflow ideas remain proposal-only until promoted through explicit
  validation and review.
- Observe/repair behavior is read-only by default and must not automatically
  rerun production tasks.
- API keys, proxy URLs, generated `.env` files, patient data, runtime logs,
  acceptance transcripts, local server addresses, and generated imaging outputs
  should never be committed.

## License

This project is released under the MIT License. See `LICENSE` for details.
