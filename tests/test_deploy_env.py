"""Every environment variable the package reads must reach the running container.

``deploy/entrypoint.sh`` sources the decrypted SOPS overlay, so every key in that file
becomes a *shell* variable — and only the names on its ``export`` line become the
server's environment. A secret an operator faithfully put in the overlay can therefore
be silently absent from the process that needs it, which is exactly how browser sign-in
shipped dead: ``DRIFTLESS_SESSION_SECRET`` was sourced, never exported, and
``driftless.auth.sessions`` fails closed without it.

So the list of variables is *derived from the source*, never hand-written: an AST walk
over ``driftless/`` collects every ``os.environ`` / ``os.getenv`` read, resolving the
module constants the reads are spelled with. Each name must be exported by the
entrypoint or carry a stated reason for having no job in the container — and the
reasons are compared as an **exact set**, so a new variable cannot quietly join them.

The second half of the file checks *values* rather than names, against one relationship:
**no value ``deploy/secrets.env.example`` ships may be a value the entrypoint accepts.**
The template is public, so any value in it is a published constant; a check spelled that
way catches the placeholder someone writes next, whatever they call it, on the day they
write it — where a check for the literal ``CHANGE-ME`` would catch only ``CHANGE-ME``.
The guard is *driven*, not modelled: the tests extract the entrypoint's own shell
function and run it, so a rule that lives only in this file cannot pretend to ship.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

SERVICE = Path(__file__).resolve().parents[1]
PACKAGE = SERVICE / "driftless"
ENTRYPOINT = SERVICE / "deploy" / "entrypoint.sh"
TEMPLATE = SERVICE / "deploy" / "secrets.env.example"

# Read by the package, deliberately NOT plumbed into the container — each with the
# reason it is not needed there. Asserted as an exact set below: adding a read without
# exporting it fails until someone writes the reason down here.
NOT_IN_THE_CONTAINER = {
    "DRIFTLESS_ALLOW_UNAUTHENTICATED": (
        "the local-development opt-out of the startup refusal, which must stay visible in "
        "the compose invocation; in the encrypted overlay it would be invisible, and left "
        "on it serves the whole API open with no credential at all"
    ),
    "DRIFTLESS_ALLOW_SCHEMA_AHEAD": (
        "a temporary rollback override that must stay visible in the compose invocation; "
        "in the encrypted overlay it would be invisible, and left on it corrupts quietly"
    ),
    "DRIFTLESS_COOKIE_SECURE": (
        "a development opt-out for plain HTTP. The shipped deployment terminates TLS and "
        "publishes only on loopback, which browsers already treat as a secure origin, so "
        "the secure default is the only value a container should have"
    ),
    "PMHUB_API_TOKEN": (
        "the deprecated token name: the entrypoint folds it into DRIFTLESS_API_TOKEN "
        "before exporting, so the container never needs the old name itself"
    ),
    "PMHUB_DATABASE_URL": (
        "a deprecated alias for the database URL, which the entrypoint assembles from "
        "parts and exports under the canonical name"
    ),
    "PMHUB_DB_URL": "the CLIs' historical database-URL alias, superseded the same way",
    "DRIFTLESS_GIT_SHA": (
        "the packaged build's own SHA, baked in at image build time (e.g. a Docker ARG/ENV "
        "set from the CI checkout), never sourced from the encrypted secrets overlay this "
        "entrypoint decrypts; read_git_sha() falls back to git-in-checkout and then "
        "'unknown', so an image that never sets it still starts"
    ),
}

EXPORT = re.compile(r"^\s*export\s+(.*)$", re.M)
REQUIRED = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*):\?([^}]*)\}")
ASSIGNED = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.M)
GUARD = re.compile(r"^(refuse_placeholder\(\)\s*\{\n.*?^\})", re.M | re.S)
# A value long enough to pass the guard, to prove it refuses on a property of the
# value rather than by refusing everything it is shown. Assembled rather than
# written out: a 32-char hex literal here reads as a leaked credential to the
# secrets scanner in CI, and an allowlist entry would teach that scanner to ignore
# exactly the shape it exists to catch.
A_REAL_SECRET = "".join(f"{n:02x}" for n in range(16))


def _named(node: ast.expr, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _is_environ(node: ast.expr) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr == "environ" and _named(node.value, "os")
    return _named(node, "environ")


def _env_name_node(node: ast.AST) -> ast.expr | None:
    """The expression naming the variable, for every shape of environment read."""
    if isinstance(node, ast.Subscript) and _is_environ(node.value):
        return node.slice
    if not isinstance(node, ast.Call) or not node.args:
        return None
    func = node.func
    if _named(func, "getenv"):
        return node.args[0]
    if isinstance(func, ast.Attribute):
        if func.attr == "getenv" and _named(func.value, "os"):
            return node.args[0]
        if func.attr == "get" and _is_environ(func.value):
            return node.args[0]
    return None


def _module_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "literal"``, so ``os.environ.get(SECRET_ENV)`` resolves."""
    return {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
        if isinstance(node.value.value, str)
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def environment_reads() -> tuple[set[str], list[str]]:
    """Every variable name the package reads, and every read that would not resolve."""
    names, unresolved = set(), []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _module_constants(tree)
        for node in ast.walk(tree):
            arg = _env_name_node(node)
            if arg is None:
                continue
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                names.add(arg.value)
            elif isinstance(arg, ast.Name) and arg.id in constants:
                names.add(constants[arg.id])
            else:
                unresolved.append(f"{path.relative_to(SERVICE)}:{arg.lineno}")
    return names, unresolved


def exported() -> set[str]:
    """The names ``deploy/entrypoint.sh`` puts into the server's environment."""
    return {
        word.split("=", 1)[0]
        for line in EXPORT.findall(ENTRYPOINT.read_text(encoding="utf-8"))
        for word in line.split("#", 1)[0].split()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=?.*", word)
    }


def test_every_environment_read_names_a_variable_statically() -> None:
    """A name assembled at runtime would defeat the whole check, so it fails here."""
    names, unresolved = environment_reads()
    assert not unresolved, f"environment reads whose variable name is not static: {unresolved}"
    assert "DRIFTLESS_DATABASE_URL" in names, f"the walk found nothing it should have: {names}"


def test_every_variable_the_package_reads_is_exported_or_excused() -> None:
    names, _ = environment_reads()
    missing = names - exported()
    assert missing == set(NOT_IN_THE_CONTAINER), (
        "deploy/entrypoint.sh does not export "
        f"{sorted(missing - set(NOT_IN_THE_CONTAINER))} and nothing says why it need not; "
        f"stale excuses: {sorted(set(NOT_IN_THE_CONTAINER) - missing)}"
    )
    assert all(len(reason) > 30 for reason in NOT_IN_THE_CONTAINER.values())


def test_the_session_secret_reaches_the_server() -> None:
    """The bug this file exists for: sourced into the shell, never exported."""
    assert "DRIFTLESS_SESSION_SECRET" in exported(), (
        "deploy/entrypoint.sh sources the SOPS overlay but never exports "
        "DRIFTLESS_SESSION_SECRET, so driftless.auth.sessions sees nothing and fails "
        "closed: no cookie can authorize and browser sign-in is dead in the container"
    )


def test_a_missing_secret_names_its_own_remedy() -> None:
    """Hard-required and absent must tell the operator the key, the file and the tool."""
    required = REQUIRED.findall(ENTRYPOINT.read_text(encoding="utf-8"))
    assert {name for name, _ in required} >= {"POSTGRES_PASSWORD", "DRIFTLESS_SESSION_SECRET"}
    for name, message in required:
        assert name in message, f"{name}'s failure message does not name it: {message!r}"
        assert "secrets.enc.env" in message, f"{name}: no file to put it in: {message!r}"
        assert "sops-edit" in message, f"{name}: no tool to edit it with: {message!r}"


def test_the_template_lists_every_secret_the_entrypoint_requires() -> None:
    """An operator filling in deploy/secrets.env.example must not be missing a key."""
    template = TEMPLATE.read_text(encoding="utf-8")
    absent = [name for name, _ in REQUIRED.findall(ENTRYPOINT.read_text(encoding="utf-8"))]
    assert not [name for name in absent if f"{name}=" not in template], (
        f"deploy/secrets.env.example does not carry {absent}, so a deployment built from "
        "the template refuses to start"
    )


def shipped_values() -> dict[str, str]:
    """Every value deploy/secrets.env.example actually ships, keyed by variable."""
    text = TEMPLATE.read_text(encoding="utf-8")
    return {name: value.strip() for name, value in ASSIGNED.findall(text) if value.strip()}


def refusal(value: str, key: str = "DRIFTLESS_SESSION_SECRET") -> str:
    """The entrypoint's own refusal of ``value``, or ``""`` if it accepts it.

    The shipped shell function is extracted and executed, so this measures the guard
    that runs at ``docker compose up`` rather than a restatement of it here.
    """
    guard = GUARD.search(ENTRYPOINT.read_text(encoding="utf-8"))
    assert guard, (
        "deploy/entrypoint.sh defines no refuse_placeholder function, so nothing rejects a "
        "value that is still the published template placeholder"
    )
    script = f'{guard.group(1)}\nrefuse_placeholder "$1" "$2"\n'
    done = subprocess.run(
        ["sh", "-c", script, "sh", key, value], capture_output=True, text=True, check=False
    )
    return done.stderr.strip() if done.returncode else ""


def test_no_value_the_template_ships_is_a_value_the_entrypoint_accepts() -> None:
    """The class, not the spelling.

    Whatever a future author calls the next placeholder, putting it in the public
    template makes it a published constant — and this fails the moment it is written
    unless the entrypoint also refuses it. Today the template ships no value for any
    required key, which is why nothing needs naming here.
    """
    required = {name for name, _ in REQUIRED.findall(ENTRYPOINT.read_text(encoding="utf-8"))}
    accepted = sorted(
        name for name, value in shipped_values().items() if name in required and not refusal(value)
    )
    assert not accepted, (
        f"deploy/secrets.env.example ships a value for {accepted} that deploy/entrypoint.sh "
        "accepts, so an operator who encrypts the template unedited serves a deployment whose "
        "session key and bearer token are constants published in this repository; leave the "
        "template's value empty, or teach refuse_placeholder to reject it"
    )


def test_the_placeholder_this_repository_published_is_still_refused() -> None:
    """Emptying the template cannot reach an overlay encrypted before it was emptied."""
    assert refusal("CHANGE-ME-to-a-long-random-value")
    assert refusal("CHANGE-ME-to-a-long-random-token")


def test_a_secret_short_enough_to_have_been_typed_is_refused() -> None:
    """Every value here is machine-generated by the documented remedy, so a short one
    is a hand-typed one — the same failure the placeholder was one instance of."""
    assert refusal("hunter2")
    assert not refusal(A_REAL_SECRET), "the guard refuses a real secret; it would refuse everything"


def test_a_refused_secret_names_its_own_remedy() -> None:
    """Same guarantee as an absent one: the key, the file and the tool, not a scolding."""
    for value in ("CHANGE-ME-to-a-long-random-value", "hunter2"):
        message = refusal(value, key="POSTGRES_PASSWORD")
        assert "POSTGRES_PASSWORD" in message, f"the refusal does not name the key: {message!r}"
        assert "secrets.enc.env" in message, f"no file to fix it in: {message!r}"
        assert "sops-edit" in message, f"no tool to fix it with: {message!r}"
