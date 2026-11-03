#!/usr/bin/env python3
"""Source-aware documentation lookup for PassDeployer coding agents.

Standard-library only. Run:
  python scripts/agent_docs.py search ServiceRevision --kind model --json
  python scripts/agent_docs.py search "/agent/v1/services/{service_id}/rebuild" --kind api --json
  python scripts/agent_docs.py search "runtime reconciliation" --kind system
  python scripts/agent_docs.py audit --json
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DOCS = ROOT / "documentation"
WORD = re.compile(r"[^\W_]+|_[a-z0-9_]+", re.IGNORECASE)
MODEL_BASES = {"Model", "BaseModel", "AbstractBaseUser", "AbstractUser", "Page", "BaseGenericSetting", "ClusterableModel", "Orderable"}


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def words(value: str) -> list[str]:
    return [x.casefold() for x in WORD.findall(value or "")]


def name_of(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = name_of(node.value)
        return parent + "." + node.attr if parent else node.attr
    if isinstance(node, ast.Call):
        return name_of(node.func)
    return ""


def string_arg(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def source_app(path: Path) -> str:
    try:
        parts = path.relative_to(SRC).parts
        return parts[0] if len(parts) > 1 else ""
    except ValueError:
        return ""


def doc_kind(path: Path) -> str:
    name = path.name.lower()
    if "model" in name or "field-reference" in name:
        return "model"
    if "api" in name or "contracts" in name:
        return "api"
    if any(x in name for x in ("architecture", "background", "state-contracts", "invariants", "control-plane")):
        return "system"
    if "execution" in path.parts or "proposals" in path.parts:
        return "system"
    return "all"


def docs_index() -> list[dict]:
    paths = set(DOCS.rglob("*.md")) if DOCS.exists() else set()
    paths.update(x for x in (ROOT / "README.md", SRC / "agent" / "README.md") if x.exists())
    results = []
    for path in sorted(paths):
        current_title = path.stem.replace("-", " ").replace("_", " ").title()
        current_line = 1
        body: list[str] = []
        for line_no, line in enumerate(read(path).splitlines(), 1):
            match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
            if match:
                if body:
                    text = "\n".join(body).strip()
                    if text:
                        app = ""
                        try:
                            bits = path.relative_to(DOCS).parts
                            if len(bits) > 1 and bits[0] == "apps":
                                app = bits[1]
                        except ValueError:
                            pass
                        results.append({
                            "kind": doc_kind(path), "title": current_title,
                            "path": rel(path), "line": current_line,
                            "app": app, "source": False, "summary": text[:2200],
                            "search_text": text,
                        })
                current_title = match.group(1).strip()
                current_line = line_no
                body = [line]
            else:
                body.append(line)
        text = "\n".join(body).strip()
        if text:
            app = ""
            try:
                bits = path.relative_to(DOCS).parts
                if len(bits) > 1 and bits[0] == "apps":
                    app = bits[1]
            except ValueError:
                pass
            results.append({
                "kind": doc_kind(path), "title": current_title,
                "path": rel(path), "line": current_line,
                "app": app, "source": False, "summary": text[:2200],
                "search_text": text,
            })
    return results


def model_inventory() -> tuple[list[dict], dict[str, list[dict]]]:
    all_models = []
    per_app: dict[str, list[dict]] = defaultdict(list)
    for path in sorted(SRC.rglob("models.py")):
        if "migrations" in path.parts or "wagtail_admin" in path.parts:
            continue
        try:
            tree = ast.parse(read(path), filename=rel(path))
        except SyntaxError:
            continue
        app = source_app(path)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(name_of(base).rsplit(".", 1)[-1] in MODEL_BASES for base in node.bases):
                continue
            field_names = []
            relation_fields = {
                "ForeignKey", "OneToOneField", "ManyToManyField", "ArrayField",
                "ParentalKey", "GenericRelation", "GenericForeignKey",
            }
            for item in node.body:
                value = item.value if isinstance(item, (ast.Assign, ast.AnnAssign)) else None
                targets = item.targets if isinstance(item, ast.Assign) else [item.target] if isinstance(item, ast.AnnAssign) else []
                if not isinstance(value, ast.Call):
                    continue
                field_type = name_of(value.func).rsplit(".", 1)[-1]
                if not field_type.endswith("Field") and field_type not in relation_fields:
                    continue
                field_names.extend(target.id for target in targets if isinstance(target, ast.Name))
            doc = ast.get_docstring(node) or "Django model."
            item = {
                "kind": "model", "title": node.name, "path": rel(path),
                "line": node.lineno, "app": app, "source": True,
                "summary": doc + "\nDeclared fields: " + (", ".join(field_names) or "(no direct fields)"),
            }
            all_models.append(item)
            per_app[app].append(item)
    return all_models, per_app


def root_prefixes() -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    path = SRC / "config" / "urls.py"
    if not path.exists():
        return result
    try:
        tree = ast.parse(read(path))
    except SyntaxError:
        return result
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or name_of(node.func).rsplit(".", 1)[-1] != "path" or len(node.args) < 2:
            continue
        prefix = string_arg(node.args[0])
        target = node.args[1]
        if not prefix or not isinstance(target, ast.Call) or name_of(target.func).rsplit(".", 1)[-1] != "include" or not target.args:
            continue
        module = string_arg(target.args[0])
        if module:
            result[module].append(prefix)
    return result


def route_inventory() -> list[dict]:
    prefixes = root_prefixes()
    found = []
    for path in sorted(SRC.rglob("*.py")):
        if not (path.name == "urls.py" or path.name.endswith("_urls.py")):
            continue
        if "migrations" in path.parts or "wagtail_admin" in path.parts:
            continue
        try:
            tree = ast.parse(read(path), filename=rel(path))
        except SyntaxError:
            continue
        module = ".".join(path.relative_to(SRC).with_suffix("").parts)
        mounts = prefixes.get(module, [""])
        app = source_app(path)
        if app == "config":
            app = ""
        seen = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = name_of(node.func).rsplit(".", 1)[-1]
            if call_name not in {"path", "re_path"} or len(node.args) < 2:
                continue
            pattern = string_arg(node.args[0])
            view = node.args[1]
            if pattern is None:
                continue
            if isinstance(view, ast.Call) and name_of(view.func).rsplit(".", 1)[-1] == "include":
                continue
            handler = name_of(view.func.value) if isinstance(view, ast.Call) and name_of(view.func).rsplit(".", 1)[-1] == "as_view" else name_of(view)
            methods = []
            if isinstance(view, ast.Call) and name_of(view.func).rsplit(".", 1)[-1] == "as_view" and view.args and isinstance(view.args[0], ast.Dict):
                methods = [string_arg(k).upper() for k in view.args[0].keys if string_arg(k)]
            method_text = ",".join(methods) if methods else "view-defined"
            for mount in mounts:
                full = re.sub(r"/+", "/", mount.rstrip("/") + "/" + pattern.lstrip("/"))
                key = (full, handler, method_text)
                if key in seen:
                    continue
                seen.add(key)
                found.append({
                    "kind": "api", "title": f"{method_text} {full}",
                    "path": rel(path), "line": node.lineno, "app": app,
                    "source": True,
                    "summary": f"Route: {method_text} {full}\nHandler: {handler or 'unresolved'}\nSee the app API guide for request semantics, access rules and side effects.",
                })
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or name_of(node.func).rsplit(".", 1)[-1] != "register" or len(node.args) < 2:
                continue
            prefix = string_arg(node.args[0])
            viewset = name_of(node.args[1])
            if prefix is None or not viewset:
                continue
            for mount in mounts:
                full = re.sub(r"/+", "/", mount.rstrip("/") + "/" + prefix.strip("/"))
                for suffix, methods in (("/", "GET,POST"), ("/<lookup>/", "GET,PUT,PATCH,DELETE")):
                    found.append({
                        "kind": "api", "title": methods + " " + full + suffix,
                        "path": rel(path), "line": node.lineno, "app": app,
                        "source": True,
                        "summary": f"DRF router route for {viewset}. Collection/detail actions follow the ViewSet methods.",
                    })
    unique = {}
    for item in found:
        unique[(item["title"], item["path"], item["app"])] = item
    return list(unique.values())


def score(entry: dict, query: str) -> float:
    q = words(query)
    if not q:
        return 0.0
    title = words(entry["title"])
    path = words(entry["path"])
    summary = words(entry.get("search_text") or entry["summary"])
    score_value = 0.0
    for term in q:
        if term in title:
            score_value += 8
        elif term in path:
            score_value += 5
        elif term in summary:
            score_value += 1.5
        elif len(term) > 3 and any(term in value for value in title + path + summary):
            score_value += 0.5
    phrase = " ".join(q)
    if phrase and phrase in " ".join(title):
        score_value += 8
    if query.casefold() in entry["title"].casefold():
        score_value += 5
    return score_value


def search(query: str, kind: str, app: str | None, limit: int) -> list[dict]:
    docs = docs_index()
    models, _ = model_inventory()
    routes = route_inventory()
    all_entries = docs + models + routes
    results = []
    for item in all_entries:
        if kind != "all" and item["kind"] != kind:
            continue
        if app and item.get("app", "").casefold() != app.casefold():
            continue
        value = score(item, query)
        if value > 0:
            results.append({
                **{key: value for key, value in item.items() if key != "search_text"},
                "score": round(value, 2),
            })
    results.sort(key=lambda x: (-x["score"], not x["source"], x["path"], x["line"] or 0))
    return results[:max(1, limit)]


def audit() -> dict:
    models, per_app = model_inventory()
    missing_models = []
    model_coverage = {}
    for app, items in sorted(per_app.items()):
        doc_path = DOCS / "apps" / app / "models.md"
        doc = read(doc_path)
        # A model is covered by its own heading or by explicit explanatory
        # prose/table text in the owning models.md. Grouped model sections
        # are valid when they name the relevant class.
        headings = [
            match.group(1).strip().casefold()
            for match in re.finditer(r"^#{2,6}\s+(.+?)\s*$", doc, re.MULTILINE)
        ]
        body_lines = [
            line.casefold() for line in doc.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        missing = [
            item["title"] for item in items
            if not any(item["title"].casefold() in heading for heading in headings)
            and not any(item["title"].casefold() in line for line in body_lines)
        ]
        model_coverage[app] = {
            "source_models": len(items),
            "models_named_in_app_doc": len(items) - len(missing),
            "missing_models": missing,
            "documentation": rel(doc_path) if doc_path.exists() else None,
        }
        missing_models.extend({"app": app, "model": name, "documentation": rel(doc_path)} for name in missing)

    routes = route_inventory()
    route_apps = sorted({x["app"] for x in routes if x["app"]})
    missing_guides = []
    for app in route_apps:
        folder = DOCS / "apps" / app
        if not (folder / "api.md").exists() and not (folder / "api-reference.md").exists():
            missing_guides.append(app)
    return {
        "repository": "nima-salamat/django-paas-deployer",
        "models_discovered": len(models),
        "model_coverage": model_coverage,
        "models_missing_from_docs": missing_models,
        "static_routes_discovered": len(routes),
        "apps_with_routes": route_apps,
        "apps_without_api_guide": missing_guides,
        "notes": [
            "Static AST inventory; dynamically composed routes and router custom actions may need manual review.",
            "An API guide existing does not prove every payload, permission and side effect has been documented.",
            "Source code and tests remain authoritative; this index is for navigation, not authorization.",
        ],
        "ok": not missing_models and not missing_guides,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search project docs and source symbols for Agents.")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("search", help="Search documentation, model classes, API routes and systems.")
    cmd.add_argument("query")
    cmd.add_argument("--kind", choices=("all", "api", "model", "system"), default="all")
    cmd.add_argument("--app")
    cmd.add_argument("--limit", type=int, default=8)
    cmd.add_argument("--json", action="store_true", dest="as_json")
    audit_cmd = sub.add_parser("audit", help="Audit model descriptions and API guide presence.")
    audit_cmd.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    if args.command == "search":
        results = search(args.query, args.kind, args.app, args.limit)
        if args.as_json:
            print(json.dumps({"query": args.query, "kind": args.kind, "count": len(results), "results": results}, ensure_ascii=False, indent=2))
        else:
            for number, item in enumerate(results, 1):
                print(f"[{number}] {item['title']} ({item['kind']})")
                print(f"    {item['path']}:{item['line'] or '-'} | score={item['score']}")
                print("    " + item["summary"].replace("\n", "\n    ")[:900])
                print()
            if not results:
                print("No matching docs or source symbols found.")
        return 0 if results else 1

    report = audit()
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Models found: {report['models_discovered']}")
        print(f"Static URL/router entries found: {report['static_routes_discovered']}")
        print("Model documentation gaps:")
        for item in report["models_missing_from_docs"]:
            print(f"  - {item['app']}.{item['model']} ({item['documentation']})")
        if not report["models_missing_from_docs"]:
            print("  - none")
        print("Apps without API guides: " + (", ".join(report["apps_without_api_guide"]) or "none"))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
