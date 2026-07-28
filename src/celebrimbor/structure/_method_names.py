"""Method-name sets the evidence facts key on. Data, not logic.

Split out of ``evidence.py`` so that module stays under its own length budget and
so the distinction is legible: these are vocabularies of Python method names,
consulted by the fact extractors, and they change for different reasons than the
role conditions do.
"""

from __future__ import annotations

# Methods that operate on plain values rather than on a resource. Calling one of
# these on a parameter is not evidence of a backend — ``text.strip()`` and
# ``db.execute()`` are both "a call on something injected", and only the second
# means anything. Without this stoplist the adapter condition would be satisfied
# by any function that uses its own arguments, i.e. all of them.
VALUE_METHODS = frozenset(
    {
        "strip",
        "lstrip",
        "rstrip",
        "upper",
        "lower",
        "title",
        "capitalize",
        "casefold",
        "split",
        "rsplit",
        "splitlines",
        "join",
        "format",
        "replace",
        "startswith",
        "endswith",
        "encode",
        "decode",
        "partition",
        "rpartition",
        "removeprefix",
        "removesuffix",
        "zfill",
        "ljust",
        "rjust",
        "count",
        "index",
        "find",
        "get",
        "items",
        "keys",
        "values",
        "copy",
        "isdigit",
        "isalpha",
        "isspace",
        "isupper",
        "islower",
        "as_posix",
        "is_dir",
        "is_file",
        "exists",
        "with_suffix",
        "relative_to",
        "resolve",
    }
)

# I/O verbs — method names that name a backend interaction on any receiver.
# ``adapters.process_runner.run(...)``, ``transport.get(url)``,
# ``cursor.execute(sql)`` are all doing I/O even though the receiver is a
# module, an injected transport, or a connection the pattern-matcher does not
# recognise as a capability. A call to one of these satisfies the ``adapter``
# role (it is adapting *something*), while leaving the escape guard intact: an
# inert ``text.strip().upper()`` uses value methods, not these, so a pure
# function dressed as an adapter is still contradicted. Only the ``adapter``
# condition consults this, so a false hit cannot weaken any other role.
IO_METHODS = frozenset(
    {
        "get",
        "post",
        "put",
        "delete",
        "patch",
        "head",
        "request",
        "fetch",
        "download",
        "upload",
        "send",
        "sendall",
        "recv",
        "execute",
        "executemany",
        "query",
        "poll",
        "submit",
        "connect",
        "commit",
        "rollback",
        "run",
        "publish",
        "subscribe",
        "invoke",
    }
)

# In-place mutators. A call to one of these on ``self`` (or a parameter) mutates
# state even though there is no assignment — ``self._jobs.append(x)``, unlike
# ``self._jobs = [...]``, is a method call, not a Store. A stateful fake usually
# mutates this way, so missing it would leave the fake looking inert.
MUTATING_METHODS = frozenset(
    {
        "append",
        "extend",
        "insert",
        "add",
        "discard",
        "remove",
        "pop",
        "clear",
        "update",
        "setdefault",
        "popitem",
        "sort",
        "appendleft",
        "popleft",
    }
)
