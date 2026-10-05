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
| `exporting/` | Export presets, frozen saved inputs and versioned output records | `service.ExportWorkflow` |
| `blender/` | `bpy` scripts and shared Blender-side helpers | `scan_blend.py`, `blender_ops.py`, `render_job.py`, `blender_linking.py` |
| `http/` | HTTP parsing, token validation, static resources | `server.create_server` |
| `web/` | Browser presentation and interaction | `js/ui_runtime.js`, `js/app_bootstrap.js`, feature scripts |
| `addon/` | Blender sidebar and live session client | `companion.py` |

`model.Pipeline` owns the core file operations. `workspace.Pipeline` composes folder, external-library, template and rendering mixins, and contains higher-level editing/linking/archive operations. This is an organized version of the existing model, not a full replacement of its internals. In particular, `workspace.py` is still a large module; extract a cohesive service when changing that area instead of adding unrelated methods there.

`project/graph_nodes.py` owns graph-only frames and recoverable graph-node removal. Containers share the `group` relationship, but `physical_folder()` resolves placement to the nearest real Folder. Frame and Export nodes have stable IDs and no `path`/file reference; the resolver refuses to treat them as filesystem entries. Existing format-3 projects remain readable without rewriting their layout.

`project/node_editing.py` owns working-file naming, dependency-aware rename/move and graph selection copies. Copies allocate new node/file IDs and remap selected source/output references. Single-file copies in the same directory preserve bytes; other copies use Blender to rebase relative paths and remap copied libraries. The source manifest is hash guarded, partial copies roll back, and copies never inherit old history/output records. Rename keeps the file ID, records path aliases, snapshots affected files and repairs registered dependents. Recovery preserves concurrent source saves. Filename metadata keeps the original naming date and working version separate from snapshot counters.

`web/js/graph_clipboard.js` owns graph clipboard shortcuts and post-paste selection through the lifecycle registry. Clipboard manifests contain project/node IDs, not file data, and only the backend resolves/copies files. Text inputs retain native editing shortcuts. `web/js/graph_menu.js` owns final canvas, node-action and Blend-output creation menus, with explicit Blender icons and one outside-click handler. A drag release's synthetic click is consumed once so the picker remains usable. Node cards and operation editors stay in their existing feature modules.

`exporting/service.py` owns export presets and records. Export nodes reference source and destination IDs. Each execution validates its source scene/content, captures the existing dependency manifest, verifies isolated input copies and invokes `blender/export_job.py`. That worker never saves the working file. Outputs use exclusive version directory creation, captured settings/hashes and project ownership. Failed versions retain their status and reserve the output directory; temporary input copies are removed. Exports run through the serial application task service, with project/revision/request guards. `web/js/graph_nodes.js` supplies compact cards and inline inspector settings through the lifecycle registry.

`blender/export_settings.py` is a pure Python contract shared by the service and worker. It defines whitelisted per-format option schemas, defaults, numeric/enum checks and saved-scene timing resolution. The UI reads this schema from application state; it does not duplicate option definitions. Presets keep separate sparse options per format and nullable inherited frame limits. Version records capture resolved timing and effective format options, while the preset continues inheriting future saved scene limits. Export operator paths and selection flags cannot be overridden by client options.

## Storage boundaries

Render plans store `source_ids` separately from stable target IDs. Targets are named setups with `scene`, `view_layer` (empty means all enabled), `compositor` (`BLENDER`/`OFF`), camera, mode/frame, sparse overrides and an internally allocated readable `output_subfolder`. Duplicate scene/layer combinations are allowed for intentional variants. Output allocation ignores client-supplied paths, reserves existing setup/version paths, and keeps paths stable for label edits. Queue submissions capture effective settings and input identity; changing/removing a setup does not rewrite submitted jobs or completed versions.

`blender/render_layers.py` shares compositor dependency tracing and metadata-based selection validation between scanning, submission and the frozen worker. Traversal follows connected outputs through groups and muted-node bypasses; switch branches are conservative. Animation isolation sets enabled view layers on the frozen copy and reapplies selection before rendering, rather than relying on Blender's still-only layer operator argument. Compositor input nodes remain unchanged. Runtime logs capture actual selected layers, enabled passes and compositing mode. Unit, browser and real Blender checks cover defaults, atomic preflight, individual/batch jobs, pixel-level layer isolation, stills, version cleanup and source preservation.

`paths.py` distinguishes immutable source resources from mutable machine-local data. Constructor injection (`data_directory`, repository, runtime, desktop, resolver) lets tests and future services choose their dependencies without changing global paths.

Project format 3 is required. Loading old formats rejects them without rewrites or migration copies. Shared project data includes node IDs, relative paths, positions, groups, links and render records. Personal selection, inspector tabs, pan/zoom and panel preferences are stored separately per browser client. Browser client identity currently belongs to a browser tab's session, not a user account.

`storage/projects.py` owns validation and compare-and-save. Each write holds an OS-backed lock, compares the expected disk revision and atomically replaces JSON with an incremented revision. Locks are active coordination files, not backups.

`storage/file_references.py` is the path resolver. Stable file IDs and relative paths identify managed files. External libraries use a storage ID plus a machine-local folder mapping. Moving a project root keeps managed identity; this does not automatically repair every dependency path embedded in a `.blend` file. Blender scan caches are observations and may contain absolute paths.

## Safe operations

Project writes carry `project_id`, `expected_revision`, and `request_id`. Reads and personal view changes carry project context when applicable. Context is checked again when queued work starts, before file side effects. HTTP revision conflicts return 412; queued conflicts become failed jobs with an error code.

The local request journal durably reserves `(project_id, request_id)` so duplicate submissions retrieve the same job. A reused request ID with different arguments is rejected. Jobs left unfinished by a dead owner become Interrupted and are not automatically replayed. This is submission deduplication, not an exactly-once guarantee across arbitrary crashes.

## Blender boundary

Ordinary background work goes through `adapters/blender_runtime.py`, which invokes an explicit script under `blender/` with background mode, disabled auto-execution and an error exit code. The worker scripts add their own directory to the search path because Blender executes them as standalone files. Backend imports must never import a worker that requires `bpy`.

The companion's installable ZIP contains `addon/companion.py`, `addon/material_assistant.py`, and the shared linking helper. Material diagnostics and live slot edits belong to the Blender-only assistant module; render submission belongs to `rendering/settings.py`. `adapters/addon_package.py` produces the archive; there is no separately maintained generated add-on source tree. The bridge discovery JSON lives in machine-local data. A custom data directory needs a matching companion Connection File preference.

## Rendering

`rendering/` owns target selection, selective overrides and the local queue. Existing process launch/output tracking remains in `project/workspace.py`; Blender executes `blender/render_job.py`. Jobs capture saved input hashes and effective settings, check them again before launch/copy, and render from isolated version inputs. Render completion must remain associated with its owning project.

`rendering/inputs.py` centralizes saved-input traversal. Render image collection is opt-in through its render contract; exports retain strict dependency validation. `rendering/images.py` resolves project-owned replacements, captures texture hashes and signatures, and verifies isolated copies before launch. Files outside the project and absolute references receive collision-safe snapshot destinations; project-relative textures reuse their existing copy. Input manifests retain original references, copied destinations and content identity. Queued image changes reject stale jobs.

`blender/image_usage.py` combines the ID user map with saved node observations. Only unreferenced images and static, disconnected known image nodes are classified unused. Unknown consumers or animated trees remain uncertain. Missing unused images create nonblocking notices; other unresolved images require per-submission approval. Queue validation remains atomic across targets, and the warning set is rechecked before launch. Enumerated UDIM tiles are collected; unresolved sequence/tile sets retain warnings.

`blender/render_resources.py` remaps collected textures only in disposable render data, including linked-library-relative paths, and restores unresolved references to their original paths. It also supplies Windows extended paths where OpenImageIO would otherwise fail on long names. `locate_render_image` uses the normal operation context/revision guards, copies selected replacements into project metadata, and stores stable reference keys with relative paths. It never saves a working Blend file. Version freshness tracks collected texture signatures separately and marks approved unresolved inputs unverified. `web/js/render_warnings.js` owns review, the system picker, revalidation and compact version notices through the lifecycle registry.

`rendering/graph.py` owns Render-node plans. Each target has a stable ID, source file ID, scene/camera, enable flag and sparse overrides. The plan holds the output Folder ID and optional shared overrides. Virtual target IDs (`operation_id:target_id`) let the existing rendering workspace and queue select several scenes from one file; jobs retain the real source file reference plus separate operation/target identity. Per-target overrides merge with operation overrides before one-off batch overrides. Queue validation is atomic across the chosen targets; execution remains serial. Render nodes and Export nodes have no filesystem path. Their destination folders receive versioned output files, with per-scene subdirectories for Render nodes.

`project/dependencies.py` derives read-only upstream/downstream impact and output freshness from scan hashes, retained dependency baselines, live companion state and saved-input signatures. Graph metadata stays authoritative for node IDs and references; this observation layer does not save or repair Blender files. An unchanged-file scan retains its previous dependency baseline. Saving a changed destination or an explicit library refresh acknowledges its current dependencies. Input signatures are captured before freezing inputs, never at job completion, and duplicate signature checks are cached within a state request. Older output records remain readable; unknown freshness is not treated as a verified match.

Companion render submission saves a checkpoint, guards that working-file hash, and submits the current scene/camera/range as one-off queue settings. Graph overrides remain intact. An existing connected output is reused; the first submission can create a target. Input manifests are compared again when queuing, then by the worker. The companion catalog exposes folder choices and active/recent queue summaries.

A future Flamenco adapter should submit prepared jobs and store Flamenco job IDs against render versions. Flamenco should own execution status and worker scheduling. Graph target selection, settings composition, frozen inputs, output naming and project ownership remain Pipeline responsibilities. No Flamenco client, remote server or authentication system is implemented in this checkout.

`rendering/worker.py` owns a reusable background Blender process per submitted batch. `blender/render_worker.py` reads job paths from stdin and emits completion records keyed by run ID. The reader writes separate run logs and exposes per-job completion independently of process exit. Python failures finish a job; process crashes/cancellation invalidate the worker so the next setup starts a new one. Each setup reloads its frozen file and removes its render handlers in `finally`, preserving settings isolation. Idle batches close their worker; application shutdown cancels owned jobs and processes.

Render preparation reuses scan catalogues only when saved file signatures match. Hash preconditions and frozen-copy verification remain enforced. Identical immutable inputs in one batch can use hard links between version-owned snapshot directories, falling back to normal copies when unavailable; working files are never hard-linked. Version deletion remains independently owned. `rendering/inventory.py` groups real image files into scene/layer/version sequences and compresses frame numbers into ranges, including gaps. Folder scans are bounded at 20,000 entries and return summaries rather than an unbounded frame list.

`rendering/environment.py` retains usable default GPU caches and explicit environment overrides. On Windows, inaccessible driver caches fall back to the machine-local settings directory. This uses NVIDIA's supported `OPTIX_CACHE_PATH` / `CUDA_CACHE_PATH` variables; it never deletes or rewrites existing driver databases. See [OptiX cache-location documentation](https://raytracing-docs.nvidia.com/optix9/api/group__optix__host__api__device__context.html). Project folders and NAS storage do not own these machine caches.

## Browser structure

`web/js/render_overview.js` derives batch progress from stable submission IDs and per-run frame markers. Queued setups keep batch activity alive between workers. Render-node, folder and workspace views share those counts. Settings editors use sibling collapsible categories, lazy RNA loading and hover descriptions; progress-only polls update activity instead of rebuilding editor forms. Expansion and scroll positions remain client UI state.

`render_nodes.js` exposes one operation-plan editor for Render details, Folder rendering and the Rendering workspace. Embedded editors never change graph selection. Drafts are scoped by project and operation and are invalidated when the saved plan changes. Workspace selection is separate from the saved enable flag. Rendering saves pending editors sequentially before capturing the submission. Shared overrides identify the operation they affect; batch overrides stay submission-specific. `render_settings_ui.js` loads the additional RNA catalog only when its visible disclosure opens. Focus restoration includes operation identity when a folder contains several render operations.

`web/index.html` loads scripts in an explicit order. `ui_runtime.js` defines lifecycle entry points (`render`, `inspect`, `pick`, `paintTasks`, `paintNavigator`, `run`). Features register named middleware with an order rather than replace those entry points. `app_bootstrap.js` starts state loading and owned background polling after registration.

Feature scripts still share some graph bindings and specialized helper wrappers. `project_tree.js` demonstrates a controller with injected dependencies. Prefer that pattern for new cohesive controllers. This change organizes the source and resource loading without introducing a frontend toolchain or rewriting established interactions.

## Future shared service

Preserve the application/adapter boundary, explicit contexts and portable references. Replace the single active project with project-scoped contexts, and provide transactional central metadata, authenticated users, file reservations, update subscriptions and worker ownership/recovery. Do not expose this loopback server as a workplace service by changing its bind address alone.

## Output navigation

`rendering/output_browser.py` resolves version IDs within the active project and enumerates only the selected version. File requests use version-relative paths, reject traversal, links/junctions and metadata directories, and retain explicit project context. Authenticated POST media requests stream bounded chunks through a separate HTTP lock. EXR/TIFF conversion uses `blender/preview_image.py` without opening or saving a working Blend file; content/signature-keyed PNGs live outside projects with a 64-file/256-MiB cache limit.

`web/js/output_browser_model.js` owns pure folder-scope and setup/version grouping. `output_browser.js` owns the modeless workspace and compact folder inspector. Selection, expansion, playback and preview caches are browser-only. Selected-version metadata and media load on demand; stale responses cannot replace a newer selection, and frame changes cancel previous requests. Cache sizes are bounded, and preview URLs are released on close. Existing queue/version data and output layouts remain authoritative.
