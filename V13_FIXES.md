# v13 fixes

- Fix Laravel cached Node/Vite multi-stage build: Composer dependencies are installed in a named PHP backend stage and `vendor/` is copied into the Node builder, so frontend imports from `vendor/...` resolve.
- Final image is derived from the PHP backend stage and receives only the frontend build output.
- Base-image waiters trust the DB `READY` state before accepting a Docker tag, preventing stale/intermediate tags from winning a concurrent rebuild race.
- Base-image builder preserves deployment ownership metadata while the dedicated build is running, allowing retain-after-deploy cleanup to work even when the deployment is cancelled mid-build.
- Added regression coverage for cached Laravel frontend/vendor behavior and base-image wait semantics.
