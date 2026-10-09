# Architecture

AYON server backend is an async Python (3.13) application built on FastAPI,
PostgreSQL (via `asyncpg`) and Redis. It exposes a REST API, a GraphQL API
(Strawberry) and a websocket event feed, hosts server-side addons, and serves
the web frontend.

```
.
├── api/            REST endpoint modules, one package per area (auto-discovered)
├── ayon_server/    Core library: DB access, entities, events, addons, settings, ...
├── setup/          Database installation / migration and initial data (`python -m setup`)
├── schemas/        SQL schemas (public + per-project template) and numbered migrations
├── maintenance/    Periodic cleanup tasks (scheduled in-process or run standalone)
├── cli/            Plug-in commands for the `ayon_server` CLI (`./aycli`)
├── nxtools/        Backwards-compatibility shim for addons importing the old nxtools
├── static/         GraphiQL explorer, Redoc, e-mail templates
├── tests/          unit / integration (needs Postgres) / api (needs a running server)
├── docs/           Focused design notes (e.g. addon-routing.md)
└── start.sh        Container entrypoint: setup -> gunicorn/uvicorn (or maintenance only)
```

## Process model

`start.sh` runs, depending on `AYON_RUN_SETUP`, `AYON_RUN_SERVER` and
`AYON_RUN_MAINTENANCE`:

1. `python -m setup --ensure-installed` - creates the schema if the DB is
   empty, applies `schemas/migrations/*.sql`, and deploys default attributes,
   access groups, users and the initial bundle.
2. `gunicorn -k uvicorn.workers.UvicornWorker ayon_server.api.server:app`
   (or plain uvicorn, `AYON_SERVER_TYPE`). Multiple workers are supported;
   they share state only through Postgres and Redis.
3. Alternatively, `python -m maintenance` as a standalone maintenance worker.

All configuration comes from `AYON_*` environment variables, parsed into
`ayon_server.config.ayonconfig` (`ayon_server/config/ayonconfig.py`).
Runtime-editable server configuration (customization, frontend flags, ...)
lives in the database (`ayon_server/config/serverconfig.py`).

## Request lifecycle and startup

`ayon_server/api/server.py` builds the FastAPI app:

- **Import time**: REST modules from `api/` are registered (`init_api`). Every
  top-level package there that exposes a `router` is mounted under `/api`.
  This happens before addons load, because addons may depend on classes
  initialized by the API modules.
- **Lifespan** (`ayon_server/api/lifespan.py`): startup runs as a background
  task, so the process accepts connections immediately:
  `ayon_init()` (connect Postgres + Redis with retry, load extensions, install
  default event hooks, enum registry, project list) -> access groups ->
  background workers, websocket messaging, maintenance scheduler -> addon
  `pre_setup()` / `setup()` (broken addons are unloaded) -> addon routes ->
  addon static files -> frontend (mounted at `/`, so it must be last). Only
  then is the app marked ready.
- **Probes**: `/livez` is always 200 unless startup crashed; `/readyz` is 503
  until startup finishes. `ReadinessMiddleware` returns 503 for every other
  request until then.

Middleware stack (outermost first): `ReadinessMiddleware` ->
`AuthMiddleware` (resolves the user from the `accessToken` cookie, bearer
token, API key or `token` query param) -> `LoggingMiddleware` ->
`RequestContextMiddleware` (stores user / sender in a `ContextVar` used by
e.g. event dispatch). Endpoints obtain the user and other common values via
the FastAPI dependencies in `ayon_server/api/dependencies.py`
(`CurrentUser`, `ProjectName`, ...).

Other top-level routes: `/graphql` and `/graphiql`, `/ws` (websocket),
`/docs` + `/openapi.json`, `/static` (from `/storage/static`).

## `api/` - REST endpoints

Each package (e.g. `api/folders/`) contains a `router.py` defining an
`APIRouter` (with its own prefix and tag) and modules adding endpoints to it.
Endpoints are thin: validate input, check access, and delegate to
`ayon_server`. Function names become OpenAPI operation ids, which the
generated frontend/client code relies on, so renaming them is a breaking
change.

## `ayon_server/` - core library

```
ayon_server/
├── api/            App, lifespan, middlewares, dependencies, websocket messaging, frontend/static serving
├── lib/            Postgres (pool, contextual connection/transaction) and Redis (KV, cache, pub/sub)
├── config/         Env-based config (ayonconfig) and DB-stored server config
├── entities/       Entity classes (Project, Folder, Task, Product, Version, Representation, Workfile, User)
│   ├── core/       BaseEntity, TopLevelEntity, ProjectLevelEntity, attribute handling
│   └── models/     Dynamically generated pydantic models from the attribute definitions
├── operations/     Atomic batch create/update/delete of project entities (used by /operations)
├── graphql/        Strawberry schema: nodes, connections, resolvers, dataloaders
├── access/         Access groups and permission evaluation
├── auth/           Password auth, sessions (stored in Redis), tokens, API keys
├── events/         EventStream: persisted events, hooks, enrolling (job queue for services)
├── addons/         BaseServerAddon, AddonLibrary (discovery/loading), addon settings resolution
├── settings/       BaseSettingsModel / SettingsField, overrides, anatomy model
├── bundles/        Bundle (set of addon versions) helpers, project bundles
├── installer/      Addon / installer / dependency package installation (background worker)
├── activities/     Activity feed (comments, status changes, ...) and watchers
├── entity_lists/   Entity lists (playlists, review sessions, ...)
├── views/          Saved grid / list views
├── reviewables/    Reviewable media attached to versions
├── files/          Project file storage (local or S3)
├── actions/        Launcher / web actions provided by addons
├── attributes/     Attribute value validation and fixing
├── enum/           Enum registry and resolvers for dynamic enums
├── suggestions/    Mention / entity suggestions
├── metrics/        Usage metrics collection
├── background/     BackgroundWorker base and the server's workers (log collector, ...)
├── helpers/        Assorted domain helpers (anatomy, thumbnails, statuses, cloud, e-mail, ...)
├── models/         Shared pydantic base models (AyonBaseModel, RestModel, ...)
├── utils/          JSON, SQL builder (SQLTool), entity ids, hashing, strings
├── initialize.py   ayon_init(): shared bootstrap for the server and standalone tools
├── extensions.py   Loads server extensions from /extensions
├── cli.py          Typer app behind `python -m ayon_server` / `./aycli`
├── exceptions.py   AyonException hierarchy (mapped to HTTP status codes)
├── logging.py      Loguru-based logger; records are also collected to the DB
└── types.py        Shared types, validators and name regexes
```

## Data model

- **`public` schema** (`schemas/schema.public.sql`): server-wide data - users,
  projects registry, access groups, attributes, bundles, studio settings,
  site settings, events, secrets, services/hosts, addon data, config, stats.
- **`project_<name>` schemas** (`schemas/schema.project.sql`): one schema per
  project with the hierarchy (`folders`, `tasks`, `products`, `versions`,
  `representations`, `workfiles`), links, thumbnails, files, activities,
  entity lists, project anatomy aux tables (folder/task types, statuses, tags),
  project settings and project access groups.
- Entity attributes are stored as JSONB; attribute definitions live in
  `public.attributes` and drive the generated pydantic models and GraphQL
  types. Inherited attribute values are precomputed in `exported_attributes`.
- Schema changes go into a new numbered file in `schemas/migrations/` (applied
  by `setup`), and into the base schema files for fresh installs.

`Postgres.acquire()` / `Postgres.transaction()` keep the current connection in
a `ContextVar`, so nested calls reuse the same connection/transaction instead
of passing it around.

## Events and messaging

`EventStream.dispatch()` stores an event in `public.events` and publishes it
on a Redis channel. Every server worker listens on that channel
(`ayon_server/api/messaging.py`) and:

- forwards it to subscribed, authorized websocket clients (`/ws`), and
- runs global hooks registered with `EventStream.subscribe(..., all_nodes=True)`.

Local hooks run only in the dispatching process. Events are also the job
queue for external services: `/api/enroll` (`ayon_server/events/enroll.py`)
lets a service atomically claim the next unprocessed event of a topic.

Redis is additionally used for sessions, caches (`Redis.cached` /
namespaced keys) and short-lived state shared across workers.

## Addons

Addons are versioned packages in `AYON_ADDONS_DIR`, each version a subclass of
`BaseServerAddon` (`ayon_server/addons/addon.py`). The `AddonLibrary`
singleton discovers them at startup. An addon can:

- register REST routes (`add_router` / `add_endpoint`) under
  `/api/addons/{name}/{version}`, and a websocket at `.../ws`;
- serve `frontend`, `public` and `private` directories under `/addons/...`
  (see [docs/addon-routing.md](docs/addon-routing.md));
- define settings (`get_settings_model`, `get_site_settings_model`) and react
  to settings changes;
- provide actions, SSO options, client code for the desktop launcher, and
  subscribe to events in `setup()`.

Which addon versions are active is determined by **bundles**
(production / staging / dev; projects may pin their own bundle).
Addon settings are resolved by layering overrides on top of defaults:
studio (`public.settings`) -> project (`project_<name>.settings`), and
site settings (`public.site_settings`) -> project site
(`project_<name>.project_site_settings`).

## Access control

Users are admins, managers or regular users. Regular users get project
permissions from access groups (studio-level defaults, overridable per
project). `ayon_server/access/` merges a user's groups into a `Permissions`
object; entity endpoints and GraphQL resolvers enforce it (e.g.
`ensure_entity_access`, folder-path based access conditions). Services
authenticate with API keys; guest users have limited access to activities
and review content.

## Background work

- In the server process: background workers (`ayon_server/background/`:
  log collector, background installer, action cache invalidation), websocket
  messaging, and the maintenance scheduler (daily at 03:00 unless
  `AYON_RUN_MAINTENANCE` is off).
- `maintenance/tasks/`: removal of old events/logs/files/thumbnails/settings,
  index fixes, vacuum, metrics push, auto-update.
- These workers exist only inside a running server; standalone tools (CLI,
  setup, maintenance) call `ayon_init()` themselves and log only to stdout.

## Tooling

- `make check` - ruff (imports, format, lint) and mypy; `make test`,
  `make test-integration`, `make test-api` - see the Makefile for the
  required environment.
- `./aycli` / `python -m ayon_server` - CLI; commands from `cli/` (and
  `/ayon-server-cli`, `/storage/ayon-server-cli`) are loaded as plug-ins.
