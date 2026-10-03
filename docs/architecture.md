# Architecture

## Request flow

1. `run.py` calls `blender_pipeline.__main__.main()`.
2. `bootstrap.create_application()` constructs the model, task service, companion bridge and application commands. Importing the HTTP adapter creates no application or worker pool.
3. `http/server.py` serves `web/` and translates local authenticated HTTP requests into `Application.dispatch()` calls.
4. `application/commands.py` routes the operation through one command catalog. `application/operations.py` captures/checks project identity, revision and request identity.
5. Project operations update the model, call storage adapters, and run Blender workers where necessary. Long operations run through `application/tasks.py`.
6. The browser obtains state and presents graph, inspector and render views.

The backend has no framework dependencies. Python imports use the `blender_pipeline` package explicitly. The only source-path bootstrap is in the checkout's launcher/developer scripts; production modules do not modify Python's search path.

## Module ownership

| Directory | Responsibility | Main entry points |
| --- | --- | --- |
| `application/` | Dispatch, request contracts, queued operation lifecycle | `commands.Application`, `operations.OperationContracts`, `tasks.Tasks` |
| `project/` | Working project and graph operations | `model.Pipeline`, composed `workspace.Pipeline` |
| `storage/` | Atomic persistence, revisions, portable references, personal settings | `projects.JsonProjectRepository`, `file_references.FileResolver`, `local_settings.LocalSettings` |
| `adapters/` | Operating system and external-process boundaries | `blender_runtime.BlenderRuntime`, `desktop.DesktopIntegration`, `companion_bridge.Bridge` |
| `rendering/` | Output scopes/settings and existing local render queue | `settings.RenderManagement`, `queue.RenderQueue` |
| `blender/` | `bpy` scripts and shared Blender-side helpers | `scan_blend.py`, `blender_ops.py`, `render_job.py`, `blender_linking.py` |
| `http/` | HTTP parsing, token validation, static resources | `server.create_server` |
| `web/` | Browser presentation and interaction | `js/ui_runtime.js`, `js/app_bootstrap.js`, feature scripts |
| `addon/` | Blender sidebar and live session client | `companion.py` |

`model.Pipeline` owns the core file operations. `workspace.Pipeline` composes folder, external-library, template and rendering mixins, and contains higher-level editing/linking/archive operations. This is an organized version of the existing model, not a full replacement of its internals. In particular, `workspace.py` is still a large module; extract a cohesive service when changing that area instead of adding unrelated methods there.

## Storage boundaries

`paths.py` distinguishes immutable source resources from mutable machine-local data. Constructor injection (`data_directory`, repository, runtime, desktop, resolver) lets tests and future services choose their dependencies without changing global paths.

Project format 3 is required. Loading old formats rejects them without rewrites or migration copies. Shared project data includes node IDs, relative paths, positions, groups, links and render records. Personal selection, inspector tabs, pan/zoom and panel preferences are stored separately per browser client. Browser client identity currently belongs to a browser tab's session, not a user account.

`storage/projects.py` owns validation and compare-and-save. Each write holds an OS-backed lock, compares the expected disk revision and atomically replaces JSON with an incremented revision. Locks are active coordination files, not backups.

`storage/file_references.py` is the path resolver. Stable file IDs and relative paths identify managed files. External libraries use a storage ID plus a machine-local folder mapping. Moving a project root keeps managed identity; this does not automatically repair every dependency path embedded in a `.blend` file. Blender scan caches are observations and may contain absolute paths.

## Safe operations

Project writes carry `project_id`, `expected_revision`, and `request_id`. Reads and personal view changes carry project context when applicable. Context is checked again when queued work starts, before file side effects. HTTP revision conflicts return 412; queued conflicts become failed jobs with an error code.

The local request journal durably reserves `(project_id, request_id)` so duplicate submissions retrieve the same job. A reused request ID with different arguments is rejected. Jobs left unfinished by a dead owner become Interrupted and are not automatically replayed. This is submission deduplication, not an exactly-once guarantee across arbitrary crashes.

## Blender boundary

Ordinary background work goes through `adapters/blender_runtime.py`, which invokes an explicit script under `blender/` with background mode, disabled auto-execution and an error exit code. The worker scripts add their own directory to the search path because Blender executes them as standalone files. Backend imports must never import a worker that requires `bpy`.

The companion's installable ZIP contains `addon/companion.py` and the shared linking helper. `adapters/addon_package.py` produces the archive; there is no separately maintained generated add-on source tree. The bridge discovery JSON lives in machine-local data. A custom data directory needs a matching companion Connection File preference.

## Rendering

`rendering/` owns target selection, selective overrides and the local queue. Existing process launch/output tracking remains in `project/workspace.py`; Blender executes `blender/render_job.py`. Jobs capture saved input hashes and effective settings, check them again before launch/copy, and render from isolated version inputs. Render completion must remain associated with its owning project.

A future Flamenco adapter should submit prepared jobs and store Flamenco job IDs against render versions. Flamenco should own execution status and worker scheduling. Graph target selection, settings composition, frozen inputs, output naming and project ownership remain Pipeline responsibilities. No Flamenco client, remote server or authentication system is implemented in this checkout.

## Browser structure

`web/index.html` loads scripts in an explicit order. `ui_runtime.js` defines lifecycle entry points (`render`, `inspect`, `pick`, `paintTasks`, `paintNavigator`, `run`). Features register named middleware with an order rather than replace those entry points. `app_bootstrap.js` starts state loading and owned background polling after registration.

Feature scripts still share some graph bindings and specialized helper wrappers. `project_tree.js` demonstrates a controller with injected dependencies. Prefer that pattern for new cohesive controllers. This change organizes the source and resource loading without introducing a frontend toolchain or rewriting established interactions.

## Future shared service

Preserve the application/adapter boundary, explicit contexts and portable references. Replace the single active project with project-scoped contexts, and provide transactional central metadata, authenticated users, file reservations, update subscriptions and worker ownership/recovery. Do not expose this loopback server as a workplace service by changing its bind address alone.
