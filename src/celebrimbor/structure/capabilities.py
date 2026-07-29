"""The dependency-injection gate: ambient capability use, budgeted by role.

An un-injected dependency is a claim the test cannot contradict. A function
that calls ``datetime.now()`` has a behaviour — what it does at midnight, at a
leap second, in another timezone — that no test can reach, because there is no
seam to reach it through. That is the epistemic vacuum this project exists to
close, so this gate is not a style rule bolted on beside the obligation
engine; it is the same idea applied to capabilities instead of to proofs.

**Ambient versus injected.** The distinction is structural and the AST can see
it. Given ``x.y()``, walk the attribute chain to its root name. If that root is
a parameter of the enclosing callable, or ``self``/``cls``, the capability was
handed in — a test can hand in a different one, so the behaviour is reachable.
If the root is a module-level import, or the call is a bare builtin like
``open()``, the capability was reached for. There is no seam, and the
behaviour is unreachable.

    def stamp(record):              def stamp(record, clock):
        record.at = now()               record.at = clock.now()
        #          ^ ambient           #          ^ injected: root `clock`
        #            unreachable       #            is a parameter

**Budgeted by role.** A capability is not universally forbidden — it has to
live *somewhere*, or the program does nothing. The role says where. An
``adapter`` exists precisely to be the place network and database access is
allowed to be ambient; that is what makes it the seam everything else injects
through. A ``pure`` callable touching the clock is a contradiction of a
declared obligation, and that is exactly the kind of claim the harness should
be able to falsify.

The budget lives in :data:`ROLE_BUDGET`. Reading it top to bottom is a good
summary of what each role is *for*.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from ..roles import Role

if TYPE_CHECKING:
    from ..surface.inventory import CallableInfo


class Capability(StrEnum):
    """A thing a callable can reach for instead of being handed."""

    CLOCK = "clock"
    RANDOM = "random"
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    ENVIRONMENT = "environment"
    PROCESS = "process"
    DATABASE = "database"

    def __str__(self) -> str:
        return self.value


# Dotted-suffix patterns, matched against the resolved attribute chain of a
# call. Kept as data rather than logic so an adopter can read exactly what is
# detected — a gate whose trigger conditions are opaque gets disabled.
_PATTERNS: dict[Capability, tuple[str, ...]] = {
    Capability.CLOCK: (
        "datetime.now",
        "datetime.utcnow",
        "datetime.today",
        "date.today",
        "time.time",
        "time.monotonic",
        "time.perf_counter",
        "time.time_ns",
        "time.sleep",
        "pendulum.now",
        "arrow.now",
    ),
    Capability.RANDOM: (
        "random.random",
        "random.randint",
        "random.choice",
        "random.shuffle",
        "random.sample",
        "random.uniform",
        "random.randrange",
        "random.seed",
        "uuid.uuid1",
        "uuid.uuid4",
        "secrets.token_hex",
        "secrets.token_bytes",
        "secrets.token_urlsafe",
        "secrets.choice",
    ),
    Capability.FILESYSTEM: (
        "open",
        "Path.open",
        "Path.read_text",
        "Path.read_bytes",
        "Path.write_text",
        "Path.write_bytes",
        "Path.unlink",
        "Path.mkdir",
        "Path.rmdir",
        "Path.rename",
        "os.remove",
        "os.rename",
        "os.mkdir",
        "os.makedirs",
        "os.rmdir",
        "os.listdir",
        "os.walk",
        "shutil.copy",
        "shutil.copytree",
        "shutil.rmtree",
        "shutil.move",
        "tempfile.mkstemp",
        "tempfile.mkdtemp",
        "tempfile.NamedTemporaryFile",
    ),
    Capability.NETWORK: (
        "requests.get",
        "requests.post",
        "requests.put",
        "requests.delete",
        "requests.patch",
        "requests.head",
        "requests.request",
        "requests.Session",
        "httpx.get",
        "httpx.post",
        "httpx.put",
        "httpx.delete",
        "httpx.request",
        "httpx.Client",
        "httpx.AsyncClient",
        "urllib.request.urlopen",
        "request.urlopen",
        "urlopen",
        "socket.socket",
        "socket.create_connection",
        "aiohttp.ClientSession",
        "smtplib.SMTP",
        "ftplib.FTP",
    ),
    Capability.ENVIRONMENT: (
        "os.getenv",
        "os.environ.get",
        "os.environ.setdefault",
        "environ.get",
        "getpass.getuser",
        "platform.node",
        "socket.gethostname",
    ),
    Capability.PROCESS: (
        "subprocess.run",
        "subprocess.Popen",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "os.system",
        "os.popen",
        "os.fork",
        "os.execv",
        "os.spawnv",
        "sys.exit",
    ),
    Capability.DATABASE: (
        "cursor.execute",
        "cursor.executemany",
        "connection.commit",
        "connection.cursor",
        "session.commit",
        "session.execute",
        "session.query",
        "session.add",
        "engine.connect",
        "engine.execute",
        "sqlite3.connect",
        "psycopg2.connect",
        "psycopg.connect",
        "pymysql.connect",
        "redis.Redis",
        "redis.from_url",
    ),
}

# Bare names (no dotted prefix) that count as ambient when called directly.
_BARE: dict[str, Capability] = {
    "open": Capability.FILESYSTEM,
    "input": Capability.ENVIRONMENT,
    "urlopen": Capability.NETWORK,
    "eval": Capability.PROCESS,
    "exec": Capability.PROCESS,
}

# Module-level attribute reads that are ambient even without a call, because
# reading them is already the dependency: `os.environ["HOME"]` needs no call.
_AMBIENT_READS: dict[str, Capability] = {
    "os.environ": Capability.ENVIRONMENT,
    "sys.argv": Capability.ENVIRONMENT,
    "sys.stdin": Capability.ENVIRONMENT,
}

# Method names distinctive enough to signal a capability *regardless of the
# receiver*. `path.read_bytes()`, `p.glob("*")`, `entry.is_file()` all reach the
# filesystem, but the receiver is a variable (`path`, `p`, `entry`), so the
# dotted-pattern match — which keys on `Path.read_bytes` — never fires. Keying on
# the method leaf catches I/O through a variable, including inside a comprehension
# or loop body where the receiver is a bound loop variable. Kept to names that
# are unambiguously capability operations, to avoid flagging an arbitrary object
# that happens to have a `.read()`.
_METHOD_CAPABILITIES: dict[str, Capability] = {
    "read_bytes": Capability.FILESYSTEM,
    "read_text": Capability.FILESYSTEM,
    "write_bytes": Capability.FILESYSTEM,
    "write_text": Capability.FILESYSTEM,
    "glob": Capability.FILESYSTEM,
    "rglob": Capability.FILESYSTEM,
    "iterdir": Capability.FILESYSTEM,
    "is_file": Capability.FILESYSTEM,
    "is_dir": Capability.FILESYSTEM,
    "hardlink_to": Capability.FILESYSTEM,
    "symlink_to": Capability.FILESYSTEM,
}


# What each role is permitted to reach for. Everything absent is a violation.
#
# The shape of this table is the architecture:
#
#   pure / normalizer / parser   nothing. They transform what they are handed.
#                                A parser that opens a file is two functions.
#   verifier                     filesystem only. It inspects artifacts, and
#                                artifacts are usually files — but a verifier
#                                that reaches the network is deciding based on
#                                something no negative fixture can control.
#   producer                     filesystem only, for the same reason inverted:
#                                it writes the artifact its verifier inspects.
#   orchestrator                 nothing. Orchestration is wiring; a coordinator
#                                that reaches for a capability instead of
#                                passing one along has stopped coordinating and
#                                started doing.
#   adapter                      everything. This is the designated boundary,
#                                and it is what makes the whole scheme work —
#                                every other role stays testable because
#                                adapters exist to be swapped.
#   presenter                    filesystem, process, environment. It renders
#                                to somewhere, and is proved end-to-end anyway.
ROLE_BUDGET: dict[Role, frozenset[Capability]] = {
    Role.PURE: frozenset(),
    Role.NORMALIZER: frozenset(),
    Role.PARSER: frozenset(),
    Role.VERIFIER: frozenset({Capability.FILESYSTEM}),
    Role.PRODUCER: frozenset({Capability.FILESYSTEM}),
    Role.ORCHESTRATOR: frozenset(),
    Role.ADAPTER: frozenset(Capability),
    Role.PRESENTER: frozenset({Capability.FILESYSTEM, Capability.PROCESS, Capability.ENVIRONMENT}),
}


@dataclass(frozen=True, slots=True)
class AmbientUse:
    """One reach for a capability that was not handed in."""

    capability: Capability
    expression: str
    lineno: int
    callable_key: str
    qualname: str

    def __str__(self) -> str:
        return f"{self.expression} (line {self.lineno})"


@dataclass(frozen=True, slots=True)
class BudgetViolation:
    """An ambient use the callable's role does not permit."""

    use: AmbientUse
    role: Role
    allowed: frozenset[Capability]

    @property
    def message(self) -> str:
        permitted = ", ".join(sorted(c.value for c in self.allowed)) or "nothing"
        return (
            f"{self.use.callable_key} is `{self.role.value}` and reaches for "
            f"{self.use.capability.value} via `{self.use.expression}` at line "
            f"{self.use.lineno}. A `{self.role.value}` may reach for: {permitted}."
        )

    @property
    def remedy(self) -> str:
        return (
            f"Inject it: take `{self.use.capability.value}` as a parameter (or a "
            f"constructor attribute) so a test can substitute one. If this callable "
            f"genuinely is the boundary, its role is `adapter`, not `{self.role.value}`."
        )


def chain(node: ast.expr) -> str | None:
    """Resolve an expression to a dotted string, seeing through common shapes.

    ``Name`` and ``Attribute`` are the easy cases. The other three matter more
    than they look, because idiomatic pathlib hides behind all of them:

    * ``BinOp`` — ``(root / "x.json").read_text()``. Resolving to the *left*
      operand gives ``root.read_text``, which is what we need: the object being
      operated on is ``root``, and if ``root`` is a parameter this is an
      injected filesystem access, not an ambient one.
    * ``Call`` — ``Path("/etc/passwd").read_text()`` resolves to
      ``Path.read_text``, correctly ambient.
    * ``Subscript`` — ``handlers["json"].load()``.

    Getting this wrong is not neutral in one direction. Before these cases were
    handled, both examples above resolved to ``None``: the first produced a
    false "this adapter adapts nothing", and the second silently missed a real
    ambient filesystem read. Under-resolving looks conservative and is not.

    Still returns ``None`` for anything genuinely unresolvable, which stays a
    deliberate under-report — this gate only claims what it can see clearly.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = chain(node.value)
        return f"{base}.{node.attr}" if base else None
    if isinstance(node, ast.BinOp):
        return chain(node.left)
    if isinstance(node, ast.Call):
        return chain(node.func)
    if isinstance(node, ast.Subscript):
        return chain(node.value)
    if isinstance(node, ast.Await):
        return chain(node.value)
    return None


def root_of(node: ast.expr) -> str | None:
    """The leftmost name of an expression, or None if it has none."""
    resolved = chain(node)
    return _root(resolved) if resolved else None


# Kept as the private spelling used throughout this module.
_chain = chain


def _root(dotted: str) -> str:
    return dotted.split(".", 1)[0]


def _match_reads(dotted: str) -> Capability | None:
    """Match an attribute read (no call) against the ambient-read table."""
    for expression, capability in _AMBIENT_READS.items():
        if dotted == expression or dotted.startswith(expression + "."):
            return capability
    return None


def _match(
    dotted: str, capability_patterns: dict[Capability, tuple[str, ...]]
) -> Capability | None:
    """Match a dotted chain against the pattern table by suffix.

    Suffix matching means ``a.b.datetime.now`` matches ``datetime.now``, which
    catches aliased imports without needing to resolve them. It also means the
    match is on the *shape* of the call rather than on import resolution, which
    the AST cannot do reliably anyway.
    """
    for capability, patterns in capability_patterns.items():
        for pattern in patterns:
            if dotted == pattern or dotted.endswith("." + pattern):
                return capability
    return None


class _Scanner(ast.NodeVisitor):
    """Finds ambient capability use within one callable's body.

    ``injected`` holds the names that count as seams: every parameter, plus
    ``self`` and ``cls``. Any chain rooted at one of those is a dependency the
    caller controls, so it is not ambient no matter what it resolves to.
    """

    def __init__(self, injected: frozenset[str], callable_key: str, qualname: str) -> None:
        self.injected = injected
        self.callable_key = callable_key
        self.qualname = qualname
        self.uses: list[AmbientUse] = []
        self._locals: set[str] = set()

    def visit_Assign(self, node: ast.Assign) -> None:
        # A local bound from an injected value stays injected:
        #     def f(clock):
        #         c = clock          # `c` is now a seam too
        #         return c.now()
        source = _chain(node.value)
        if source and _root(source) in (self.injected | self._locals):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._locals.add(target.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        dotted = _chain(node.func)
        if dotted is not None:
            self._consider(dotted, node.lineno)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Some capabilities need no call to be a dependency: reading
        # `os.environ["HOME"]` is already the reach.
        dotted = _chain(node)
        if dotted is not None and _root(dotted) not in self._seams():
            capability = _match_reads(dotted)
            if capability is not None:
                self._record(capability, dotted, node.lineno)
        self.generic_visit(node)

    def _seams(self) -> frozenset[str]:
        return self.injected | frozenset(self._locals)

    def _consider(self, dotted: str, lineno: int) -> None:
        if _root(dotted) in self._seams():
            return
        capability = _BARE.get(dotted) if "." not in dotted else _match(dotted, _PATTERNS)
        if capability is None and "." in dotted:
            # Receiver is a variable (`path.read_bytes()`), so the dotted-pattern
            # match on `Path.read_bytes` missed it. Fall back to the method leaf,
            # which is distinctive enough to name the capability on its own.
            capability = _METHOD_CAPABILITIES.get(dotted.rsplit(".", 1)[-1])
        if capability is not None:
            self._record(capability, dotted, lineno)

    def _record(self, capability: Capability, expression: str, lineno: int) -> None:
        use = AmbientUse(capability, expression, lineno, self.callable_key, self.qualname)
        if use not in self.uses:
            self.uses.append(use)


def scan_callable(
    node: ast.FunctionDef | ast.AsyncFunctionDef, info: CallableInfo
) -> list[AmbientUse]:
    """Every ambient capability use inside one callable."""
    args = node.args
    injected = {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
    if args.vararg:
        injected.add(args.vararg.arg)
    if args.kwarg:
        injected.add(args.kwarg.arg)
    injected |= {"self", "cls"}

    scanner = _Scanner(frozenset(injected), info.key, info.qualname)
    for stmt in node.body:
        scanner.visit(stmt)
    return scanner.uses


def violations(
    uses: list[AmbientUse], role: Role, ambient_ok: frozenset[Capability] = frozenset()
) -> list[BudgetViolation]:
    """Ambient uses that neither the role's budget nor the app's allow-list permits.

    ``ambient_ok`` is an app-declared set of capabilities that are its tested
    domain medium (filesystem for a file-processing tool, say) rather than an
    injectable side effect — permitted ambiently for *every* role. It defaults
    empty, so the strict per-role budget is unchanged unless a project opts in.
    """
    allowed = ROLE_BUDGET.get(role, frozenset()) | ambient_ok
    return [
        BudgetViolation(use=use, role=role, allowed=allowed)
        for use in uses
        if use.capability not in allowed
    ]
