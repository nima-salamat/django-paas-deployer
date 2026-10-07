# API rate limiting and abuse prevention

PassDeployer applies layered rate limiting to the HTTP API. Counters use the Django cache; production deployments should use the shared Redis cache.

## Global protection

| Scope | Default | Identity |
|---|---:|---|
| Global IP | `600/min` | client IP |
| Global authenticated user | `1200/min` | authenticated user ID |

Every DRF endpoint receives these defaults unless it explicitly declares a stricter policy. The backend contract test requires an explicit override to retain an IP boundary.

These application limits complement, rather than replace, reverse-proxy/WAF/DDoS protection.

## Authentication, OTP and recovery

| Endpoint family | IP | Account/identifier |
|---|---:|---:|
| `/auth/api/authentication/`, `/auth/api/login/` | `20/min` | `10/min` |
| `/auth/api/login/validate/` | `20/min` | `5/min` |
| `/auth/api/login/token/` | `20/min` | `5/min` |
| `/auth/api/set-password/` | `20/min` | `10/min` |
| `/auth/api/recovery/*` | `20/min` | `5/min` |
| `/auth/api/password-recovery/*` | `20/min` | `5/min` |

The account bucket is derived from submitted email, phone_number and/or username values and hashes them before the Redis key is stored. This limits repeated attacks against one identifier even when the source IP changes. The auth IP bucket also prevents simple identifier rotation from bypassing protection.

OTP expiry and wrong-attempt limits remain separate controls through LoginSettings.otp_expire_minutes and LoginSettings.otp_max_attempts.

## Expensive authenticated operations

Ready App mutations use `10/min` per authenticated user. Contact-change request/confirmation uses `5/min`. High-cost service shell operations (session create/replace, command execution, file access/download and tree operations) use the sensitive per-user bucket, default `30/min`. Deploy keeps its existing scoped `20/min` limit. Agent keeps its contract-driven throttles and also retains the global buckets.

Existing business limits remain additional safeguards, including ticket create/message limits and the custom-email send limit.

## Configuration

Defaults can be overridden with these environment variables:

`API_GLOBAL_IP_RATE=600/min`

`API_GLOBAL_USER_RATE=1200/min`

`AUTH_IP_RATE=30/min`

`AUTH_ACCOUNT_RATE=10/min`

`API_SENSITIVE_USER_RATE=30/min`

## Cache and proxy requirements

Rate-limit counters use Django's shared cache. Redis should be used in production so multiple web workers share counters. Client IP currently comes from the first X-Forwarded-For value and falls back to REMOTE_ADDR; the reverse proxy must sanitize/overwrite forwarded-client headers.

## Tests

Targeted regression suites:

`pytest -q src/core/tests/test_api_rate_limits.py`

`pytest -q src/auth_users/tests/test_rate_limits.py`

`pytest -q src/app_catalog/tests/test_rate_limits.py`

`pytest -q src/core/tests/test_backend_contract_matrix.py`

The tests cover shared IP buckets, authenticated-user buckets across IPs, per-account auth limits, identifier rotation protection, legacy login aliases, Ready App mutation throttling and future explicit-throttle regressions.