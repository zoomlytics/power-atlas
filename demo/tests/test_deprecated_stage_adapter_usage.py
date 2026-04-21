from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


DEPRECATED_STAGE_ADAPTERS = {
    "run_pdf_ingest",
    "run_claim_and_mention_extraction",
    "run_entity_resolution",
}

ALLOWED_DIRECT_CALLS = {
    ("test_orchestrator_modules.py", None, "test_pdf_ingest_config_first_adapter_warns_deprecated", "run_pdf_ingest"),
    (
        "test_orchestrator_modules.py",
        None,
        "test_claim_extraction_config_first_adapter_warns_deprecated",
        "run_claim_and_mention_extraction",
    ),
    (
        "test_orchestrator_modules.py",
        None,
        "test_entity_resolution_config_first_adapter_warns_deprecated",
        "run_entity_resolution",
    ),
    (
        "test_entity_resolution.py",
        "TestRunEntityResolutionDryRun",
        "test_config_first_adapter_warns_deprecated",
        "run_entity_resolution",
    ),
}


@dataclass(frozen=True)
class AdapterCallSite:
    path: str
    class_name: str | None
    function_name: str
    adapter_name: str
    line: int


class _DeprecatedAdapterCallCollector(ast.NodeVisitor):
    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self.class_stack: list[str] = []
        self.function_stack: list[str] = []
        self.call_sites: list[AdapterCallSite] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        adapter_name = self._resolve_adapter_name(node.func)
        function_name = self.function_stack[-1] if self.function_stack else "<module>"
        if adapter_name in DEPRECATED_STAGE_ADAPTERS and function_name.startswith("test"):
            self.call_sites.append(
                AdapterCallSite(
                    path=self.relative_path,
                    class_name=self.class_stack[-1] if self.class_stack else None,
                    function_name=function_name,
                    adapter_name=adapter_name,
                    line=node.lineno,
                )
            )
        self.generic_visit(node)

    @staticmethod
    def _resolve_adapter_name(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None


def _collect_deprecated_stage_adapter_calls() -> list[AdapterCallSite]:
    tests_dir = Path(__file__).resolve().parent
    call_sites: list[AdapterCallSite] = []
    for path in sorted(tests_dir.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        collector = _DeprecatedAdapterCallCollector(path.name)
        collector.visit(tree)
        call_sites.extend(collector.call_sites)
    return call_sites


def test_deprecated_stage_adapters_are_only_called_by_explicit_compatibility_tests() -> None:
    call_sites = _collect_deprecated_stage_adapter_calls()
    actual = {
        (site.path, site.class_name, site.function_name, site.adapter_name)
        for site in call_sites
    }

    assert actual == ALLOWED_DIRECT_CALLS, (
        "Direct calls to deprecated config-first stage adapters are only allowed in explicit "
        "compatibility tests. Unexpected call sites: "
        f"{sorted(actual - ALLOWED_DIRECT_CALLS)}. Missing expected anchors: {sorted(ALLOWED_DIRECT_CALLS - actual)}"
    )