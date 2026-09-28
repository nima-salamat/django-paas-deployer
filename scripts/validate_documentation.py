#!/usr/bin/env python3
"""Validate source/documentation coverage without importing Django."""
from __future__ import annotations
import ast
import re
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DOC = ROOT / "documentation"
APPS = ["users","auth_users","services","plans","deploy","deployments","logs","app_catalog","messenger","tickets","custom_emails","docs","core","cms"]
EXCLUDED_PARTS = {"migrations","tests","__pycache__"}
EXCLUDED_FILES = {"__init__.py"}

def python_files(app):
    base = SRC / app
    return sorted(p for p in base.rglob("*.py") if not any(x in EXCLUDED_PARTS for x in p.parts) and p.name not in EXCLUDED_FILES and not p.name.endswith(".bak"))

def parse(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

def class_bases(node):
    out=set()
    for base in node.bases:
        out.add(base.id if isinstance(base,ast.Name) else base.attr if isinstance(base,ast.Attribute) else "")
    return out

def docs_for(app):
    root=DOC/"apps"/app
    return "\n".join(p.read_text(encoding="utf-8") for p in root.rglob("*.md")) + "\n" + (DOC/"apps"/"COVERAGE.md").read_text(encoding="utf-8")

def main():
    errors=[]; docs={}
    old=DOC/"deployments"
    if old.exists(): errors.append("stale canonical tree exists: documentation/deployments/")
    for app in APPS:
        root=DOC/"apps"/app
        if not (root/"README.md").exists(): errors.append(f"missing canonical README: {app}")
        docs[app]=docs_for(app)
    for app in APPS:
        for path in python_files(app):
            rel=path.relative_to(ROOT).as_posix()
            if rel not in docs[app]: errors.append(f"production module not mapped: {rel}")
            tree=parse(path)
            for node in ast.walk(tree):
                if isinstance(node,ast.ClassDef):
                    bases=class_bases(node)
                    if {"Model","ModelBase"} & bases and not re.search(rf"\b{re.escape(node.name)}\b",docs[app]): errors.append(f"model undocumented: {app}.{node.name}")
                    if {"Serializer","ModelSerializer","SerializerBase"} & bases and not re.search(rf"\b{re.escape(node.name)}\b",docs[app]): errors.append(f"serializer undocumented: {app}.{node.name}")
                if isinstance(node,ast.Call):
                    fn=node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else ""
                    if fn=="JSONField":
                        for parent in ast.walk(tree):
                            if isinstance(parent,ast.Assign) and any(node in ast.walk(t) for t in parent.targets):
                                for target in parent.targets:
                                    if isinstance(target,ast.Name) and target.id not in docs[app]: errors.append(f"JSONField undocumented: {app}.{target.id}")
    for app in APPS:
        commands=SRC/app/"management"/"commands"
        if commands.exists():
            for path in commands.glob("*.py"):
                if path.name!="__init__.py" and path.stem not in docs[app]: errors.append(f"management command undocumented: {app}.{path.stem}")
    for path in DOC.rglob("*.md"):
        text=path.read_text(encoding="utf-8")
        if "\\\\|" in text: errors.append(f"escaped table-pipe artifact: {path.relative_to(ROOT)}")
        if "\\`" in text: errors.append(f"escaped backtick artifact: {path.relative_to(ROOT)}")
        if sum(1 for line in text.splitlines() if line.startswith("```")) % 2: errors.append(f"unclosed code fence: {path.relative_to(ROOT)}")
        for target in re.findall(r"\]\(([^)#]+)(?:#[^)]+)?\)",text):
            if target.startswith(("http://","https://","mailto:")): continue
            if not (path.parent/target).resolve().exists(): errors.append(f"broken internal link: {path.relative_to(ROOT)} -> {target}")
    if errors:
        print("documentation validation: FAILED"); print("\n".join("- "+e for e in errors)); return 1
    print("documentation validation: OK"); return 0
if __name__=="__main__": sys.exit(main())
