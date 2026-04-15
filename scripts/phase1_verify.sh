#!/usr/bin/env bash
# =============================================================================
# phase1_verify.sh — Phase 1 safety harness verification script
#
# Encodes the complete validated Phase 1 command sequence:
#   reset → baseline (demo_dataset_v1) → companion isolation (demo_dataset_v2)
#   → artifact capture
#
# Canonical documentation:
#   docs/repository_restructure/repository_restructure_phase1_execution_run_log.md
#   docs/repository_restructure/repository_restructure_safety_harness.md (§9.6, §9.7)
#
# Usage:
#   make phase1-verify
#   # or directly:
#   bash scripts/phase1_verify.sh
#
# Required environment variables (must be set before running):
#   OPENAI_API_KEY    — OpenAI credentials
#   NEO4J_PASSWORD    — Neo4j credentials
#
# Optional environment variables:
#   NEO4J_URI         — defaults to neo4j://localhost:7687
#   OPENAI_MODEL      — must be gpt-5.4 or unset (default). Any other value aborts.
#
# Prerequisites:
#   - Neo4j running (docker compose up -d neo4j)
#   - .venv with Python 3.11+ (python3.11 -m venv .venv && pip install -e .)
#   - Fixture datasets present in demo/fixtures/datasets/
#
# Artifacts written to:
#   artifacts/repository_restructure/phase1/<YYYYMMDD-HHMMSS>/
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${REPO_ROOT}/.venv/bin/python"
RUNS_DIR="${REPO_ROOT}/demo/artifacts/runs"
ARTIFACTS_BASE="${REPO_ROOT}/artifacts/repository_restructure/phase1"
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
ARTIFACT_DIR="${ARTIFACTS_BASE}/${RUN_TS}"
LOG_DIR="${ARTIFACT_DIR}/logs"
MANIFEST_DIR="${ARTIFACT_DIR}/manifests"

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
log()  { echo "[phase1_verify] $*"; }
die()  { echo "[phase1_verify] ERROR: $*" >&2; exit 1; }
step() { echo; echo "[phase1_verify] ======================================================"; echo "[phase1_verify] $*"; echo "[phase1_verify] ======================================================"; }

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------
step "Preflight checks"

[[ -x "${PYTHON}" ]] || die ".venv/bin/python not found at ${PYTHON}. Run: python3.11 -m venv .venv && pip install -e ."

PY_MAJOR="$("${PYTHON}" -c 'import sys; print(sys.version_info.major)')"
PY_MINOR="$("${PYTHON}" -c 'import sys; print(sys.version_info.minor)')"
if [[ "${PY_MAJOR}" -lt 3 ]] || { [[ "${PY_MAJOR}" -eq 3 ]] && [[ "${PY_MINOR}" -lt 11 ]]; }; then
    PY_VERSION="$("${PYTHON}" --version 2>&1)"
    die "Python 3.11+ required. Found: ${PY_VERSION}  Set up a new .venv: python3.11 -m venv .venv"
fi
log "Python: $("${PYTHON}" --version 2>&1)"

# Model posture guard
EFFECTIVE_MODEL="${OPENAI_MODEL:-gpt-5.4}"
if [[ "${EFFECTIVE_MODEL}" != "gpt-5.4" ]]; then
    die "OPENAI_MODEL is set to '${OPENAI_MODEL}'. Phase 1 quality requires gpt-5.4 (or unset to use the patched default). Refusing to run with a different model."
fi
log "Model: ${EFFECTIVE_MODEL}"

# Required credentials
[[ -n "${OPENAI_API_KEY:-}" ]] || die "OPENAI_API_KEY is not set."
[[ -n "${NEO4J_PASSWORD:-}" ]] || die "NEO4J_PASSWORD is not set."

# Fixture datasets
[[ -d "${REPO_ROOT}/demo/fixtures/datasets/demo_dataset_v1" ]] \
    || die "demo_dataset_v1 fixture not found at demo/fixtures/datasets/demo_dataset_v1"
[[ -d "${REPO_ROOT}/demo/fixtures/datasets/demo_dataset_v2" ]] \
    || die "demo_dataset_v2 fixture not found at demo/fixtures/datasets/demo_dataset_v2"
log "Fixture datasets: OK"

# Create artifact directories
mkdir -p "${LOG_DIR}" "${MANIFEST_DIR}"

COMMIT_SHA="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
echo "${COMMIT_SHA}" > "${ARTIFACT_DIR}/commit_sha.txt"
log "Commit SHA: ${COMMIT_SHA}"
log "Artifacts → ${ARTIFACT_DIR}"

# ---------------------------------------------------------------------------
# Helpers: run ID extraction
# ---------------------------------------------------------------------------

# Snapshot the current set of unstructured_ingest run directories.
# Usage: snapshot_ingest_runs <output_file>
snapshot_ingest_runs() {
    ls "${RUNS_DIR}" 2>/dev/null | grep '^unstructured_ingest-' | sort > "$1" || true
}

# Find the run ID created since the given snapshot file.
# Usage: run_id_since <snapshot_file>
run_id_since() {
    local snap="$1"
    local new_dir
    # comm -13: lines only in second file (i.e., new dirs)
    new_dir="$(comm -13 "${snap}" <(ls "${RUNS_DIR}" 2>/dev/null | grep '^unstructured_ingest-' | sort) | head -1)"
    [[ -n "${new_dir}" ]] || die "No new unstructured_ingest run directory found after ingest. Check the ingest log."
    local manifest="${RUNS_DIR}/${new_dir}/pdf_ingest/manifest.json"
    [[ -f "${manifest}" ]] || die "pdf_ingest/manifest.json not found under ${new_dir}"
    "${PYTHON}" -c "import json; d=json.load(open('${manifest}')); print(d['run_id'])"
}

# ---------------------------------------------------------------------------
# Helpers: manifest copy
# ---------------------------------------------------------------------------
copy_manifests() {
    local run_id="$1"
    local prefix="$2"
    local run_dir="${RUNS_DIR}/${run_id}"
    for stage in pdf_ingest claim_and_mention_extraction entity_resolution retrieval_and_qa; do
        local src="${run_dir}/${stage}/manifest.json"
        if [[ -f "${src}" ]]; then
            cp "${src}" "${MANIFEST_DIR}/${prefix}_${stage}.json"
        fi
    done
}

# ---------------------------------------------------------------------------
# Helpers: manifest invariant extraction (for validation_summary.txt)
# ---------------------------------------------------------------------------
extract_claim_invariants() {
    local manifest="$1"
    if [[ ! -f "${manifest}" ]]; then
        echo "  (manifest not found: ${manifest})"
        return
    fi
    "${PYTHON}" - "${manifest}" <<'PYEOF'
import json, sys
manifest_path = sys.argv[1]
with open(manifest_path) as f:
    d = json.load(f)
s = d.get("stages", {}).get("claim_and_mention_extraction", {})
print("  extracted_claim_count:", s.get("extracted_claim_count", "N/A"))
print("  entity_mention_count: ", s.get("entity_mention_count", "N/A"))
print("  extractor_model:      ", s.get("extractor_model", "N/A"))
PYEOF
}

extract_qa_invariants() {
    local manifest="$1"
    local label="${2:-}"
    if [[ ! -f "${manifest}" ]]; then
        echo "  (manifest not found: ${manifest})"
        return
    fi
    "${PYTHON}" - "${manifest}" <<'PYEOF'
import json, sys
manifest_path = sys.argv[1]
with open(manifest_path) as f:
    d = json.load(f)
s = d.get("stages", {}).get("retrieval_and_qa", {})
q = s.get("citation_quality", {})
print("  all_answers_cited:        ", s.get("all_answers_cited", "N/A"))
print("  citation_fallback_applied:", s.get("citation_fallback_applied", "N/A"))
print("  evidence_level:           ", q.get("evidence_level", "N/A"))
print("  hits:                     ", s.get("hits", "N/A"))
print("  qa_model:                 ", s.get("qa_model", "N/A"))
PYEOF
}

# ---------------------------------------------------------------------------
# Execution start
# ---------------------------------------------------------------------------
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "Run timestamp: ${RUN_TS}"
log "Started at:   ${STARTED_AT}"
cd "${REPO_ROOT}"

# ===========================================================================
# BASELINE — demo_dataset_v1
# ===========================================================================

step "Step 1 / Reset demo DB"
"${PYTHON}" -m demo.reset_demo_db --confirm 2>&1 | tee "${LOG_DIR}/00_reset.log"
log "Reset complete."

step "Step 2 / Baseline ingest-pdf (demo_dataset_v1)"
snapshot_ingest_runs "${ARTIFACT_DIR}/.snap_before_v1_ingest"
"${PYTHON}" -m demo.run_demo ingest-pdf --live --dataset demo_dataset_v1 \
    2>&1 | tee "${LOG_DIR}/01_v1_ingest.log"
V1_RUN_ID="$(run_id_since "${ARTIFACT_DIR}/.snap_before_v1_ingest")"
log "Baseline run ID: ${V1_RUN_ID}"

step "Step 3 / Baseline extract-claims (demo_dataset_v1)"
export UNSTRUCTURED_RUN_ID="${V1_RUN_ID}"
"${PYTHON}" -m demo.run_demo extract-claims --live --dataset demo_dataset_v1 \
    2>&1 | tee "${LOG_DIR}/02_v1_extract.log"

step "Step 4 / Baseline resolve-entities (demo_dataset_v1)"
"${PYTHON}" -m demo.run_demo resolve-entities --live --dataset demo_dataset_v1 \
    2>&1 | tee "${LOG_DIR}/03_v1_resolve.log"

step "Step 5 / Baseline ask (demo_dataset_v1)"
"${PYTHON}" -m demo.run_demo ask --live \
    --dataset demo_dataset_v1 \
    --run-id "${V1_RUN_ID}" \
    --question "What does the document say about Endeavor and MercadoLibre?" \
    2>&1 | tee "${LOG_DIR}/04_v1_ask.log"

# Copy baseline manifests now — before the isolation re-ask overwrites retrieval_and_qa
copy_manifests "${V1_RUN_ID}" "v1"

# ===========================================================================
# COMPANION ISOLATION — demo_dataset_v2 (no reset — multi-dataset coexistence)
# ===========================================================================

step "Step 6 / Companion ingest-pdf (demo_dataset_v2) — no reset"
snapshot_ingest_runs "${ARTIFACT_DIR}/.snap_before_v2_ingest"
"${PYTHON}" -m demo.run_demo ingest-pdf --live --dataset demo_dataset_v2 \
    2>&1 | tee "${LOG_DIR}/05_v2_ingest.log"
V2_RUN_ID="$(run_id_since "${ARTIFACT_DIR}/.snap_before_v2_ingest")"
log "Companion run ID: ${V2_RUN_ID}"

step "Step 7 / Companion extract-claims (demo_dataset_v2)"
export UNSTRUCTURED_RUN_ID="${V2_RUN_ID}"
"${PYTHON}" -m demo.run_demo extract-claims --live --dataset demo_dataset_v2 \
    2>&1 | tee "${LOG_DIR}/06_v2_extract.log"

step "Step 8 / Companion resolve-entities (demo_dataset_v2)"
"${PYTHON}" -m demo.run_demo resolve-entities --live --dataset demo_dataset_v2 \
    2>&1 | tee "${LOG_DIR}/07_v2_resolve.log"

step "Step 9 / Companion ask (demo_dataset_v2)"
"${PYTHON}" -m demo.run_demo ask --live \
    --dataset demo_dataset_v2 \
    --run-id "${V2_RUN_ID}" \
    --question "Who is listed as the founder of Xapo?" \
    2>&1 | tee "${LOG_DIR}/08_v2_ask.log"

# Copy companion manifests
copy_manifests "${V2_RUN_ID}" "v2"

step "Step 10 / Baseline isolation re-ask (demo_dataset_v1 after v2 ingest)"
# Unset UNSTRUCTURED_RUN_ID to avoid override confusion; use explicit --run-id
unset UNSTRUCTURED_RUN_ID
"${PYTHON}" -m demo.run_demo ask --live \
    --dataset demo_dataset_v1 \
    --run-id "${V1_RUN_ID}" \
    --question "What does the document say about Endeavor and MercadoLibre?" \
    2>&1 | tee "${LOG_DIR}/09_v1_isolation_ask.log"

# Copy the isolation re-ask manifest (retrieval_and_qa has been overwritten for V1_RUN_ID)
cp "${RUNS_DIR}/${V1_RUN_ID}/retrieval_and_qa/manifest.json" \
    "${MANIFEST_DIR}/v1_isolation_retrieval_and_qa.json" 2>/dev/null || true

# ===========================================================================
# ARTIFACT CAPTURE — validation summary and run metadata
# ===========================================================================

step "Capturing validation summary and run metadata"

FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

{
    echo "=== Phase 1 Verify — Validation Summary ==="
    echo "Run timestamp:  ${RUN_TS}"
    echo "Commit SHA:     ${COMMIT_SHA}"
    echo "Started at:     ${STARTED_AT}"
    echo "Finished at:    ${FINISHED_AT}"
    echo "Model:          ${EFFECTIVE_MODEL}"
    echo ""
    echo "--- Baseline: demo_dataset_v1 ---"
    echo "Run ID: ${V1_RUN_ID}"
    echo ""
    echo "  Claim/mention extraction:"
    extract_claim_invariants "${MANIFEST_DIR}/v1_claim_and_mention_extraction.json"
    echo ""
    echo "  QA / citation (baseline ask):"
    extract_qa_invariants "${MANIFEST_DIR}/v1_retrieval_and_qa.json"
    echo ""
    echo "--- Companion: demo_dataset_v2 ---"
    echo "Run ID: ${V2_RUN_ID}"
    echo ""
    echo "  Claim/mention extraction:"
    extract_claim_invariants "${MANIFEST_DIR}/v2_claim_and_mention_extraction.json"
    echo ""
    echo "  QA / citation (companion ask):"
    extract_qa_invariants "${MANIFEST_DIR}/v2_retrieval_and_qa.json"
    echo ""
    echo "--- Baseline isolation re-ask (demo_dataset_v1 post-v2 ingest) ---"
    echo "Run ID: ${V1_RUN_ID}"
    echo ""
    echo "  QA / citation (isolation re-ask):"
    extract_qa_invariants "${MANIFEST_DIR}/v1_isolation_retrieval_and_qa.json"
    echo ""
    echo "=== End of validation summary ==="
} | tee "${ARTIFACT_DIR}/validation_summary.txt"

# Write run_metadata.json
"${PYTHON}" - <<PYEOF
import json, os
data = {
    "started_at": "${STARTED_AT}",
    "finished_at": "${FINISHED_AT}",
    "run_timestamp": "${RUN_TS}",
    "commit_sha": "${COMMIT_SHA}",
    "model": "${EFFECTIVE_MODEL}",
    "datasets": ["demo_dataset_v1", "demo_dataset_v2"],
    "v1_run_id": "${V1_RUN_ID}",
    "v2_run_id": "${V2_RUN_ID}",
    "artifact_dir": "${ARTIFACT_DIR}",
}
with open("${ARTIFACT_DIR}/run_metadata.json", "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print("run_metadata.json written.")
PYEOF

step "Phase 1 verification complete"
log "All stages passed."
log "Artifacts saved to: ${ARTIFACT_DIR}"
log "Validation summary: ${ARTIFACT_DIR}/validation_summary.txt"
log "Run metadata:       ${ARTIFACT_DIR}/run_metadata.json"
