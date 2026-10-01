# Restricted read-only deployment

This is a synthetic browsing demo, not an authenticated multi-user returns service.
No hosting deployment or live server verification is claimed.

## Prerequisites and build

Use Python 3.10+ (offline tests run on Python 3.13.4). Linux portability is supported
by source inspection, not a Linux test run. Use a hosting service with HTTPS
termination and a private backend port. Do not expose the backend directly over
unencrypted HTTP: Basic credentials require TLS at the public edge.

Set the hosting root directory to submissions/karthikk-2003. Install:

~~~sh
python -m pip install -r requirements-deploy.txt
~~~

Waitress is the only hosted-demo dependency. It replaces the local reference WSGI
server with a bounded, threaded WSGI server without changing the application or
provider stack. It was not installed during the no-network implementation run;
the real Waitress/hosting launch remains a required deployment smoke check.

## Server-controlled configuration

- DEPLOYMENT_MODE: demo enables the restricted hosted entry point; omitted means local.
- PORT: hosting-supplied integer 1–65535; defaults to 8000.
- DEMO_PUBLIC_ORIGIN: exact lower-case HTTPS origin without path, trailing slash,
  credentials or explicit port, for example https://your-demo-host.example.
- DEMO_ACCESS_TOKEN: privately generated random URL-safe token, 32–128 characters.
  Store in the host's secret configuration. Never commit it or send it in a URL.
- PYTHONPATH: agent, relative to the configured participant root.

Start:

~~~sh
python -B -m returns_manager.deployment
~~~

The browser prompts for HTTP Basic authentication: username demo, password the
privately shared demo access token. All pages/assets/APIs require access, except
GET /health. Share access with judges privately. This is a shared demo gate,
not individual reviewer authentication. Browser credentials may persist until
the browser session closes; rotating the token and restarting invalidates access.

The host must preserve the external Host header. The application does not trust
forwarded host/user headers, and Waitress clears untrusted proxy headers. It
accepts an internal HTTP hop only behind the mandatory HTTPS edge.
Public host/origin checks and same-origin browser restrictions remain enforced.
Configure edge rate limits if available. Do not allow plaintext public ingress.

## Synthetic data and initialization

Startup automatically and idempotently initializes exactly two fixed synthetic
records using the existing ingest/assessment/review pipeline. There are no photos,
supplier documents, independent annotations, visual observations or fabricated
model outputs. Fixture timestamps/identifiers are labelled synthetic; actual review
creation timestamps remain system-generated. All business dimensions remain
uncertain and disposition remains pending review.

The only database is runtime/public-demo/demo.sqlite3 under the participant
directory. Startup needs write access there for schema/seed initialization.
All HTTP requests are read-only; POST/PUT/DELETE are rejected even with access.

Optional explicit initialization from the participant directory, with PYTHONPATH
set to agent:

~~~sh
python -B -c "from returns_manager.deployment import seed_demo, DATABASE; seed_demo(DATABASE)"
~~~

Never upload the developer runtime folder/database or raw collection. This demo
does not need them, Pillow, Ollama, Gemini or Groq. On ephemeral hosting, the seed
is recreated after replacement; identifiers and assessments are deterministic.
Persisting the dedicated demo directory is optional. Do not share one SQLite
file between multiple service instances.

No browser parameter can select a tenant, reviewer, file, database, collection
or provider. Groq remains available only through the existing separately operated
collection inspection CLI; the hosted demo cannot invoke it.

## Health and smoke checks

Health path: /health; returns only status and demo mode, not provider readiness.
Configure the check with the public Host matching DEMO_PUBLIC_ORIGIN.

After deployment:
1. Confirm HTTPS and /health success.
2. Confirm unauthenticated / and /api/reviews return 401.
3. Log in privately; inspect both synthetic cases, uncertainty and history.
4. Confirm no review/inspection controls, no photos and no AI inference.
5. Confirm POST, foreign Host/Origin, arbitrary paths/tenant queries are rejected.
6. Restart and confirm the same two cases without duplicate history.
7. Verify no credentials appear in logs. Do not paste Authorization headers.

No AI request is part of these checks.

## Local workflow and rollback

The original local launcher remains unchanged:

~~~sh
python -B -m returns_manager.ui --organization org_demo_alpha --reviewer <actual-reviewer> --port 8000
~~~

The deployment launcher in local mode delegates to it and supplies PORT when
no explicit --port option is given. Local mode retains its existing mutations.

Keep the previous deployment release and a backup of its dedicated demo database.
If a release fails, stop public traffic and restore the matching release/storage.
The earlier checkpoint has no public deployment entry point: do not expose its
local server as a rollback shortcut. Return to local demonstration if necessary.
Inference is permanently disabled in this hosted demo; there is no automatic
provider fallback, retry, model verification or external API call.
