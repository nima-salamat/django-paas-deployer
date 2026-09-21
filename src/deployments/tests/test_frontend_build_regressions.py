import io
import tarfile
import types
import sys


def make_tar(files):
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w") as tar:
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    bio.seek(0)
    return bio


def load_dockerfile_module():
    mod = types.ModuleType("core.global_settings.config")
    mod.MIRROR_DOCKER = "mirror.test"
    sys.modules["core.global_settings.config"] = mod
    pkg = types.ModuleType("core.global_settings")
    pkg.__path__ = []
    sys.modules["core.global_settings"] = pkg
    from deployments.core import dockerfile
    return dockerfile


def test_react_template_tokens_are_resolved():
    d = load_dockerfile_module()
    template = '''FROM mirror.test/node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
__DEPLOY_INSTALL_COMMAND__
COPY . .
__DEPLOY_BUILD_COMMAND__
FROM mirror.test/nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
'''
    class Config:
        entry_point = None
        environment = {}
        package_manager = "npm"
        install_command = "npm ci"
        build_command = "npm run build"
        build_dir = "dist"
        port = 80
    out = d._render_node_family("react", template, make_tar({
        "package.json": '{"scripts":{"build":"vite build"},"dependencies":{"react":"19"},"devDependencies":{"vite":"7"}}',
        "package-lock.json": "{}",
    }), Config(), None)
    assert "__DEPLOY_" not in out
    assert "RUN npm ci" in out
    assert "RUN npm run build" in out


def test_laravel_frontend_detection_works_with_bytesio_tar():
    d = load_dockerfile_module()
    detected = d._detect_laravel_frontend(make_tar({
        "composer.json": '{"require":{"laravel/framework":"^12.0"}}',
        "artisan": "<?php",
        "package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7","react":"19"}}',
        "package-lock.json": "{}",
    }))
    assert detected["has_package_json"] is True
    assert detected["kind"] == "vite"
    assert detected["package_manager"] == "npm"


def test_laravel_frontend_does_not_reuse_composer_install_command():
    d = load_dockerfile_module()
    class Config:
        environment = {}
        frontend = {}
        package_manager = "npm"
        install_command = "composer install --no-dev --optimize-autoloader"
        build_command = "npm run build"
        runtime_version = None
        build_options = {}
    out = d._inject_laravel_frontend_build(
        "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
        tar_stream=make_tar({
            "composer.json": '{"require":{"laravel/framework":"^12.0"}}',
            "artisan": "<?php",
            "package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7","react":"19"}}',
            "package-lock.json": "{}",
        }),
        config=Config(), logger=None,
    )
    frontend_block = out.split("# --- Laravel frontend build (injected) ---", 1)[1]
    assert "npm ci" in frontend_block
    assert "npm run build" in frontend_block
    assert "composer install --no-dev" not in frontend_block


def test_laravel_frontend_detects_pnpm():
    d = load_dockerfile_module()
    detected = d._detect_laravel_frontend(make_tar({
        "package.json": '{"packageManager":"pnpm@10.0.0","scripts":{"build":"vite build"},"devDependencies":{"vite":"7"}}',
        "pnpm-lock.yaml": "lockfileVersion: '9'\n",
    }))
    assert detected["has_package_json"] is True
    assert detected["package_manager"] == "pnpm"


def test_laravel_frontend_detects_nested_sibling_and_preserves_project_roots():
    d = load_dockerfile_module()
    tar = make_tar({
        "workspace/backend/artisan": "<?php",
        "workspace/backend/composer.json": '{"require":{"laravel/framework":"^12.0"}}',
        "workspace/frontend/package.json": '{"scripts":{"build":"vite build"},"dependencies":{"react":"19"},"devDependencies":{"vite":"7"}}',
        "workspace/frontend/package-lock.json": "{}",
        "workspace/frontend/vite.config.js": "export default { build: { outDir: 'dist' } }",
    })
    detected = d._detect_laravel_frontend(tar)
    # The build context is POST-FLATTEN (flatten_single_toplevel strips the
    # single top-level 'workspace' wrapper), so every emitted root must be
    # relative to the wrapper-stripped context — 'workspace/backend' would
    # not exist at docker build time.
    assert detected["laravel_root"] == "backend"
    assert detected["frontend_root"] == "frontend"
    assert detected["package_json_path"] == "frontend/package.json"
    assert detected["kind"] == "vite"


def test_laravel_frontend_npm_lockfile_uses_resilient_ci_fallback():
    d = load_dockerfile_module()
    class Config:
        environment = {}
        frontend = {}
        package_manager = "npm"
        install_command = None
        build_command = None
        runtime_version = "20"
    out = d._inject_laravel_frontend_build(
        "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
        tar_stream=make_tar({
            "composer.json": '{"require":{"laravel/framework":"^12.0"}}',
            "artisan": "<?php",
            "package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7","@emnapi/core":"1.11.3"}}',
            # Deliberately stale/out-of-sync lock metadata. The generated
            # command must retain npm ci first but recover with npm install.
            "package-lock.json": '{"lockfileVersion":3,"packages":{}}',
            "vite.config.js": "export default { plugins: [] }",
        }),
        config=Config(), logger=None,
    )
    assert "npm ci || npm install" in out
    assert "npm ci\n" not in out


def test_laravel_frontend_build_runs_from_selected_frontend_root():
    d = load_dockerfile_module()
    class Config:
        environment = {}
        frontend = {}
        package_manager = "npm"
        install_command = None
        build_command = None
        runtime_version = "20"
    out = d._inject_laravel_frontend_build(
        "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
        tar_stream=make_tar({
            "workspace/backend/artisan": "<?php",
            "workspace/backend/composer.json": '{"require":{"laravel/framework":"^12.0"}}',
            "workspace/frontend/package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7"}}',
            "workspace/frontend/package-lock.json": "{}",
            "workspace/frontend/vite.config.js": "export default { build: { outDir: 'dist' } }",
        }),
        config=Config(), logger=None,
    )
    assert "cd /var/www/html/frontend" in out
    assert "&& npm ci" in out
    assert "&& npm run build" in out


# ---------------------------------------------------------------------------
# Wrapper-directory (flatten) regression tests.
#
# The Docker build context is produced by ``safe_extract`` +
# ``flatten_single_toplevel`` which strips a single top-level archive
# directory (GitHub zips).  Every path the detector emits (frontend_root,
# laravel_root, package_json_path) must therefore be relative to the
# POST-FLATTEN build context — a "MyProject/frontend" path is unbuildable
# because flatten removes the "MyProject/" wrapper before docker build runs.
# ---------------------------------------------------------------------------

def _post_flatten_context(tar_stream):
    """Simulate Image.create's build context: safe_extract + flatten.

    Returns (sorted member names of the post-flatten context, stripped wrapper).
    """
    import os
    import tempfile

    from deployments.core.manager.image_manager import (
        flatten_single_toplevel,
        safe_extract,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tar_stream.seek(0)
        with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
            safe_extract(tar, tmpdir, max_bytes=500 * 1024 * 1024)
        stripped = flatten_single_toplevel(tmpdir)
        names = []
        for root, _dirs, files in os.walk(tmpdir):
            for f in files:
                names.append(
                    os.path.relpath(os.path.join(root, f), tmpdir).replace("\\", "/")
                )
        return sorted(names), stripped


def make_wrapped_sibling_tar():
    """GitHub-style zip: single 'MyProject' wrapper holding backend + frontend."""
    return make_tar({
        "MyProject/backend/artisan": "<?php",
        "MyProject/backend/composer.json": '{"require":{"laravel/framework":"^12.0"}}',
        "MyProject/backend/public/index.php": "<?php",
        "MyProject/frontend/package.json": (
            '{"scripts":{"build":"vite build"},'
            '"dependencies":{"laravel-vite-plugin":"1.0","vite":"7"}}'
        ),
        "MyProject/frontend/package-lock.json": "{}",
        "MyProject/frontend/vite.config.js": "export default { plugins: [] }",
    })


def test_frontend_root_resolves_in_post_flatten_build_context():
    """THE central regression: detection on the unflattened tar must still
    emit paths that exist inside the post-flatten build context."""
    d = load_dockerfile_module()
    detected = d._detect_laravel_frontend(make_wrapped_sibling_tar())
    assert detected["has_package_json"] is True
    assert detected["frontend_root"] == "frontend"
    assert detected["package_json_path"] == "frontend/package.json"

    # Cross-check: the detected root must exist in the actual build context
    # produced by safe_extract + flatten_single_toplevel.
    names, stripped = _post_flatten_context(make_wrapped_sibling_tar())
    assert stripped == "MyProject"
    assert f"{detected['frontend_root']}/package.json" in names


def test_laravel_frontend_dockerfile_uses_post_flatten_path():
    d = load_dockerfile_module()
    class Config:
        environment = {}
        frontend = {}
        package_manager = "npm"
        install_command = None
        build_command = None
        runtime_version = "20"
    out = d._inject_laravel_frontend_build(
        "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
        tar_stream=make_wrapped_sibling_tar(),
        config=Config(), logger=None,
    )
    assert "cd /var/www/html/frontend" in out
    assert "cd /var/www/html/MyProject/frontend" not in out


def test_laravel_frontend_dockerfile_no_wrapper_prefix():
    d = load_dockerfile_module()
    class Config:
        environment = {}
        frontend = {}
        package_manager = "npm"
        install_command = None
        build_command = None
        runtime_version = "20"
    out = d._inject_laravel_frontend_build(
        "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
        tar_stream=make_wrapped_sibling_tar(),
        config=Config(), logger=None,
    )
    import re as _re
    cd_paths = _re.findall(r"cd (\S+)", out)
    assert cd_paths, "expected at least one cd path in the Dockerfile"
    for p in cd_paths:
        assert "MyProject" not in p, f"wrapper prefix leaked into cd path: {p}"


# ---------------------------------------------------------------------------
# Step 6 regression set — ProjectModel + post-flatten invariants
# ---------------------------------------------------------------------------

import os  # noqa: E402
import re  # noqa: E402
import tempfile  # noqa: E402

from deployments.core.platform_bridge import (  # noqa: E402
    enrich_config_from_project,
    extract_zip_to_temp,
    get_project_model,
)
from deployments.core.types import DeploymentConfig  # noqa: E402

LARAVEL_COMPOSER = '{"require":{"laravel/framework":"^12.0"}}'


def _build_model(files, config=None):
    from deployments.core.project_model import build_project_model_from_tar

    return build_project_model_from_tar(make_tar(files), config=config)


def test_laravel_only_in_wrapper_dir():
    model = _build_model({
        "MyProject/artisan": "<?php",
        "MyProject/composer.json": LARAVEL_COMPOSER,
        "MyProject/public/index.php": "<?php",
    })
    assert model.applications[0].root == "."
    assert model.frontends == []
    assert model.flattened_wrapper == "MyProject"


def test_laravel_plus_vite_same_directory():
    model = _build_model({
        "artisan": "<?php",
        "composer.json": LARAVEL_COMPOSER,
        "package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7"}}',
        "vite.config.js": "x",
    })
    assert model.applications[0].root == "."
    assert model.frontends[0].root == "."
    assert model.frontends[0].kind == "vite"


def test_laravel_plus_vite_same_directory_in_wrapper():
    model = _build_model({
        "MyProject/artisan": "<?php",
        "MyProject/composer.json": LARAVEL_COMPOSER,
        "MyProject/package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7"}}',
        "MyProject/vite.config.js": "x",
    })
    assert model.applications[0].root == "."
    assert model.frontends[0].root == "."
    assert model.flattened_wrapper == "MyProject"


def test_laravel_plus_sibling_vite_frontend():
    model = _build_model({
        "backend/artisan": "<?php",
        "backend/composer.json": LARAVEL_COMPOSER,
        "frontend/package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7"}}',
        "frontend/vite.config.js": "x",
    })
    assert model.applications[0].root == "backend"
    assert model.frontends[0].root == "frontend"


def test_laravel_plus_sibling_vite_frontend_in_wrapper():
    model = _build_model({
        "MyProject/backend/artisan": "<?php",
        "MyProject/backend/composer.json": LARAVEL_COMPOSER,
        "MyProject/frontend/package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7"}}',
        "MyProject/frontend/vite.config.js": "x",
    })
    assert model.applications[0].root == "backend"
    assert model.frontends[0].root == "frontend"
    assert model.flattened_wrapper == "MyProject"


def test_laravel_plus_nested_frontend():
    model = _build_model({
        "services/api/laravel/artisan": "<?php",
        "services/api/laravel/composer.json": LARAVEL_COMPOSER,
        "apps/web/package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7"}}',
        "apps/web/vite.config.js": "x",
    })
    assert model.applications[0].root == "services/api/laravel"
    assert model.frontends[0].root == "apps/web"


def test_multiple_package_json_prefers_frontend_candidate():
    model = _build_model({
        "backend/package.json": '{"scripts":{"post-install-cmd":"php artisan optimize"}}',
        "backend/composer.json": LARAVEL_COMPOSER,
        "backend/artisan": "<?php",
        "frontend/package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7"}}',
        "frontend/vite.config.js": "x",
        "tools/package.json": '{"scripts":{"build":"tsc"}}',
    })
    assert model.frontend_root == "frontend"


def test_multiple_lockfiles_pnpm_by_directory():
    model = _build_model({
        "backend/package.json": '{"scripts":{"post-install-cmd":"php artisan optimize"}}',
        "backend/package-lock.json": "{}",
        "backend/composer.json": LARAVEL_COMPOSER,
        "backend/artisan": "<?php",
        "frontend/package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7"}}',
        "frontend/pnpm-lock.yaml": "lockfileVersion: '9'\n",
        "frontend/vite.config.js": "x",
    })
    assert model.frontend_root == "frontend"
    assert model.frontends[0].package_manager == "pnpm"


def test_no_frontend_laravel_still_detected():
    model = _build_model({
        "artisan": "<?php",
        "composer.json": LARAVEL_COMPOSER,
    })
    assert model.applications[0].root == "."
    assert model.frontends == []


def test_invalid_frontend_package_json_does_not_crash():
    model = _build_model({
        "artisan": "<?php",
        "composer.json": LARAVEL_COMPOSER,
        "frontend/package.json": "{not json at all",
    })
    assert model.applications[0].root == "."
    assert model.frontends == []


def test_laravel_mix_detection():
    model = _build_model({
        "artisan": "<?php",
        "composer.json": LARAVEL_COMPOSER,
        "package.json": '{"scripts":{"prod":"mix"},"devDependencies":{"laravel-mix":"6"}}',
        "webpack.mix.js": "x",
    })
    assert model.frontends[0].kind == "mix"


def test_wrapper_with_multiple_top_level_not_stripped():
    model = _build_model({
        "MyProject/backend/artisan": "<?php",
        "MyProject/backend/composer.json": LARAVEL_COMPOSER,
        "apps/web/package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7"}}',
        "apps/web/vite.config.js": "x",
        "README.md": "hi",
    })
    # Three top-level entries: flatten does not run, so no wrapper is
    # stripped and every emitted path keeps its full archive-relative form.
    assert model.flattened_wrapper is None
    assert model.applications[0].root == "MyProject/backend"
    assert model.frontend_root == "apps/web"


def test_user_override_frontend_root_wins_over_scoring():
    from deployments.core.project_model import build_project_model_from_tree

    class Config:
        frontend = {"root": "frontend"}
        environment = {}

    index = {
        "backend/package.json": "backend/package.json",
        "backend/composer.json": "backend/composer.json",
        "backend/artisan": "backend/artisan",
        "frontend/package.json": "frontend/package.json",
        "frontend/vite.config.js": "frontend/vite.config.js",
    }
    model = build_project_model_from_tree(index, config=Config())
    assert model.frontend_root == "frontend"
    assert model.frontends[0].evidence["package_json_path"] == "frontend/package.json"


def test_user_override_frontend_root_escape_rejected():
    from deployments.common.exceptions import DeploymentValidationError
    from deployments.core.project_model import build_project_model_from_tar

    for bad in ("../escape", "/etc/passwd", "a/../../escape"):

        class Config:
            frontend = {"root": bad}
            environment = {}

        try:
            build_project_model_from_tar(make_tar({
                "artisan": "<?php",
                "composer.json": LARAVEL_COMPOSER,
            }), config=Config())
        except DeploymentValidationError:
            continue
        raise AssertionError(f"frontend root {bad!r} was not rejected")


def test_user_override_frontend_kind_and_package_manager():
    class Config:
        frontend = {"root": "frontend", "kind": "vite", "package_manager": "pnpm"}
        environment = {}

    model = _build_model({
        "artisan": "<?php",
        "composer.json": LARAVEL_COMPOSER,
        "frontend/package.json": '{"scripts":{"dev":"vite"}}',
    }, config=Config())
    assert model.frontends[0].kind == "vite"
    assert model.frontends[0].package_manager == "pnpm"


def test_laravel_runtime_workdir_is_app_root():
    d = load_dockerfile_module()
    tar = make_tar({
        "MyProject/backend/artisan": "<?php",
        "MyProject/backend/composer.json": LARAVEL_COMPOSER,
        "MyProject/backend/public/index.php": "<?php",
    })
    detected = d._detect_laravel_frontend(tar)
    assert detected["laravel_root"] == "backend"
    # The PHP entrypoint derives APP_ROOT from the (post-flatten) document
    # root, so artisan migrate runs where artisan actually lives.
    script = d._php_entrypoint_script(
        is_laravel=True,
        schema_files=[],
        doc_root_rel="backend/public",
    )
    assert 'APP_ROOT="/var/www/html/backend"' in script
    assert 'cd "$APP_ROOT"' in script


def test_laravel_apache_document_root_is_post_flatten():
    d = load_dockerfile_module()
    tar = make_tar({
        "MyProject/backend/artisan": "<?php",
        "MyProject/backend/composer.json": LARAVEL_COMPOSER,
        "MyProject/backend/public/index.php": "<?php",
    })
    assert d._detect_php_document_root(tar) == "backend/public"


def test_build_context_has_no_wrapper_after_flatten():
    from deployments.core.manager.image_manager import (
        flatten_single_toplevel,
        safe_extract,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tar_stream = make_wrapped_sibling_tar()
        tar_stream.seek(0)
        with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
            safe_extract(tar, tmpdir, max_bytes=500 * 1024 * 1024)
        stripped = flatten_single_toplevel(tmpdir)
        assert stripped == "MyProject"
        entries = set(os.listdir(tmpdir))
        assert "backend" in entries
        assert "frontend" in entries
        assert "MyProject" not in entries


def test_dockerfile_paths_resolve_in_build_context():
    import tarfile as _tf

    from deployments.core.manager.image_manager import (
        flatten_single_toplevel,
        safe_extract,
    )

    d = load_dockerfile_module()

    class Config:
        environment = {}
        frontend = {}
        package_manager = "npm"
        install_command = None
        build_command = None
        runtime_version = "20"

    out = d._inject_laravel_frontend_build(
        "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
        tar_stream=make_wrapped_sibling_tar(),
        config=Config(), logger=None,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        tar_stream = make_wrapped_sibling_tar()
        tar_stream.seek(0)
        with _tf.open(fileobj=tar_stream, mode="r:*") as tar:
            safe_extract(tar, tmpdir, max_bytes=500 * 1024 * 1024)
        flatten_single_toplevel(tmpdir)
        cd_paths = re.findall(r"cd (\S+)", out)
        assert cd_paths
        for cd_path in cd_paths:
            if not cd_path.startswith("/var/www/html/"):
                continue
            rel = cd_path[len("/var/www/html/"):]
            assert os.path.isdir(os.path.join(tmpdir, rel)), (
                f"cd {cd_path} does not resolve inside the post-flatten build context"
            )
\


def test_enrich_config_attaches_post_flatten_project_model():
    import shutil
    import tempfile
    import zipfile as _zipfile

    from deployments.core.platform_bridge import (
        enrich_config_from_project,
        get_project_model,
    )
    from deployments.core.types import DeploymentConfig

    class RendererConfig:
        def __init__(self, model):
            self.environment = {}
            self.frontend = {}
            self.package_manager = "npm"
            self.install_command = None
            self.build_command = None
            self.runtime_version = "20"
            self.project_model = model

    d = load_dockerfile_module()
    work = tempfile.mkdtemp(prefix="fe-regression-")
    try:
        zip_path = os.path.join(work, "proj.zip")
        with _zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("MyProject/backend/artisan", "<?php\n")
            zf.writestr(
                "MyProject/backend/composer.json",
                '{"require":{"laravel/framework":"^12.0"}}',
            )
            zf.writestr("MyProject/backend/public/index.php", "<?php\n")
            zf.writestr(
                "MyProject/frontend/package.json",
                '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7"}}',
            )
            zf.writestr("MyProject/frontend/vite.config.js", "export default {}")

        cfg = DeploymentConfig(
            name="svc", tag="v1", zip_path=zip_path,
            dockerfile_template="", max_cpu=1.0, max_ram=512,
            networks=[], volumes=[], port=None, read_only=False,
            platform="", platform_type="app",
        )
        temp_dir, project_root = extract_zip_to_temp(zip_path)
        try:
            enriched = enrich_config_from_project(cfg, project_root)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        model = get_project_model(enriched)
        assert model is not None
        assert model.flattened_wrapper == "MyProject"
        assert model.applications[0].root == "backend"
        assert model.frontends[0].root == "frontend"
        assert enriched.application_root == "backend"
        assert enriched.frontend_root == "frontend"
        assert enriched.build_root == "frontend"
        assert enriched.runtime_root == "/var/www/html/backend"
        assert enriched.document_root == "backend/public"

        out = d._inject_laravel_frontend_build(
            "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
            tar_stream=make_wrapped_sibling_tar(),
            config=RendererConfig(model), logger=None,
        )
        assert "cd /var/www/html/frontend" in out
        assert "MyProject" not in out
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_deployment_config_accepts_root_fields():
    cfg = DeploymentConfig(
        name="svc", tag="v1", zip_path="z", dockerfile_template="",
        max_cpu=1.0, max_ram=512, networks=[], volumes=[], port=None,
        read_only=False, platform="laravel", platform_type="app",
        application_root="backend", frontend_root="frontend",
        build_root="frontend", build_output="frontend/dist",
        runtime_root="/var/www/html/backend",
        document_root="backend/public",
    )
    assert cfg.application_root == "backend"
    assert cfg.frontend_root == "frontend"
    assert cfg.runtime_root == "/var/www/html/backend"
    assert cfg.document_root == "backend/public"
    assert cfg.project_model is None


def test_full_php_render_wrapped_sibling_frontend_is_buildable():
    """End-to-end render: GitHub-style zip with backend + sibling frontend.

    Every path emitted into the Dockerfile must exist in the post-flatten
    build context: the frontend cd, the composer cd and the DocumentRoot.
    """
    import base64

    d = load_dockerfile_module()

    class Config:
        entry_point = None
        environment = {}
        platform = "laravel"
        document_root = None
        frontend = {}
        package_manager = "npm"
        install_command = None
        build_command = None
        runtime_version = "20"
        project_model = None

    out = d._render_php(
        "FROM mirror.test/php:8.2-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
        make_wrapped_sibling_tar(),
        Config(), None,
    )
    assert "cd /var/www/html/frontend" in out
    assert "RUN cd /var/www/html/backend\\" in out
    assert "MyProject" not in out
    assert "ENV APACHE_DOCUMENT_ROOT=/var/www/html/backend/public" in out
    # Well-formed: the injected frontend block must not end in a dangling
    # backslash before the next instruction.
    block = out.split("# --- Laravel frontend build (injected) ---", 1)[1]
    block_only = block.split("EXPOSE 80", 1)[0]
    last_line = [ln for ln in block_only.rstrip().splitlines() if ln.strip()][-1]
    assert not last_line.rstrip().endswith("\\")


def test_cached_laravel_frontend_stage_sees_composer_vendor():
    """Laravel/Vite frontend builds may import package CSS from vendor/.
    The cached Node stage must inherit vendor from the Composer/PHP stage.
    """
    d = load_dockerfile_module()

    class Config:
        environment = {}
        frontend = {}
        package_manager = "npm"
        install_command = None
        build_command = None
        runtime_version = "20"
        base_images = {
            "node_base_image": "paas-base/node-alpine:20-r1",
        }

    out = d._inject_laravel_frontend_build(
        "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nRUN composer install --no-dev\nCMD [\"apache2-foreground\"]\n",
        tar_stream=make_tar({
            "artisan": "<?php",
            "composer.json": LARAVEL_COMPOSER,
            "package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7"}}',
            "package-lock.json": "{}",
            "vite.config.js": "export default {}",
            "resources/css/app.css": "@import '../../vendor/pkg/resources/css/tailwind.css';",
        }),
        config=Config(), logger=None,
    )
    assert "AS deployer-backend" in out
    assert "AS deployer-frontend-builder" in out
    assert "COPY --from=deployer-backend /var/www/html/vendor /frontend/vendor" in out
    assert "FROM deployer-backend AS deployer-final" in out
    assert "COPY --from=deployer-frontend-builder /frontend/public/build /var/www/html/public/build" in out
