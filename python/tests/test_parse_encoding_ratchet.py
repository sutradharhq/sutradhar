"""Class ratchet: every file a guard parses is read as `utf-8-sig` (R25-2).

R24-27 moved swallow, interpolation and conflated-degrade to `utf-8-sig`,
because a byte-order mark read as `utf-8` reaches `ast.parse` as a
character it refuses, and a file Python imports and runs was reported as
unparsable. It missed `detectors.py` and `framework_only.py`: a sibling fix
with no class check behind it, found a round later by the corpus sweep.

This walks every module in `sutradhar_guards/` by AST, not grep. A *sink*
is `ast.parse` or any function whose parameter reaches a sink (to a fixed
point, across modules by bare name, so `check_file -> check_source ->
_parse -> ast.parse` is one chain). At every sink call it resolves the
argument back - through local assignments, `with open(...) as fh`, and the
return statements of same-package reader functions - to where the text
was read. A `read_text` / `open` / `.decode` whose encoding is not
`utf-8-sig` (or is left to the locale) is a violation. Bytes go straight
to the parser, which reads a BOM correctly, and are allowed.

What it cannot see, said here so nobody reads its green as more (2.9):
Python held in string constants (the corpus runner bodies in corpus.py),
reads behind dynamic dispatch, and readers outside this package. An
argument it can neither resolve to a read nor to non-file text (a literal)
is a third outcome, `unresolved`, and fails the test as well: a feed the
ratchet cannot follow is not one it has passed.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

GUARDS = Path(__file__).resolve().parents[1] / "sutradhar_guards"
WANT = "utf-8-sig"
_LOCALE = "<locale default>"


def _own_nodes(fn: ast.AST):
    """Nodes of `fn`'s body, not descending into nested defs or classes."""
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _callee(call: ast.Call) -> str | None:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        if isinstance(f.value, ast.Name) and f.value.id == "ast" and f.attr == "parse":
            return "ast.parse"
        return f.attr
    return None


def _kw(call: ast.Call, name: str, pos: int):
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return call.args[pos] if len(call.args) > pos else None


def _encoding(node) -> str:
    if node is None:
        return _LOCALE
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.lower().replace("_", "-")
    return f"<dynamic: {ast.unparse(node) if hasattr(ast, 'unparse') else '?'}>"


class _Scope:
    def __init__(self, module: str, fn: ast.AST, params: list[str]):
        self.module, self.fn, self.params = module, fn, params


class Analysis:
    """Sinks, resolved reads, and anything that could not be followed."""

    def __init__(self, sources: dict[str, str]):
        self.trees = {m: ast.parse(src.lstrip("﻿")) for m, src in sources.items()}
        # name -> [(module, def)]; bare names, so cross-module calls resolve.
        self.defs: dict[str, list] = {}
        self.scopes: list[_Scope] = []
        for m, tree in self.trees.items():
            self.scopes.append(_Scope(m, tree, []))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.defs.setdefault(node.name, []).append((m, node))
                    a = node.args
                    params = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
                    self.scopes.append(_Scope(m, node, params))
        # sink name -> set of parameter names that reach ast.parse
        self.sinks: dict[str, set[str]] = {"ast.parse": {"source"}}
        self.reads: list[tuple[str, int, str]] = []        # (module, line, encoding)
        self.unresolved: list[tuple[str, int, str]] = []
        self._fixpoint()

    # -- which argument of a call reaches the parser -------------------------
    def _sink_args(self, call: ast.Call) -> list:
        name = _callee(call)
        if name == "ast.parse":
            arg = _kw(call, "source", 0)
            return [arg] if arg is not None else []
        if name not in self.sinks:
            return []
        out = []
        for _m, d in self.defs.get(name, []):
            a = d.args
            pos = [x.arg for x in a.posonlyargs + a.args]
            if isinstance(call.func, ast.Attribute) and pos[:1] in (["self"], ["cls"]):
                pos = pos[1:]
            for p in self.sinks[name]:
                if p in pos:
                    v = _kw(call, p, pos.index(p))
                else:
                    v = next((k.value for k in call.keywords if k.arg == p), None)
                if v is not None:
                    out.append(v)
        return out

    # -- resolve an expression back to where its text was read ---------------
    def _resolve(self, expr, scope: _Scope, seen: set, out: dict) -> None:
        key = (id(expr), id(scope.fn))
        if key in seen:
            return
        seen.add(key)
        line = getattr(expr, "lineno", 0)
        if isinstance(expr, ast.Constant):
            return  # literal text, not file contents
        if isinstance(expr, ast.JoinedStr):
            return
        if isinstance(expr, ast.BinOp):  # "﻿" + body, prefix + text
            self._resolve(expr.left, scope, seen, out)
            self._resolve(expr.right, scope, seen, out)
            return
        if isinstance(expr, ast.Subscript):
            self._resolve(expr.value, scope, seen, out)
            return
        if isinstance(expr, ast.Name):
            if expr.id in scope.params:
                out["params"].add(expr.id)
                return
            bound = False
            for node in _own_nodes(scope.fn):
                if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    if any(isinstance(t, ast.Name) and t.id == expr.id for t in targets):
                        if node.value is not None:
                            bound = True
                            self._resolve(node.value, scope, seen, out)
                elif isinstance(node, ast.withitem):
                    v = node.optional_vars
                    if isinstance(v, ast.Name) and v.id == expr.id:
                        bound = True
                        self._resolve(node.context_expr, scope, seen, out)
                elif isinstance(node, (ast.For, ast.AsyncFor)) and any(
                        isinstance(t, ast.Name) and t.id == expr.id
                        for t in ast.walk(node.target)):
                    bound = True
                    # A loop over a literal table of fixtures: every element
                    # is followed (over-approximating which slot is ours).
                    if isinstance(node.iter, (ast.Tuple, ast.List)):
                        for el in node.iter.elts:
                            for part in (el.elts if isinstance(el, (ast.Tuple, ast.List))
                                         else [el]):
                                self._resolve(part, scope, seen, out)
                    else:
                        out["unresolved"].append(
                            (scope.module, line, f"loop variable {expr.id}"))
            if not bound and scope.fn is not self.trees[scope.module]:
                # a module-level name (a constant fixture) - resolve there
                mod = _Scope(scope.module, self.trees[scope.module], [])
                self._resolve(expr, mod, seen, out)
                return
            if not bound:
                out["unresolved"].append((scope.module, line, ast.dump(expr)[:80]))
            return
        if isinstance(expr, ast.Call):
            name = _callee(expr)
            f = expr.func
            if name == "read_text":
                out["reads"].append((scope.module, line, _encoding(_kw(expr, "encoding", 0))))
                return
            if name in ("read_bytes",):
                return  # bytes: the parser reads a BOM itself
            if name == "open":
                mode = _kw(expr, "mode", 1)
                if isinstance(mode, ast.Constant) and "b" in str(mode.value):
                    return
                out["reads"].append((scope.module, line, _encoding(_kw(expr, "encoding", 3))))
                return
            if name == "decode":
                enc = _kw(expr, "encoding", 0)
                out["reads"].append((scope.module, line,
                                     "utf-8" if enc is None else _encoding(enc)))
                return
            if name in ("read", "strip", "lstrip", "rstrip", "replace", "expandtabs") \
                    and isinstance(f, ast.Attribute):
                self._resolve(f.value, scope, seen, out)
                return
            if name in ("join", "format") and isinstance(f, ast.Attribute):
                for a in expr.args:
                    self._resolve(a, scope, seen, out)
                return
            if name in self.defs:
                for m, d in self.defs[name]:
                    inner = _Scope(m, d, [])  # its params are its caller's business
                    for node in _own_nodes(d):
                        if isinstance(node, ast.Return) and node.value is not None:
                            self._resolve(node.value, inner, seen, out)
                return
            out["unresolved"].append((scope.module, line, f"call to {name}()"))
            return
        out["unresolved"].append((scope.module, line, type(expr).__name__))

    def _fixpoint(self) -> None:
        changed = True
        while changed:
            changed = False
            self.reads, self.unresolved = [], []
            for scope in self.scopes:
                for node in _own_nodes(scope.fn):
                    if not isinstance(node, ast.Call):
                        continue
                    for arg in self._sink_args(node):
                        out = {"params": set(), "reads": [], "unresolved": []}
                        self._resolve(arg, scope, set(), out)
                        self.reads += out["reads"]
                        self.unresolved += out["unresolved"]
                        if out["params"] and isinstance(
                                scope.fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            have = self.sinks.setdefault(scope.fn.name, set())
                            if not out["params"] <= have:
                                have |= out["params"]
                                changed = True

    def violations(self) -> list[str]:
        return sorted({f"{m}:{line}: file text reaches ast.parse read as {enc}, "
                       f"not {WANT}" for m, line, enc in self.reads if enc != WANT})


def _package_sources() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8-sig")
            for p in sorted(GUARDS.glob("*.py"))}


def test_every_parsed_file_is_read_as_utf8_sig():
    a = Analysis(_package_sources())
    assert not a.violations(), (
        "a guard parses file text it read with an encoding other than "
        "utf-8-sig; a BOM-prefixed file Python imports will read as "
        "unparsable (R24-27, R25-2):\n  " + "\n  ".join(a.violations()))


def test_every_parse_feed_was_followed():
    a = Analysis(_package_sources())
    assert not a.unresolved, (
        "the ratchet could not follow these arguments back to a read; it "
        "has not judged them (2.9):\n  "
        + "\n  ".join(f"{m}:{l}: {w}" for m, l, w in a.unresolved))


def test_the_walk_reached_every_known_reader():
    # Vacuity floor: a resolver that silently stopped following chains would
    # find no reads at all and pass. These five modules each read files and
    # parse them today; each must contribute at least one resolved read.
    a = Analysis(_package_sources())
    reached = {m for m, _l, _e in a.reads}
    want = {"detectors.py", "framework_only.py", "swallow_lint.py",
            "interpolation_lint.py", "conflated_degrade_lint.py"}
    assert want <= reached, f"no resolved read in {sorted(want - reached)}"


# ── the ratchet's own pair: a known-bad it must flag, a known-good it must not

_CHAIN = '''
import ast
def _parse(source):
    return ast.parse(source)
def check_source(source):
    return _parse(source)
def read_source(path):
    return path.read_text(encoding="{enc}", errors="replace")
def check_file(path):
    return check_source(read_source(path))
'''

_DIRECT = '''
import ast
def walk(root):
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="{enc}", errors="replace"))
'''

_VIA_WITH = '''
import ast
def roots(path):
    with open(path{enc}) as fh:
        text = fh.read()
    return ast.parse(text)
'''


def test_ratchet_flags_the_r24_27_shape_through_a_call_chain():
    # The shape the three lints had before R24-27: read_source -> check_source
    # -> _parse -> ast.parse, with the read three calls away from the parse.
    bad = Analysis({"lint.py": _CHAIN.format(enc="utf-8")})
    assert [v.split(":")[0] for v in bad.violations()] == ["lint.py"]
    assert Analysis({"lint.py": _CHAIN.format(enc="utf-8-sig")}).violations() == []


def test_ratchet_flags_a_direct_read_and_a_locale_default():
    assert Analysis({"d.py": _DIRECT.format(enc="utf-8")}).violations()
    assert not Analysis({"d.py": _DIRECT.format(enc="utf-8-sig")}).violations()
    locale = Analysis({"w.py": _VIA_WITH.format(enc="")})
    assert locale.violations() and _LOCALE in locale.violations()[0]
    assert not Analysis({"w.py": _VIA_WITH.format(enc=', encoding="utf-8-sig"')}).violations()


def test_ratchet_follows_a_sink_across_modules():
    # framework_only's shape: the parse lives in a helper taking `source`,
    # and the read is at the call site in another function.
    helper = "import ast\ndef _roots(source):\n    return ast.parse(source)\n"
    caller = 'def scan(py):\n    return _roots(py.read_text(encoding="utf-8"))\n'
    a = Analysis({"h.py": helper, "c.py": caller})
    assert [v.split(":")[0] for v in a.violations()] == ["c.py"]


if __name__ == "__main__":  # pragma: no cover - manual runs against any tree
    a = Analysis({Path(p).name: Path(p).read_text(encoding="utf-8-sig")
                  for p in sys.argv[1:]})
    for v in a.violations():
        print(v)
    for m, l, w in a.unresolved:
        print(f"{m}:{l}: UNRESOLVED {w}")
    print(f"{len(a.reads)} read(s) resolved, {len(a.violations())} violation(s), "
          f"{len(a.unresolved)} unresolved")
    raise SystemExit(1 if a.violations() or a.unresolved else 0)
