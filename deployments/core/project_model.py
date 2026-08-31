"""
deployments/core/project_model.py
---------------------------------
Structured project model for a submitted deployment archive.

The deployer must distinguish several paths that are NOT interchangeable:

  * the ARCHIVE ROOT — the complete user-submitted source tree, as the
    Docker build sees it (post-``flatten_single_toplevel``);
  * the APPLICATION root — where the backend application lives
    (``backend/``, ``services/api/laravel``, ``.`` …);
  * the FRONTEND root — where the frontend ``package.json`` lives;
  * the BUILD root — the directory build commands execute from;
  * the BUILD OUTPUT — where build artifacts land;
  * the RUNTIME root — the directory the container process executes from;
  * the DOCUMENT root — the directory Apache/nginx serves.

The key invariant of this module: **every path it emits is relative to the
post-flatten build context.**  The image build strips a single top-level
archive wrapper directory (GitHub zips, commit-hash folders) after
extraction, so detection strips the same prefix before emitting any path.
This is the same ``single_prefix`` logic ``_detect_php_document_root``
always applied; it is now shared by every consumer.

Pure stdlib — no Django or Docker imports — so it is unit-testable in
isolation and importable from both the plugin layer and the renderer
without import cycles.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Callable, Iterable

from deployments.common.exceptions import DeploymentValidationError

# Size cap when reading package.json / composer.json members.
_MAX_JSON_BYTES = 512_000

# System directory names the image build refuses to flatten away
# (image_manager.flatten_single_toplevel).
_REFUSED_TOPLEVEL = frozenset(
    {"bin", "etc", "usr", "var", "lib", "opt", "tmp", "dev", "proc"}
)

# Top-level entries flatten_single_toplevel ignores when deciding whether
# the archive has a single top-level directory to strip (the build writes
# its own Dockerfile / .dockerignore afterwards).
_FLATTEN_IGNORED = frozenset({"Dockerfile", ".dockerignore"})

_VITE_CONFIG_BASENAMES = (
    "vite.config.js", "vite.config.ts", "vite.config.mjs", "vite.config.cjs",
)

_LOCKFILE_BASENAMES = (
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock",
)

_BUILD_SCRIPT_CANDIDATES = ("build", "prod", "production", "build:prod", "build:ssr")

_SAFE_KIND_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._+-"
)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def normalize_member_name(name: str | None) -> str:
    """Normalize an archive member path to a clean posix relative path."""
    n = (name or "").replace("\\", "/").strip()
    while n.startswith("./"):
        n = n[2:]
    n = n.lstrip("/")
    return n.rstrip("/")


def parent_of(name: str) -> str:
    """Parent directory of a normalized file path ('' for top-level)."""
    parent = str(PurePosixPath(name).parent)
    return "" if parent == "." else parent


def strip_archive_prefix(rel: str, prefix: str) -> str:
    """Remove a single top-level archive directory from *rel*."""
    if not prefix or not rel:
        return rel
    if rel == prefix:
        return ""
    if rel.startswith(prefix + "/"):
        return rel[len(prefix) + 1:]
    return rel


def clean_rel_path(path: Any) -> str:
    """
    Normalize a user-supplied relative archive path; "" means archive root.

    Raises ``DeploymentValidationError`` for traversal, absolute paths or
    any value that cannot live inside the post-flatten build context.
    """
    p = (str(path) if path is not None else "").replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    p = p.rstrip("/")
    if p in ("", "."):
        return ""
    if (
        p.startswith("/")
        or p == ".."
        or p.startswith("../")
        or p.endswith("/..")
        or "/../" in f"/{p}/"
    ):
        raise DeploymentValidationError(
            f"Project root must be relative and inside the build context: {p!r}",
            stage="frontend_detection",
            details={"root": str(p)},
        )
    return p


def detect_archive_wrapper(names: Iterable[str]) -> str:
    """
    Return the name of the single top-level wrapper directory that the
    image build's ``flatten_single_toplevel`` will strip, or ``""``.

    Mirrors ``flatten_single_toplevel`` decision-for-decision:

      * exactly one top-level entry (``Dockerfile`` / ``.dockerignore``
        excluded — the build writes those itself),
      * that entry must be a directory with content under it,
      * its name must not be a refused system directory,
      * flattening must not collide with any other top-level entry
        (a collision makes the real flatten abort).
    """
    norm: list[str] = []
    for n in names:
        c = normalize_member_name(n)
        if c and c not in (".", ".."):
            norm.append(c)
    if not norm:
        return ""
    top_all = {n.split("/", 1)[0] for n in norm}
    candidates = [t for t in top_all if t not in _FLATTEN_IGNORED]
    if len(candidates) != 1:
        return ""
    only = candidates[0]
    inner = [n[len(only) + 1:] for n in norm if n.startswith(only + "/")]
    if not any(inner):
        return ""
    if only in _REFUSED_TOPLEVEL:
        return ""
    inner_tops = {n.split("/", 1)[0] for n in inner if n}
    outer_tops = {t for t in top_all if t != only}
    if inner_tops & outer_tops:
        return ""
    return only


# ---------------------------------------------------------------------------
# File views — one interface over the tar stream and the extracted tree
# ---------------------------------------------------------------------------


class FileView:
    """Uniform read interface over a tar stream or an extracted tree."""

    def names(self) -> list[str]:
        """All normalized member names (files and directories)."""
        raise NotImplementedError

    def read(self, name: str) -> "bytes | None":
        raise NotImplementedError


class TarFileView(FileView):
    """Read access over an in-memory tar stream.

    Archive members are indexed by their normalised original path.  In
    addition, when the archive has a single top-level wrapper directory
    (the common GitHub-zip / commit-hash layout), every file is *also*
    indexed under its post-flatten path so that callers which have already
    stripped the wrapper (``build_project_model``, frontend detection,
    etc.) can still read content.  Without the dual mapping,
    ``view.read("package.json")`` silently returned ``None`` for any
    wrapped archive and Laravel + Vite auto-injection was skipped.
    """

    def __init__(self, tar_stream):
        import tarfile as _tf

        self._names: list[str] = []
        self._members: dict[str, Any] = {}
        # lookup key → original member name that tarfile.extractfile expects
        self._extract_name: dict[str, str] = {}
        self._payload: dict[str, bytes] = {}
        self._stream = tar_stream
        self._tf = _tf

        tar_stream.seek(0)
        with _tf.open(fileobj=tar_stream, mode="r:*") as tar:
            for m in tar.getmembers():
                n = normalize_member_name(m.name)
                if not n or n in (".", "..") or "/../" in f"/{n}/":
                    continue
                self._names.append(n)
                if m.isfile():
                    self._members[n] = m
                    self._extract_name[n] = m.name
        try:
            tar_stream.seek(0)
        except Exception:
            pass

        # Dual-index under post-flatten paths when a single wrapper exists.
        wrapper = detect_archive_wrapper(self._names)
        if wrapper:
            for original in list(self._members.keys()):
                stripped = strip_archive_prefix(original, wrapper)
                if stripped and stripped not in self._members:
                    self._members[stripped] = self._members[original]
                    self._extract_name[stripped] = self._extract_name[original]

    def names(self) -> list[str]:
        return list(self._names)

    def read(self, name: str) -> "bytes | None":
        if name in self._payload:
            return self._payload[name]
        if name not in self._members:
            return None
        data = b""
        extract_as = self._extract_name.get(name, name)
        try:
            self._stream.seek(0)
            with self._tf.open(fileobj=self._stream, mode="r:*") as tar:
                f = tar.extractfile(extract_as)
                if f is not None:
                    data = f.read(_MAX_JSON_BYTES)
        except Exception:
            data = b""
        self._payload[name] = data
        return data

class TreeFileView(FileView):
    """Read access over an extracted project tree via ``file_index``."""

    def __init__(self, file_index: "dict[str, str]"):
        # file_index: normalized relative path -> absolute path
        self._index: dict[str, str] = {}
        for k, v in (file_index or {}).items():
            nk = normalize_member_name(k)
            if nk and nk not in (".", ".."):
                self._index[nk] = v

    def names(self) -> list[str]:
        return sorted(self._index.keys())

    def read(self, name: str) -> "bytes | None":
        abs_path = self._index.get(name)
        if not abs_path:
            return None
        try:
            with open(abs_path, "rb") as f:
                return f.read(_MAX_JSON_BYTES)
        except OSError:
            return None


def _safe_read(view: FileView, name: str) -> "bytes | None":
    try:
        return view.read(name)
    except Exception:
        return b""


def _read_json_bytes(data: "bytes | None") -> dict:
    try:
        pkg = json.loads((data or b"").decode("utf-8", "ignore"))
    except Exception:
        return {}
    return pkg if isinstance(pkg, dict) else {}


def _read_json_view(view: FileView, name: str) -> dict:
    return _read_json_bytes(_safe_read(view, name))


# ---------------------------------------------------------------------------
# Detection core
# ---------------------------------------------------------------------------


def _read_json_bytes(data: "bytes | None") -> dict:
    try:
        pkg = json.loads((data or b"").decode("utf-8", "ignore"))
    except Exception:
        return {}
    return pkg if isinstance(pkg, dict) else {}


def detect_laravel_roots(
    names: "list[str]", read_file: "Callable[[str], bytes | None]"
) -> "list[str]":
    """
    Return candidate Laravel application roots (post-flatten), shallowest
    first.  A root is a directory whose composer.json requires
    ``laravel/framework``; an ``artisan`` script in the same directory is
    the second marker, and a directory with both markers always wins over
    one with only artisan.
    """
    composer_laravel_dirs: "list[str]" = []
    artisan_dirs: "set[str]" = set()
    for n in names:
        base = n.rsplit("/", 1)[-1].lower()
        if base == "artisan":
            artisan_dirs.add(parent_of(n))
        elif base == "composer.json":
            pkg = _read_json_bytes(read_file(n))
            req = pkg.get("require")
            if isinstance(req, dict) and "laravel/framework" in req:
                composer_laravel_dirs.append(parent_of(n))

    if composer_laravel_dirs:
        roots = [d for d in composer_laravel_dirs if d in artisan_dirs]
        if not roots:
            # No artisan anywhere — composer evidence alone is enough.
            roots = list(composer_laravel_dirs)
    else:
        # Fallback to any artisan-containing directory.
        roots = sorted(artisan_dirs)
    return sorted(set(roots), key=lambda d: (d.count("/"), d))


def frontend_candidates(
    names: "list[str]",
    read_file: "Callable[[str], bytes | None]",
    laravel_root: str,
) -> "list[dict]":
    """
    Score every ``package.json`` in the (post-flatten) archive as a
    frontend candidate.  Markers (vite.config.*, lockfiles) are associated
    by shared parent directory, never archive-wide.
    """
    name_set = set(names)
    candidates: "list[dict]" = []
    for n in names:
        if n.rsplit("/", 1)[-1].lower() != "package.json":
            continue
        pkg_dir = parent_of(n)
        pkg = _read_json_bytes(_safe_read_file(read_file, n))

        deps: "dict[str, str]" = {}
        for key in ("dependencies", "devDependencies"):
            val = pkg.get(key)
            if isinstance(val, dict):
                deps.update(val)
        scripts = pkg.get("scripts")
        if not isinstance(scripts, dict):
            scripts = {}

        local_files = {
            x.rsplit("/", 1)[-1]
            for x in name_set
            if parent_of(x) == pkg_dir
        }

        vite_local = any(b in local_files for b in _VITE_CONFIG_BASENAMES)
        mix_local = "webpack.mix.js" in local_files
        has_react = any(
            k in deps
            for k in ("react", "react-dom", "react-scripts", "@inertiajs/react")
        )
        has_vue = any(k in deps for k in ("vue", "@inertiajs/vue3"))
        is_vite = vite_local or any(
            k in deps
            for k in (
                "vite", "laravel-vite-plugin",
                "@vitejs/plugin-react", "@vitejs/plugin-vue",
            )
        )

        if is_vite:
            kind = "vite"
        elif "react-scripts" in deps:
            kind = "react"
        elif "laravel-mix" in deps or mix_local:
            kind = "mix"
        elif "next" in deps:
            kind = "nextjs"
        elif "nuxt" in deps or "nuxt3" in deps:
            kind = "nuxt"
        elif has_react or has_vue:
            kind = "node"
        elif "build" in scripts:
            kind = "node"
        else:
            kind = ""

        build_script = next(
            (c for c in _BUILD_SCRIPT_CANDIDATES if c in scripts),
            "build",
        )

        lockfile = next((x for x in _LOCKFILE_BASENAMES if x in local_files), None)

        # Score: prefer Laravel's own package.json for Inertia/Vite, but let
        # a sibling frontend win when it carries stronger frontend evidence.
        score = 0
        if pkg_dir == laravel_root:
            score += 30
        if is_vite:
            score += 50
        if "laravel-vite-plugin" in deps:
            score += 25
        if "@inertiajs/react" in deps or "@inertiajs/vue3" in deps:
            score += 20
        if has_react or has_vue:
            score += 10
        if "build" in scripts:
            score += 10
        if lockfile is not None:
            score += 5

        candidates.append({
            "path": n,
            "root": pkg_dir,
            "pkg": pkg,
            "deps": deps,
            "scripts": scripts,
            "kind": kind,
            "build_script": build_script,
            "score": score,
            "local_files": local_files,
            "lockfile": lockfile,
            "package_manager": package_manager_for(pkg, local_files),
            "has_package_lock": "package-lock.json" in local_files,
        })
    return candidates


def _safe_read_file(read_file, name):
    try:
        return read_file(name)
    except Exception:
        return b""


def package_manager_for(pkg: dict, local_files: "set[str]") -> str:
    """Resolve the package manager from the *same directory* as package.json."""
    if "pnpm-lock.yaml" in local_files:
        return "pnpm"
    if "yarn.lock" in local_files:
        return "yarn"
    if "bun.lockb" in local_files or "bun.lock" in local_files:
        return "bun"
    pm_field = str(pkg.get("packageManager") or "").split("@", 1)[0].strip().lower()
    if pm_field in {"npm", "pnpm", "yarn", "bun"}:
        return pm_field
    return "npm"


def select_frontend(candidates: "list[dict]") -> "dict | None":
    """
    Pick the best frontend candidate.  Candidates without a recognized
    frontend kind are excluded — a package.json carrying only composer
    hook scripts is not a frontend and must never win.

    Deterministic tiebreaker: highest score, then shallowest root, then
    lexicographic package.json path.
    """
    usable = [c for c in candidates if c["kind"]]
    if not usable:
        return None
    return max(
        usable,
        key=lambda c: (c["score"], -c["root"].count("/"), c["path"]),
    )


def detect_build_output(
    kind: str,
    deps: "dict[str, str]",
    frontend_root: str,
    laravel_root: str,
) -> "str | None":
    """Where the frontend build writes its artifacts (archive-relative)."""
    if kind == "vite" and "laravel-vite-plugin" in deps:
        base = laravel_root if laravel_root and laravel_root != "." else ""
        return f"{base}/public/build" if base else "public/build"
    if kind == "mix":
        base = laravel_root if laravel_root and laravel_root != "." else ""
        return f"{base}/public" if base else "public"
    if kind == "react":
        base = frontend_root if frontend_root and frontend_root != "." else ""
        return f"{base}/build" if base else "build"
    base = frontend_root if frontend_root and frontend_root != "." else ""
    return f"{base}/dist" if base else "dist"


# ---------------------------------------------------------------------------
# Structured model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectRoot:
    """A single detected project inside the archive (post-flatten paths)."""

    kind: str
    root: str                      # archive-relative, post-flatten; "" = root
    confidence: float = 0.0
    evidence: "dict[str, Any]" = field(default_factory=dict)
    package_manager: "str | None" = None
    build_script: "str | None" = None
    build_output: "str | None" = None
    install_command: "str | None" = None
    build_command: "str | None" = None


@dataclass(frozen=True)
class ProjectModel:
    """Structured description of a submitted archive (post-flatten paths)."""

    archive_root: str = "."
    applications: "list[ProjectRoot]" = field(default_factory=list)
    frontends: "list[ProjectRoot]" = field(default_factory=list)
    # Name of the wrapper directory the image build flattens away, if any.
    flattened_wrapper: "str | None" = None

    @property
    def application_root(self) -> str:
        return (self.applications[0].root if self.applications else "") or "."

    @property
    def frontend_root(self) -> "str | None":
        if self.frontends:
            return self.frontends[0].root or "."
        return None

    def to_dict(self) -> "dict[str, Any]":
        return {
            "archive_root": self.archive_root,
            "flattened_wrapper": self.flattened_wrapper,
            "applications": [_root_dict(a) for a in self.applications],
            "frontends": [_root_dict(f) for f in self.frontends],
        }

    def frontend_info(self) -> "dict[str, Any] | None":
        """
        Legacy detection-record shape (the dict ``_detect_laravel_frontend``
        used to return) so the renderer and existing log lines keep their
        contract.  ``None`` when no frontend was detected.
        """
        if not self.frontends:
            return None
        f = self.frontends[0]
        return {
            "kind": f.kind,
            "has_package_json": bool(f.evidence.get("package_json_path")),
            "build_script": f.build_script or "build",
            "package_manager": f.package_manager or "npm",
            "detected_files": list(f.evidence.get("detected_files") or []),
            "package_json_path": f.evidence.get("package_json_path"),
            "frontend_root": f.root or ".",
            "laravel_root": (self.applications[0].root or ".") if self.applications else ".",
            "has_package_lock": bool(f.evidence.get("has_package_lock")),
            "build_output": f.build_output,
        }


def _root_dict(p: ProjectRoot) -> "dict[str, Any]":
    return {
        "kind": p.kind,
        "root": p.root or ".",
        "confidence": p.confidence,
        "package_manager": p.package_manager,
        "build_script": p.build_script,
        "build_output": p.build_output,
        "evidence": dict(p.evidence),
    }


# ---------------------------------------------------------------------------
# Model builder
# ---------------------------------------------------------------------------


def _validate_user_kind(kind: str) -> str:
    """User-supplied kind must be a safe identifier (no shell metachars)."""
    k = (kind or "").strip().lower()
    if not k:
        return ""
    if any(ch not in _SAFE_KIND_CHARS for ch in k):
        raise DeploymentValidationError(
            f"Invalid frontend kind: {k!r}",
            stage="frontend_detection",
            details={"kind": k},
        )
    return k


def _frontend_options(config: Any) -> "dict[str, Any]":
    frontend = getattr(config, "frontend", None)
    return dict(frontend) if isinstance(frontend, dict) else {}


def _user_overrides(config: Any) -> "dict[str, Any]":
    """Collect explicit user overrides for the frontend detection."""
    env = getattr(config, "environment", None)
    env = env if isinstance(env, dict) else {}
    frontend = _frontend_options(config)

    kind = ""
    kind_source = "auto"
    env_kind = str(
        env.get("FRONT_BUILD_PLATFORM") or env.get("FRONTEND_BUILD") or ""
    ).strip()
    if env_kind:
        kind = env_kind
        kind_source = "env"
    if not kind:
        kind = str(
            frontend.get("platform")
            or frontend.get("kind")
            or getattr(config, "front_build_platform", None)
            or ""
        ).strip()
        if kind:
            kind_source = "user_override"
    kind = _validate_user_kind(kind)

    root_raw = frontend.get("root") or frontend.get("frontend_root")
    root = clean_rel_path(root_raw) if root_raw else ""

    pm = str(
        frontend.get("package_manager")
        or getattr(config, "package_manager", None)
        or ""
    ).strip().lower()

    return {
        "kind": kind,
        "kind_source": kind_source,
        "root": root,
        "package_manager": pm if pm in {"npm", "pnpm", "yarn", "bun"} else "",
        "build_command": frontend.get("build_command") or frontend.get("command"),
        "install_command": frontend.get("install_command"),
    }


def _archive_markers(names: "list[str]") -> "list[str]":
    """Basenames of node/composer marker files present anywhere in the archive."""
    markers = {
        n.rsplit("/", 1)[-1]
        for n in names
        if n.rsplit("/", 1)[-1].lower() in _DETECTED_FILE_BASENAMES
    }
    return sorted(markers)


_MARKER_BASENAMES = (
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "bun.lockb", "bun.lock", "vite.config.js", "vite.config.ts",
    "vite.config.mjs", "webpack.mix.js", "composer.json", "artisan",
)

_DETECTED_FILE_BASENAMES = frozenset(_MARKER_BASENAMES)


_DETECTED_FILE_BASENAMES = frozenset(_MARKER_BASENAMES)


def build_project_model(
    view: FileView,
    *,
    config: Any = None,
    wrapper: "str | None" = None,
) -> ProjectModel:
    """
    Detect the archive structure and return a ``ProjectModel`` whose paths
    are all relative to the post-flatten build context.

    ``wrapper`` forces the flattened-wrapper name (used when the caller
    already stepped into the wrapper, e.g. the filesystem inspector path).
    When ``None`` it is computed from the archive member names using the
    same rules as ``image_manager.flatten_single_toplevel``.
    """
    raw_names = [n for n in view.names() if n]
    wrapper = wrapper or detect_archive_wrapper(raw_names)
    names = [n for n in (strip_archive_prefix(x, wrapper) for x in raw_names) if n]

    read_file = view.read
    laravel_roots = detect_laravel_roots(names, read_file)
    laravel_root = laravel_roots[0] if laravel_roots else ""

    applications: "list[ProjectRoot]" = []
    if laravel_roots:
        applications.append(
            ProjectRoot(
                kind="laravel",
                root=laravel_root or ".",
                confidence=0.9,
                evidence={
                    "markers": sorted(
                        n for n in names
                        if n.rsplit("/", 1)[-1].lower() in ("composer.json", "artisan")
                        and parent_of(n) == laravel_root
                    ),
                },
            )
        )

    candidates = frontend_candidates(names, read_file, laravel_root)
    overrides = _user_overrides(config)
    user_root = str(overrides.get("root") or "").strip()
    user_kind = str(overrides.get("kind") or "").strip().lower()
    user_pm = str(overrides.get("package_manager") or "").strip().lower()

    if user_root:
        # Explicit user root wins over scoring: use the candidate living at
        # that root (when any), otherwise synthesize one from the override.
        chosen = next(
            (c for c in candidates if c["root"] == user_root), None
        )
    else:
        chosen = select_frontend(candidates)

    frontends: "list[ProjectRoot]" = []
    if chosen is not None:
        f_root = chosen["root"] or "."
        f_kind = user_kind or chosen["kind"]
        f_pm = user_pm or chosen["package_manager"]
        frontends.append(
            ProjectRoot(
                kind=f_kind,
                root=f_root,
                confidence=min(1.0, 0.5 + chosen["score"] / 200.0),
                evidence={
                    "package_json_path": chosen["path"],
                    "deps": sorted(chosen["deps"].keys()),
                    "scripts": sorted(chosen["scripts"].keys()),
                    "lockfile": chosen.get("lockfile"),
                    "has_package_lock": bool(chosen.get("has_package_lock")),
                    "detected_files": _archive_markers(names),
                    "config_files": sorted(
                        f for f in chosen["local_files"]
                        if f in _VITE_CONFIG_BASENAMES or f == "webpack.mix.js"
                    ),
                    "package_manager": f_pm,
                    "build_script": chosen["build_script"],
                    "score": chosen["score"],
                    "kind_source": overrides.get("kind_source") or "auto",
                },
                package_manager=f_pm,
                build_script=chosen["build_script"],
                build_output=detect_build_output(
                    f_kind, chosen["deps"], f_root, laravel_root
                ),
            )
        )
    elif user_kind or user_root:
        # User forced a frontend even though auto-detection found none.
        frontends.append(
            ProjectRoot(
                kind=user_kind or "node",
                root=user_root or ".",
                confidence=0.5,
                evidence={"source": "user_override"},
                package_manager=user_pm or None,
            )
        )

    return ProjectModel(
        archive_root=".",
        applications=applications,
        frontends=frontends,
        flattened_wrapper=wrapper or None,
    )


def build_project_model_from_tar(tar_stream, *, config=None) -> ProjectModel:
    """Build a ProjectModel from an in-memory tar stream (post-flatten)."""
    return build_project_model(TarFileView(tar_stream), config=config)


def build_project_model_from_tree(
    file_index: "dict[str, str]",
    *,
    config=None,
    wrapper: "str | None" = None,
) -> ProjectModel:
    """
    Build the model from an extracted project tree.  The tree root is
    already inside the wrapper (``extract_zip_to_temp`` steps into it), so
    ``wrapper`` records the stripped directory for observability while all
    emitted paths stay tree-relative (== post-flatten).
    """
    return build_project_model(
        TreeFileView(file_index), config=config, wrapper=wrapper
    )


def frontend_info_from_model(model: "ProjectModel | None") -> "dict[str, Any] | None":
    """Legacy ``_detect_laravel_frontend``-shaped record, or None."""
    if model is None:
        return None
    return model.frontend_info()
