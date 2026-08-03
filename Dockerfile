# The token-gated driftless API. Runs as an unprivileged user; secrets are decrypted
# from SOPS to a tmpfs at start by deploy/entrypoint.sh (see OPERATIONS.md).
# Pinned by digest, not by tag: `python:3.12-slim` moves on every upstream rebuild, so the
# same commit built twice is two different images and the interpreter, OpenSSL and system
# libraries pip-audit reasoned about are not the ones that ship. Bump this deliberately
# (`docker pull python:3.12-slim && docker image inspect --format '{{index .RepoDigests 0}}'`).
FROM python:3.12-slim@sha256:9e01bf1ae5db7649a236da7be1e94ffbbbdd7a93f867dd0d8d5720d9e1f89fab

# sops + age decrypt the secrets overlay; curl backs the healthcheck.
# SOPS_SHA256 is the `sops-v${SOPS_VERSION}.linux.amd64` line of the release's own
# `sops-v${SOPS_VERSION}.checksums.txt`, and the two are bumped together. It is checked
# BEFORE chmod on purpose: deploy/entrypoint.sh runs this binary to decrypt
# DRIFTLESS_SESSION_SECRET, DRIFTLESS_API_TOKEN and POSTGRES_PASSWORD at start, so an
# unverified download is a swap of the program that holds every deployment secret — and a
# binary made executable and only then inspected has already been trusted for a step.
# `sha256sum -c` exits non-zero on mismatch, which fails the RUN and the whole build.
RUN apt-get update \
    && apt-get install -y --no-install-recommends age curl \
    && rm -rf /var/lib/apt/lists/* \
    && SOPS_VERSION=3.9.4 \
    && SOPS_SHA256=5488e32bc471de7982ad895dd054bbab3ab91c417a118426134551e9626e4e85 \
    && curl -fsSL "https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops-v${SOPS_VERSION}.linux.amd64" \
        -o /usr/local/bin/sops \
    && echo "${SOPS_SHA256}  /usr/local/bin/sops" | sha256sum -c - \
    && chmod 0755 /usr/local/bin/sops

WORKDIR /app
# requirements.lock is deliberately NOT here: the image installs from the hashed file below,
# and a lock the build never reads is a file the next reader assumes is load-bearing. It is
# still what CI and pip-audit constrain with, and what the hashed file is compiled against.
COPY pyproject.toml requirements-runtime.txt ./
COPY driftless ./driftless
COPY alembic ./alembic
COPY alembic.ini ./
# The two files the server itself runs on, by name. The rest of deploy/ is host-side (the Caddyfile
# and proxy.compose.yml configure the *proxy* container; secrets.env.example is the
# operator's template; compose bind-mounts the encrypted overlay at run time), and
# copying the directory wholesale would put an operator's age PRIVATE key into a
# permanent layer. .dockerignore is the second lock, not the first.
COPY deploy/entrypoint.sh ./deploy/entrypoint.sh
COPY deploy/logging.json ./deploy/logging.json
# Two installs, because they answer two different questions.
#
# The first is the dependency set, and it is the one an attacker would want. A version pin
# says WHICH release to fetch; it says nothing about what the index actually returned, so
# `--constraint requirements.lock` alone still trusts whatever bytes arrived. `--require-hashes`
# makes pip refuse anything whose sha256 is not one this repo committed — the same argument
# the sops digest above already wins for the one binary that was fetched unverified.
# requirements-runtime.txt carries a hash for every distribution in the runtime closure and is
# compiled under `-c requirements.lock`, so both files name one version set and pip-audit still
# scans what the image installs; tests/test_image_dependency_parity.py fails if they diverge.
#
# The second installs the checkout, and it cannot be part of the first: pip refuses a
# directory under --require-hashes ("Can't verify hashes for these file:// requirements
# because they point to directories"). `--no-deps` is what makes that safe rather than a
# hole — every dependency is already present from the hashed set, so this line resolves
# nothing and reaches no index. Runtime only, still: the `[dev]` extra put pytest,
# pytest-xdist, coverage and httpx in a production image, CVE surface with nothing to run it.
RUN pip install --no-cache-dir --require-hashes -r requirements-runtime.txt \
    && pip install --no-cache-dir --no-deps . \
    && useradd --system --uid 10001 driftless \
    && chmod 0755 deploy/entrypoint.sh

USER driftless
EXPOSE 8000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
# --log-config is what makes this image observable. driftless/api/logging.py emits one JSON
# line per request — ts, method, path, status, duration_ms, client — but only above INFO on
# its own logger, and it never configures logging itself (a library that shouts by default
# is one no caller can quiet). uvicorn's own default configuration has never heard of that
# logger, so without this flag the shipped container answers "what happened at 3am?" with
# nothing: a failed request and a slow one look identical, because neither is written down.
# The document is JSON, not YAML, on purpose — uvicorn reads YAML only with PyYAML installed
# (uvicorn[standard]), and a logging format is a poor reason to add a dependency to an image.
# What it cannot print is as deliberate as what it prints: the two format strings interpolate
# only asctime/levelname/name/message, and uvicorn's own access logger is held at WARNING
# because its line is built from the raw request target, query string included, where
# driftless.request logs request.url.path. tests/test_api_logging.py pins both halves.
# --proxy-headers/--forwarded-allow-ips are the deployment half of the login throttle.
# deploy/proxy.compose.yml puts Caddy in front, and uvicorn trusts X-Forwarded-For from
# 127.0.0.1 alone by default — which the proxy container never is — so every request would
# arrive as the proxy's compose address: one failed password would spend the throttle
# budget for all of them. The value is the private range compose allocates its bridge
# networks from, never `*`: trusting the header from anyone lets a client forge another
# user's address, both into that throttle and into the request log.
CMD ["uvicorn", "driftless.api.secure:secured", "--host", "0.0.0.0", "--port", "8000", "--log-config", "/app/deploy/logging.json", "--proxy-headers", "--forwarded-allow-ips=172.16.0.0/12"]
