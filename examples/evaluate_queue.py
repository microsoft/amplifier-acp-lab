#!/usr/bin/env python3
"""Operator-owned evaluator for one intentionally restricted pure function.

The artifact's AST is restricted before execution, and has no calls, imports,
attributes, loops, comprehensions, or builtins. This is a narrow verifier, not a
general code sandbox. The lab also enforces this evaluator's process timeout.
"""
import ast
import hashlib
import json
import sys


def main():
    request = json.load(sys.stdin)
    content = request["content"]
    sha = hashlib.sha256(content.encode()).hexdigest()
    checks = []
    try:
        tree = ast.parse(content)
        allowed = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.If, ast.Return,
                   ast.Compare, ast.Name, ast.Constant, ast.Load, ast.Eq, ast.NotEq,
                   ast.Is, ast.IsNot, ast.In, ast.NotIn, ast.BoolOp, ast.And, ast.Or,
                   ast.UnaryOp, ast.Not, ast.Tuple, ast.List, ast.Expr)
        if any(not isinstance(node, allowed) for node in ast.walk(tree)):
            raise ValueError("Use only the agreed pure-function subset")
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        if len(functions) != 1 or len(tree.body) != 1 or functions[0].name != "queue_label" or functions[0].decorator_list:
            raise ValueError("Expected only the queue_label function")
        namespace = {}
        exec(compile(tree, "<observed-artifact>", "exec"), {"__builtins__": {}}, namespace)
        function = namespace["queue_label"]
        import itertools
        for accepted, current, stopped, busy, ready in itertools.product((None, "", "v1", "v2"), (None, "", "v1", "v2"), (False, True), (False, True), (False, True)):
            expected = ("released" if stopped else "unknown" if accepted is None or current is None else "review" if accepted != current else "working" if busy else "ready" if ready else "waiting")
            actual = function(accepted, current, stopped, busy, ready)
            checks.append({"name": f"{accepted}/{current}/{stopped}/{busy}/{ready}", "passed": actual == expected, "expected": expected, "actual": actual})
    except Exception as exc:
        checks.append({"name": "restricted-function validation", "passed": False, "detail": str(exc)})
    print(json.dumps({"artifact_sha256": sha, "checks": checks}))
    return 0 if all(check["passed"] for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
