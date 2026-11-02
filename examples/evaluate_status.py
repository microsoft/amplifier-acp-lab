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
        if len(functions) != 1 or len(tree.body) != 1 or functions[0].name != "profile_status" or functions[0].decorator_list:
            raise ValueError("Expected only the profile_status function")
        namespace = {}
        exec(compile(tree, "<observed-artifact>", "exec"), {"__builtins__": {}}, namespace)
        function = namespace["profile_status"]
        cases = [
            (None, None, "completed", "unknown"),
            ("v1", None, "completed", "unknown"),
            (None, "v1", "in_progress", "unknown"),
            ("v1", None, "interrupted", "unknown"),
            ("v1", "v1", "completed", "current"),
            ("v2", "v1", "completed", "previous"),
            ("v1", "v1", "in_progress", "partial"),
            ("v2", "v1", "interrupted", "partial"),
            ("v1", "v1", "unknown", "unknown"),
        ]
        for installed, supplied, state, expected in cases:
            actual = function(installed, supplied, state)
            checks.append({"name": f"{installed}/{supplied}/{state}", "passed": actual == expected,
                           "expected": expected, "actual": actual})
    except Exception as exc:
        checks.append({"name": "restricted-function validation", "passed": False, "detail": str(exc)})
    print(json.dumps({"artifact_sha256": sha, "checks": checks}))
    return 0 if all(check["passed"] for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
