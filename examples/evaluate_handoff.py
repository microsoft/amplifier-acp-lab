#!/usr/bin/env python3
"""Independently check the exact delivered handoff function in a narrow subset."""
import ast
import hashlib
import itertools
import json
import sys


def main():
    content = json.load(sys.stdin)["content"]
    sha = hashlib.sha256(content.encode()).hexdigest()
    checks = []
    try:
        tree = ast.parse(content)
        allowed = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.If, ast.Return,
                   ast.Compare, ast.Name, ast.Constant, ast.Load, ast.Eq, ast.NotEq,
                   ast.Is, ast.IsNot, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not)
        if any(not isinstance(node, allowed) for node in ast.walk(tree)):
            raise ValueError("Only the agreed pure-function subset is accepted")
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
            raise ValueError("Expected one function")
        function = tree.body[0]
        if function.name != "handoff_state" or function.decorator_list or function.returns or function.args.defaults or function.args.kw_defaults or function.args.vararg or function.args.kwarg or function.args.posonlyargs or function.args.kwonlyargs:
            raise ValueError("Use only the three agreed positional arguments without defaults")
        if [arg.arg for arg in function.args.args] != ["owner", "accepted", "blocked"] or any(arg.annotation for arg in function.args.args):
            raise ValueError("Expected owner, accepted, blocked")
        namespace = {}
        exec(compile(tree, "<observed-artifact>", "exec"), {"__builtins__": {}}, namespace)
        for owner, accepted, blocked in itertools.product((None, "", "Builder"), (False, True), (False, True)):
            expected = "unassigned" if owner is None else "offered" if not accepted else "blocked" if blocked else "active"
            actual = namespace["handoff_state"](owner, accepted, blocked)
            checks.append({"name": f"{owner!r}/{accepted}/{blocked}", "passed": actual == expected, "expected": expected, "actual": actual})
    except Exception as exc:
        checks.append({"name": "restricted-function validation", "passed": False, "detail": str(exc)})
    print(json.dumps({"artifact_sha256": sha, "checks": checks}))
    return 0 if all(item["passed"] for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
