# Platform Configuration Contract

This document defines the tenant-facing `Deploy.config` overrides. The deployer is **automatic by default**. A custom value changes only the subsystem it names; all unrelated platform detection, runtime selection, base-image resolution, frontend detection, package-manager selection, resource policy, and static serving remain automatic.

## General rule

Priority is: explicit supported override > auto-detection > platform default. Invalid or unsafe overrides fail validation before Docker build. A path override must be relative to the uploaded project and must exist. No override may select a host path, privileged Docker setting, network, device, CPU/RAM limit, or arbitrary Docker host configuration.

## URL handling

Example — let the platform handle HTTPS automatically (default):

```json
{"url_handling": {"mode": "auto"}}
```

Example — let the application fully manage its own URL scheme/asset prefix:

```json
{"url_handling": {"mode": "disabled"}}
```

Example — use a custom application URL and CDN asset URL:

```json
{
  "url_handling": {
    "mode": "custom",
    "public_url": "https://example.com/my-app",
    "asset_url": "https://cdn.example.com/my-app"
  }
}
```


`url_handling` supports `mode`: `auto` (default), `disabled`, `custom`.

- `auto`: the platform supplies the public HTTPS URL/asset URL when applicable. For Laravel/PHP it also supplies proxy HTTPS detection.
- `disabled`: the deployer does not inject automatic `APP_URL`/`ASSET_URL`/`PUBLIC_URL`/HTTPS defaults. The application is responsible for its own URL configuration. Explicit user `env` values are never removed.
- `custom`: use `public_url` and/or `asset_url` from `url_handling`, or the top-level shorthand `public_url` / `asset_url`. Only URL generation changes. Static directories and build detection are unchanged.

### URL consequences

Disabling URL automation can reintroduce mixed-content or incorrect absolute URLs if the application does not understand the reverse proxy. A custom URL can intentionally point to a CDN/subpath, but it must be an HTTP(S) URL and must not contain shell metacharacters.

## Path overrides

Use `paths` for scoped overrides:

```json
{
  "paths": {
    "document_root": "public",
    "static_dir": "public/assets",
    "build_dir": "frontend/dist",
    "media_dir": "storage/app/public"
  }
}
```

The same values are accepted by the corresponding top-level legacy keys. Absolute paths and `..` traversal are rejected. If a custom path does not exist in the upload, validation fails instead of silently disabling auto-detection.

## PHP / Laravel

Allowed: `document_root`, `paths.document_root`, `url_handling`, `public_url`, `asset_url`, `static_dir`, `media_dir`, normal frontend overrides.

Default: Laravel serves from `public`. Custom `document_root` changes only Apache's served directory; Composer root/frontend detection still uses the application model. `document_root: "."` is an explicit request to serve the project root; it can expose `.env`, source, or other sensitive files and should only be used for projects designed for root serving. A wrong custom directory fails validation rather than silently switching unrelated automation off.

## React / Vue / Angular / static SPA

Allowed: `build_dir`, `paths.build_dir`, `static_dir`, `paths.static_dir`, `frontend` path overrides, `url_handling`, `public_url`.

The build output remains auto-detected unless overridden. A wrong output directory causes pre-build validation/build-output validation to fail; it does not turn off framework detection.

## Node / Next.js / Nuxt

Allowed: `build_dir`, `paths.build_dir`, `url_handling`, `public_url`, supported frontend/package-manager overrides.

`build_dir` changes only where the generated artifact is expected. Start-command and framework detection remain automatic unless separately overridden.

## Django / Flask / Python

Allowed: `static_dir`, `media_dir`, `url_handling`, `public_url`, server type and supported build/package-manager overrides.

`static_dir` changes static serving only; application entrypoint detection and WSGI/ASGI selection remain automatic.

## Go

Allowed: `build_dir`, `static_dir`, `url_handling`, `public_url` and supported build/start overrides.

## Validation guarantee

Before Docker build, the deployer validates the custom value's syntax, platform applicability and (for project paths) existence in the uploaded build context. A valid custom value is passed only to the matching renderer. Unspecified subsystems continue using automatic detection.

If an unsupported key is provided, the API should report a warning/suggestion; operator-only Docker host controls are stripped.
