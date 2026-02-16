#!/usr/bin/env python3
"""Generate a project-wide PlantUML class diagram from Python sources."""

from __future__ import annotations

import ast
import argparse
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


IGNORED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".cache",
    "pipeline_runs_v2",
    "price_history",
    "runtime_history",
    "session_transcripts",
}

IGNORED_TOKENS = {
    "Any",
    "Dict",
    "List",
    "Set",
    "Tuple",
    "Optional",
    "Union",
    "Literal",
    "Callable",
    "Iterable",
    "Sequence",
    "Mapping",
    "MutableMapping",
    "Iterator",
    "Generator",
    "ClassVar",
    "Final",
    "Annotated",
    "Self",
    "Type",
    "object",
    "str",
    "int",
    "float",
    "bool",
    "bytes",
    "dict",
    "list",
    "set",
    "tuple",
    "None",
    "ABC",
    "Protocol",
    "unittest",
    "dataclass",
    "field",
}

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_\.]*")


@dataclass
class ModuleInfo:
    module: str
    imports: dict[str, str] = field(default_factory=dict)


@dataclass
class ClassInfo:
    module: str
    file_path: Path
    name: str
    full_name: str
    bases: list[str] = field(default_factory=list)
    decorators: set[str] = field(default_factory=set)
    attributes: dict[str, str] = field(default_factory=dict)
    methods: list[str] = field(default_factory=list)

    @property
    def is_abstract(self) -> bool:
        if "abstractmethod" in self.decorators:
            return True
        return any(base.endswith("ABC") for base in self.bases)

    @property
    def stereotype(self) -> str:
        tags: list[str] = []
        if "dataclass" in self.decorators:
            tags.append("dataclass")
        if self.is_abstract:
            tags.append("abstract")
        return ", ".join(tags)


def should_skip(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


def module_from_path(root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else "__root__"


def safe_unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def decorator_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return decorator_name(node.func)
    return safe_unparse(node)


def parse_imports(module_node: ast.Module) -> dict[str, str]:
    imports: dict[str, str] = {}
    for node in module_node.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[-1]
                imports[local] = alias.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                imports[local] = f"{mod}.{alias.name}" if mod else alias.name
    return imports


def parse_class(module: str, file_path: Path, node: ast.ClassDef) -> ClassInfo:
    full_name = f"{module}.{node.name}"
    info = ClassInfo(
        module=module,
        file_path=file_path,
        name=node.name,
        full_name=full_name,
        bases=[safe_unparse(base) for base in node.bases if safe_unparse(base)],
        decorators={decorator_name(dec) for dec in node.decorator_list},
    )

    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            attr = item.target.id
            info.attributes[attr] = safe_unparse(item.annotation) or "Any"
        elif isinstance(item, ast.FunctionDef):
            if item.name == "__init__":
                for stmt in item.body:
                    if (
                        isinstance(stmt, ast.AnnAssign)
                        and isinstance(stmt.target, ast.Attribute)
                        and isinstance(stmt.target.value, ast.Name)
                        and stmt.target.value.id == "self"
                    ):
                        info.attributes[stmt.target.attr] = safe_unparse(stmt.annotation) or "Any"
            if not item.name.startswith("__"):
                info.methods.append(item.name)

    return info


def collect_classes(root: Path, include_tests: bool) -> tuple[dict[str, ClassInfo], dict[str, ModuleInfo]]:
    classes: dict[str, ClassInfo] = {}
    modules: dict[str, ModuleInfo] = {}

    for file_path in sorted(root.rglob("*.py")):
        if should_skip(file_path):
            continue
        if not include_tests and "tests" in file_path.parts:
            continue
        source = file_path.read_text(encoding="utf-8")
        try:
            module_node = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            continue
        module = module_from_path(root, file_path)
        modules[module] = ModuleInfo(module=module, imports=parse_imports(module_node))

        for node in module_node.body:
            if isinstance(node, ast.ClassDef):
                class_info = parse_class(module, file_path, node)
                classes[class_info.full_name] = class_info

    return classes, modules


def collect_name_index(classes: dict[str, ClassInfo]) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = defaultdict(list)
    for full_name, class_info in classes.items():
        idx[class_info.name].append(full_name)
    return idx


def expand_token(token: str, imports: dict[str, str]) -> str:
    if "." not in token:
        return imports.get(token, token)
    head, _, tail = token.partition(".")
    if head in imports:
        return f"{imports[head]}.{tail}"
    return token


def resolve_ref(
    token: str,
    current_module: str,
    imports: dict[str, str],
    classes: dict[str, ClassInfo],
    name_index: dict[str, list[str]],
) -> str | None:
    expanded = expand_token(token, imports)
    if expanded in classes:
        return expanded

    simple = expanded.rsplit(".", 1)[-1]
    if simple in name_index:
        matches = name_index[simple]
        if len(matches) == 1:
            return matches[0]
        in_same_module = [m for m in matches if classes[m].module == current_module]
        if len(in_same_module) == 1:
            return in_same_module[0]
    return None


def type_tokens(type_expr: str) -> list[str]:
    tokens = TOKEN_RE.findall(type_expr)
    return [tok for tok in tokens if tok not in IGNORED_TOKENS]


def build_edges(
    classes: dict[str, ClassInfo],
    modules: dict[str, ModuleInfo],
) -> tuple[set[tuple[str, str]], set[tuple[str, str, str]]]:
    name_index = collect_name_index(classes)
    inheritance_edges: set[tuple[str, str]] = set()
    association_edges: set[tuple[str, str, str]] = set()

    for full_name, info in classes.items():
        imports = modules.get(info.module, ModuleInfo(info.module)).imports

        for base in info.bases:
            for token in type_tokens(base):
                target = resolve_ref(token, info.module, imports, classes, name_index)
                if target and target != full_name:
                    inheritance_edges.add((full_name, target))

        for attr, type_expr in info.attributes.items():
            for token in type_tokens(type_expr):
                target = resolve_ref(token, info.module, imports, classes, name_index)
                if target and target != full_name:
                    association_edges.add((full_name, target, attr))

    return inheritance_edges, association_edges


def build_plantuml(
    classes: dict[str, ClassInfo],
    inheritance_edges: set[tuple[str, str]],
    association_edges: set[tuple[str, str, str]],
) -> str:
    alias_by_class: dict[str, str] = {}
    for i, full_name in enumerate(sorted(classes), start=1):
        alias_by_class[full_name] = f"C{i}"

    grouped: dict[str, list[ClassInfo]] = defaultdict(list)
    for class_info in classes.values():
        grouped[class_info.module or "__root__"].append(class_info)

    lines: list[str] = [
        "@startuml",
        "title Trading Agent - Diagramme de classes (Python)",
        "left to right direction",
        "skinparam classAttributeIconSize 0",
        "skinparam packageStyle rectangle",
        "skinparam linetype ortho",
        "hide empty members",
        "",
    ]

    for module_name in sorted(grouped):
        lines.append(f'package "{module_name}" {{')
        for cls in sorted(grouped[module_name], key=lambda c: c.name):
            alias = alias_by_class[cls.full_name]
            if cls.stereotype:
                lines.append(f'  class "{cls.name}" as {alias} <<{cls.stereotype}>> {{')
            else:
                lines.append(f'  class "{cls.name}" as {alias} {{')

            for attr, typ in sorted(cls.attributes.items()):
                lines.append(f"    +{attr}: {typ}")
            for method in sorted(set(cls.methods)):
                lines.append(f"    +{method}()")

            lines.append("  }")
        lines.append("}")
        lines.append("")

    for source, target in sorted(inheritance_edges):
        lines.append(f"{alias_by_class[source]} --|> {alias_by_class[target]}")

    for source, target, attr in sorted(association_edges):
        label = attr.replace('"', "")
        lines.append(f'{alias_by_class[source]} --> {alias_by_class[target]} : "{label}"')

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PlantUML class diagram.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project root to scan (default: cwd).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/diagrams/project_class_diagram.puml"),
        help="Output PlantUML file path.",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Include classes under tests/.",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    classes, modules = collect_classes(root, include_tests=args.include_tests)
    inheritance_edges, association_edges = build_edges(classes, modules)
    plantuml_text = build_plantuml(classes, inheritance_edges, association_edges)

    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(plantuml_text, encoding="utf-8")

    print(f"Generated: {output}")
    print(f"Classes: {len(classes)}")
    print(f"Inheritance edges: {len(inheritance_edges)}")
    print(f"Association edges: {len(association_edges)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
