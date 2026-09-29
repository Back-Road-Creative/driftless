#!/usr/bin/env bash
# One command that runs the gates CI runs, at the versions CI runs them at.
#
# Every pin below is READ from .github/workflows/, never written here. A local
# runner that names its own `ruff==` is right until the day CI bumps and then
# goes quietly wrong — green locally against a linter the merge never uses. The
# same reasoning keeps the coverage floor out of this file: it lives in
# pyproject.toml's addopts, and `pytest` picks it up on its own.
#
# The venv is part of the gate, not a precondition of it. A shared interpreter
# drifts from requirements.lock and takes the suite's answer with it, so this
# builds an in-repo .venv under the lock's constraints the way CI does — the
# uv-then-pip shim, same as every install step in the workflows.
#
# usage:
#   bin/driftless-gates.sh                    # the full run: every stage below, mirroring
#                                              # all four CI jobs in ci.yml, PLUS pip-audit
#   bin/driftless-gates.sh --quality          # one stage (repeatable: --tests --samples ...);
#                                              # selecting a stage this way leaves pip-audit out
#                                              # (see --audit below) so a fast single-stage loop
#                                              # never pays its network cost
#   bin/driftless-gates.sh --no-env           # reuse .venv as it stands
#   bin/driftless-gates.sh --migrations       # the Postgres-16 job: starts postgres:16 in
#                                              # Docker itself, needs no env var set first
#   bin/driftless-gates.sh --docker-build     # the Docker image build job: `docker build`,
#                                              # nothing pushed
#   bin/driftless-gates.sh --browser          # the OPT-IN rendered-browser tier: installs
#                                              # .[browser] + Chromium and runs tests/browser.
#                                              # Never part of the default run and never a
#                                              # required CI check — the byte-diffable page
#                                              # snapshots stay the floor; this runs beside them
#   bin/driftless-gates.sh --audit            # force pip-audit on even with other stages named
#   bin/driftless-gates.sh --no-audit         # the declared opt-out: skip pip-audit on a run
#                                              # that would otherwise include it (offline / a
#                                              # flaky connection) — prints that it did, never
#                                              # silent
#   bin/driftless-gates.sh --print-pins       # what it read out of the workflows
#
# --migrations and --docker-build need Docker; pip-audit needs network at every
# invocation (it queries an advisory database, not just a one-time package
# install like every other stage); all three fail loudly, never skip quietly,
# if what they need is not available — pip-audit retries a bounded 3 times on a
# transient network error first, the same backoff pip-audit.yml uses, before
# failing.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
CI_YML=".github/workflows/ci.yml"
AUDIT_YML=".github/workflows/pip-audit.yml"
COMPOSE_YML="docker-compose.yml"

die() { echo "gates: $*" >&2; exit 1; }

# --- cleanup, accumulated by whichever stages run -----------------------------
# One EXIT trap for the whole script (not one per stage) so a container or
# scratch file registered by an early stage is still removed if a later stage
# fails, and so an interrupt (Ctrl-C) cleans up too: INT/TERM re-raise through
# `exit`, which is what actually fires the EXIT trap below.
CLEANUP_CMDS=()
cleanup_all() { local cmd; for cmd in "${CLEANUP_CMDS[@]:-}"; do [ -n "$cmd" ] && eval "$cmd" || true; done; }
trap cleanup_all EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# --- pins, read from the workflows -------------------------------------------
read_pin() {  # read_pin <file> <regex-with-one-group> <label>
    local value
    value="$(sed -nE "s/.*$2.*/\1/p" "$1" | sort -u)"
    [ -n "$value" ] || die "no $3 pin found in $1 — the workflow changed shape"
    [ "$(printf '%s\n' "$value" | wc -l)" -eq 1 ] || die "conflicting $3 pins: $value"
    printf '%s' "$value"
}

RUFF_V="$(read_pin "$CI_YML" "RUFF_VERSION:[[:space:]]*'([^']+)'" ruff)"
SECRETS_V="$(read_pin "$CI_YML" "DETECT_SECRETS_VERSION:[[:space:]]*'([^']+)'" detect-secrets)"
MYPY_V="$(read_pin "$CI_YML" "mypy==([0-9][^[:space:]\"']*)" mypy)"
AUDIT_V="$(read_pin "$AUDIT_YML" "PIP_AUDIT_VERSION:[[:space:]]*'([^']+)'" pip-audit)"
PY_V="$(read_pin "$CI_YML" "python-version:[[:space:]]*'([^']+)'" python)"

# --- argument parsing ---------------------------------------------------------
DO_ENV=1 STAGES="" AUDIT=""
for arg in "$@"; do
    case "$arg" in
        --print-pins)
            echo "ruff=$RUFF_V detect-secrets=$SECRETS_V mypy=$MYPY_V" \
                 "pip-audit=$AUDIT_V python=$PY_V" | tr ' ' '\n'
            exit 0 ;;
        --no-env)      DO_ENV=0 ;;
        --quality)     STAGES="$STAGES quality" ;;
        --tests)       STAGES="$STAGES tests" ;;
        --samples)     STAGES="$STAGES samples" ;;
        --migrations)  STAGES="$STAGES migrations" ;;
        --docker-build) STAGES="$STAGES docker-build" ;;
        --browser)     STAGES="$STAGES browser" ;;
        --audit)       AUDIT=1 ;;
        --no-audit)    AUDIT=0 ;;
        -h|--help)   sed -n '/^# usage:/,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//;$d'; exit 0 ;;
        *)           die "unknown argument: $arg" ;;
    esac
done
# The full default run (no stage flag named) is the only run pip-audit joins
# uninvited — it queries the network on every invocation, unlike the one-time
# package installs the other stages pay for, so naming one stage explicitly
# (a fast local loop) never pays that cost unless --audit says to. --audit and
# --no-audit each override this outright, in either direction.
FULL_DEFAULT=0
if [ -z "$STAGES" ]; then
    STAGES="quality tests samples migrations docker-build"
    FULL_DEFAULT=1
fi
[ -n "$AUDIT" ] || AUDIT="$FULL_DEFAULT"

PY="$(command -v "python$PY_V" || command -v python3)"
"$PY" -c "import sys; sys.exit(0 if sys.version_info[:2] == tuple(
    int(p) for p in '$PY_V'.split('.')[:2]) else 1)" \
    || die "$PY is not Python $PY_V — CI runs $PY_V and a different minor answers a different question"

if command -v uv >/dev/null 2>&1; then
    mkvenv()    { uv venv "$1" --python "$PY" -q; }
    pyinstall() { local v="$1"; shift; uv pip install --python "$v/bin/python" -q "$@"; }
else
    mkvenv()    { "$PY" -m venv "$1"; "$1/bin/pip" install --quiet --upgrade pip; }
    pyinstall() { local v="$1"; shift; "$v/bin/pip" install --quiet "$@"; }
fi

step() { echo; echo "=== $* ==="; }

# --- env ----------------------------------------------------------------------
if [ "$DO_ENV" -eq 1 ]; then
    step "env (.venv from requirements.lock + .[dev])"
    [ -x .venv/bin/python ] || mkvenv .venv
    pyinstall .venv pytest pytest-cov pytest-xdist
    CONSTRAINTS="$(mktemp)"; CLEANUP_CMDS+=("rm -f '$CONSTRAINTS'")
    grep -v '^-e ' requirements.lock > "$CONSTRAINTS"
    pyinstall .venv --constraint "$CONSTRAINTS" ".[dev]"
fi
[ -x .venv/bin/python ] || die ".venv is missing — drop --no-env to build it"

# --- stages -------------------------------------------------------------------
run_quality() {
    step "quality (ruff $RUFF_V, detect-secrets $SECRETS_V, mypy $MYPY_V strict)"
    local tools=".venv-gates-tools"
    [ -x "$tools/bin/ruff" ] && "$tools/bin/ruff" --version | grep -qF "$RUFF_V" \
        || { mkvenv "$tools"; pyinstall "$tools" "ruff==$RUFF_V" "detect-secrets==$SECRETS_V"; }

    "$tools/bin/ruff" check .
    "$tools/bin/ruff" format . --check

    local scan; scan="$(mktemp)"
    "$tools/bin/detect-secrets" scan . --no-verify \
        --exclude-files '.*\.(lock|baseline|backup|enc)$' \
        --exclude-files '.*/\.?venv/.*' \
        --exclude-files '.*/node_modules/.*' \
        --exclude-files '^\.data/.*' > "$scan"
    local count
    count="$("$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); \
print(sum(len(v) for v in d.get('results',{}).values()))" "$scan")"
    [ "$count" -eq 0 ] || { cat "$scan"; rm -f "$scan"; die "detect-secrets found $count"; }
    rm -f "$scan"

    # mypy resolves third-party imports from its own interpreter, so it gets the
    # real deps in a venv of its own — the shape CI settled on after a phantom
    # no-any-return on this service.
    local mypy_venv=".venv-gates-mypy"
    [ -x "$mypy_venv/bin/python" ] || mkvenv "$mypy_venv"
    pyinstall "$mypy_venv" -e ".[dev]" "mypy==$MYPY_V"
    "$mypy_venv/bin/python" -m mypy . --config-file pyproject.toml \
        --install-types --non-interactive
}

run_tests() {
    step "tests (pytest -n auto, tmp_path in RAM; coverage floor from pyproject addopts)"
    set +e
    # tmp_path in RAM, as CI does: every test's sqlite store lands there instead
    # of the disk (77 s -> 8 s for two files on the WSL host, 2026-09-05).
    .venv/bin/python -m pytest -n auto --basetemp="${TMPDIR_RAM:-/dev/shm}/driftless-tmp-$$"
    local rc=$?
    set -e
    [ "$rc" -ne 5 ] || die "no tests collected — likely an import failure"
    [ "$rc" -eq 0 ] || exit "$rc"
}

run_samples() {
    step "committed sample reports have not drifted"
    local out; out="$(mktemp -d)"
    .venv/bin/python bin/driftless-sample-reports.py --out "$out"
    local tracked; tracked="$(git ls-files -- docs/samples)"
    [ -n "$tracked" ] || die "no committed samples under docs/samples — this gate proves nothing"
    local rc=0 path
    for path in $tracked; do
        diff -u "$path" "$out/${path#docs/samples/}" || rc=1
    done
    rm -rf "$out"
    [ "$rc" -eq 0 ] || die "docs/samples no longer matches the generator — rerun and commit it"
    echo "$(echo "$tracked" | wc -l) committed sample(s) regenerate byte-identically"
}

run_browser() {
    step "rendered browser checks (opt-in; Chromium via playwright)"
    local venv=".venv-gates-browser"
    [ -x "$venv/bin/python" ] || mkvenv "$venv"
    pyinstall "$venv" -e ".[dev,browser]" uvicorn  # uvicorn named, never declared — see pyproject
    # Chromium only. The tier checks THIS product's layout, not cross-engine parity,
    # and a second engine doubles the download for an answer nothing here asks.
    # No --with-deps: it shells out to the system package manager as root, which the
    # dev container refuses and a self-hosted runner should not be doing per test run.
    # The host provides the shared libraries once; a missing one fails here, loudly.
    "$venv/bin/python" -m playwright install chromium \
        || die "playwright could not install Chromium — this stage needs network; it never skips quietly"
    # addopts is overridden wholesale: the repo default carries the coverage floor and
    # the --ignore that hides this very directory from the default run.
    "$venv/bin/python" -m pytest tests/browser -o addopts="" -q
}

require_docker() {  # require_docker <stage-name>
    command -v docker >/dev/null 2>&1 \
        || die "docker not found — the $1 stage needs it, the same way CI's $1 job does; install Docker or skip this stage"
}

run_migrations() {
    step "migrations (postgres:16 in Docker, mirrors CI's Migrations job)"
    require_docker migrations
    local pg_image
    pg_image="$(read_pin "$COMPOSE_YML" "image:[[:space:]]*(postgres:[^[:space:]]+)" postgres)"

    # Container port only, published to whatever free host port Docker picks —
    # never assumed to be 5432, which is exactly what keeps this stage off any
    # other Postgres that happens to already be listening on this machine.
    local cid
    cid="$(docker run -d --rm \
        -e POSTGRES_USER=driftless -e POSTGRES_DB=driftless \
        -e POSTGRES_HOST_AUTH_METHOD=trust \
        -p 127.0.0.1::5432 "$pg_image")" \
        || die "failed to start $pg_image — is Docker running?"
    CLEANUP_CMDS+=("docker rm -f '$cid' >/dev/null 2>&1")

    local host_port
    host_port="$(docker port "$cid" 5432/tcp | head -1 | sed -E 's/.*:([0-9]+)$/\1/')"
    [ -n "$host_port" ] || die "could not read back the host port Docker assigned to $pg_image"

    local tries=0
    until docker exec "$cid" pg_isready -U driftless -d driftless >/dev/null 2>&1; do
        tries=$((tries + 1))
        [ "$tries" -lt 40 ] || die "$pg_image did not become ready on 127.0.0.1:$host_port in time"
        sleep 0.5
    done

    # Same test, same flag as CI's Migrations job: `-o addopts=` drops the
    # repo-wide coverage floor on purpose — one module cannot cover the
    # package, and coverage is the tests stage's question, not this one's.
    DRIFTLESS_TEST_DB_URL="postgresql+psycopg://driftless@127.0.0.1:$host_port/driftless" \
        .venv/bin/python -m pytest tests/test_migrations.py -o "addopts=" -q
}

run_docker-build() {
    step "docker-build (docker build, mirrors CI's Docker image build job)"
    require_docker docker-build
    # No push, no registry, no cache — same reasoning as ci.yml's docker-build
    # job: nothing here has yet reused a previous run, so a cold build is the
    # honest answer and the only one that catches a build that no longer works.
    docker build --tag driftless:ci .
}

run_audit() {
    step "pip-audit $AUDIT_V (clean venv, requirements.lock-constrained .[dev] + uvicorn — mirrors pip-audit.yml)"
    # Two venvs, rebuilt fresh every run, same as the workflow: the tool venv
    # holds pip-audit itself, the deps venv holds ONLY what this audits, so
    # pip-audit's own transitive tree can never be mistaken for something this
    # service ships. Reusing the quality/tests .venv would audit the dev
    # environment instead of the shipped one, and would still miss uvicorn,
    # which pyproject.toml never declares but the Dockerfile installs.
    local tool_venv=".venv-gates-audit-tool" deps_venv=".venv-gates-audit-deps"
    rm -rf "$tool_venv" "$deps_venv"
    mkvenv "$tool_venv"
    mkvenv "$deps_venv"
    pyinstall "$tool_venv" "pip-audit==$AUDIT_V"

    local constraints; constraints="$(mktemp)"; CLEANUP_CMDS+=("rm -f '$constraints'")
    grep -v '^-e ' requirements.lock > "$constraints"
    pyinstall "$deps_venv" --constraint "$constraints" ".[dev]" uvicorn

    # .pip-audit-ignore: one CVE id per line, comments and blanks skipped —
    # same parse pip-audit.yml uses, so the two never disagree about what an
    # entry there actually silences.
    local ignore_args=()
    if [ -f .pip-audit-ignore ]; then
        local cve
        while IFS= read -r cve || [ -n "$cve" ]; do
            [[ -n "$cve" && ! "$cve" =~ ^# ]] && ignore_args+=(--ignore-vuln "$cve")
        done < .pip-audit-ignore
    fi

    local site_pkgs
    site_pkgs="$("$deps_venv/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"

    # Retry ONLY a transient network error, bounded, same backoff as
    # pip-audit.yml; anything else — including a real finding — exits non-zero
    # here and stops the run. A security gate that cannot execute must fail,
    # never stay quiet.
    local attempt=1 max=3 out rc
    while :; do
        set +e
        out="$("$tool_venv/bin/pip-audit" --timeout 60 --path "$site_pkgs" "${ignore_args[@]}" 2>&1)"
        rc=$?
        set -e
        printf '%s\n' "$out"
        [ "$rc" -eq 0 ] && break
        if printf '%s' "$out" | grep -qiE 'ReadTimeout|ConnectTimeout|ConnectionError|timed out|Max retries|HTTPSConnectionPool|Failed to establish' \
            && [ "$attempt" -lt "$max" ]; then
            echo "gates: pip-audit transient network error (attempt $attempt/$max) — retrying"
            sleep $((attempt * 15)); attempt=$((attempt + 1)); continue
        fi
        die "pip-audit failed (rc=$rc) — see output above"
    done
}

for stage in $STAGES; do "run_$stage"; done

if [ "$AUDIT" -eq 1 ]; then
    run_audit
else
    echo; echo "gates: pip-audit skipped (--no-audit, or a single non-default stage was named — pass --audit to force it)"
fi

echo; echo "gates: all requested stages passed"
