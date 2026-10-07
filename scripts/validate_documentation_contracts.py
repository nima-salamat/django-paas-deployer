#!/usr/bin/env python3
from pathlib import Path
import ast
import sys

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"src"
INV=ROOT/"documentation/reference/contracts.md"
APPS=["agent","users","auth_users","services","plans","deploy","deployments","logs","app_catalog","messenger","tickets","custom_emails","docs","core","cms"]
BASES={"Model","BaseModel","BaseGenericSetting","AbstractBaseUser","PermissionsMixin","Page","ClusterableModel","Orderable"}
FIELDS={"ForeignKey","OneToOneField","ManyToManyField","ArrayField","ParentalKey","GenericRelation"}

def n(x):
    return x.id if isinstance(x,ast.Name) else x.attr if isinstance(x,ast.Attribute) else ""

def tree(p):
    return ast.parse(p.read_text(encoding="utf-8"),filename=str(p))

def rel(p):
    return p.relative_to(ROOT).as_posix()

def source_models():
    models=set(); fields=set()
    for app in APPS:
        base=SRC/app
        if not base.exists(): continue
        for p in base.rglob("models.py"):
            if any(x in {"tests","migrations","__pycache__"} for x in p.parts): continue
            for c in tree(p).body:
                if not isinstance(c,ast.ClassDef) or not any(n(b) in BASES for b in c.bases): continue
                models.add((app,rel(p),c.name))
                for x in c.body:
                    v=getattr(x,"value",None)
                    if not isinstance(v,ast.Call): continue
                    ft=n(v.func)
                    if ft not in FIELDS and not ft.endswith("Field") and not ft.endswith("Relation"): continue
                    ts=x.targets if isinstance(x,ast.Assign) else [x.target] if isinstance(x,ast.AnnAssign) else []
                    for t in ts:
                        if isinstance(t,ast.Name): fields.add((app,rel(p),c.name,t.id))
    return models,fields

def source_api():
    out=set()
    for app in APPS:
        base=SRC/app
        if not base.exists(): continue
        for p in base.rglob("*urls.py"):
            if p.name=="html_urls.py" or any(x in {"tests","migrations","__pycache__"} for x in p.parts): continue
            for x in ast.walk(tree(p)):
                if isinstance(x,ast.Call) and n(x.func) in {"path","re_path"} and x.args and isinstance(x.args[0],ast.Constant):
                    out.add((app,rel(p),"explicit",x.args[0].value or "<root>"))
    p=SRC/"config/urls.py"
    if p.exists():
        for x in ast.walk(tree(p)):
            if not isinstance(x,ast.Call) or n(x.func) not in {"path","re_path"} or not x.args or not isinstance(x.args[0],ast.Constant): continue
            r=x.args[0].value
            if isinstance(r,str) and r.startswith(("api/","media/")):
                if len(x.args)>1 and isinstance(x.args[1],ast.Call) and n(x.args[1].func)=="include": continue
                out.add(("config",rel(p),"explicit",r or "<root>"))
    return out

def source_router():
    out=set()
    for app in APPS:
        base=SRC/app
        if not base.exists(): continue
        for p in base.rglob("*.py"):
            if any(x in {"tests","migrations","__pycache__"} for x in p.parts): continue
            for x in ast.walk(tree(p)):
                if not isinstance(x,ast.Call) or not isinstance(x.func,ast.Attribute) or x.func.attr!="register" or "router" not in n(x.func.value) or len(x.args)<2: continue
                pre=x.args[0].value if isinstance(x.args[0],ast.Constant) else None
                vs=n(x.args[1])
                if isinstance(pre,str) and vs: out.add((app,rel(p),"router",pre,vs))
    return out

def sec(s,a,b):
    i=s.find(a)
    if i<0: return ""
    j=s.find(b,i+len(a))
    return s[i:j if j>=0 else len(s)]

def rows(s):
    out=[]
    for line in s.splitlines():
        z=line.strip()
        if not z.startswith("|") or z.startswith("|---"): continue
        out.append([p.strip().strip(chr(96)) for p in z.strip("|").split("|")])
    return out

def inventory():
    s=INV.read_text(encoding="utf-8")
    api={(r[0],r[1],r[2],r[3]) for r in rows(sec(s,"## API route inventory","## Router actions")) if len(r)>=5 and r[0]!="App"}
    routers={(r[0],r[1],"router",r[3],r[2]) for r in rows(sec(s,"## Router actions","## Model inventory")) if len(r)>=8 and r[0]!="App"}
    models={(r[0],r[1],r[2]) for r in rows(sec(s,"## Model inventory","## Model field inventory")) if len(r)>=5 and r[0]!="App"}
    fields={(r[0],r[1],r[2],r[3]) for r in rows(sec(s,"## Model field inventory","## Inheritance")) if len(r)>=6 and r[0]!="App"}
    return api,routers,models,fields

def main():
    if not INV.exists():
        print("missing contracts.md")
        return 1
    da,dr,dm,df=inventory()
    sa=source_api(); sr=source_router(); sm,sf=source_models()
    errors=[]
    for label,src,doc in [("API",sa,da),("router",sr,dr),("model",sm,dm),("field",sf,df)]:
        errors += [f"{label} missing: {x}" for x in sorted(src-doc)]
        errors += [f"{label} stale: {x}" for x in sorted(doc-src)]
    if errors:
        print("documentation contract validation: FAILED")
        print("\n".join("- "+x for x in errors))
        return 1
    print(f"documentation contract validation: OK apis={len(sa)} routers={len(sr)} models={len(sm)} fields={len(sf)}")
    return 0

if __name__=="__main__":
    sys.exit(main())
