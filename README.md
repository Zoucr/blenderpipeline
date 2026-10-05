# Blender Pipeline

A local, browser-based workspace for Blender projects: file and folder nodes, linked assets, snapshots, startup templates, and versioned renders. Version 1.18.0 reorganizes the working application into a source tree. It does not add a shared server or Flamenco integration.

Version 1.19.0 adds collapsible asset trees, visible operation feedback, connector-driven file creation, and companion rendering/material tools. Reinstall the generated companion (1.7.0) for checkpointed current-frame or animation rendering and the material/override assistant.

Version 1.20.0 adds visual Frame nodes and versioned Export nodes for GLB, FBX, USD and Alembic. Frames create no directories. Export settings live in the inspector and exports run from disposable saved-file copies.

Version 1.20.1 exposes format-specific export options and explicit animation timing, including Alembic frame limits, transform/geometry sampling and shutter settings. Export versions record their resolved frame range and format options.

Version 1.21.0 adds Render nodes: multiple files/scenes → one render operation → output Folder, with per-scene settings, shared overrides and separate scene/version directories. Dependency status distinguishes unsaved edits, saved source updates, renamed/removed linked assets and outdated render/export versions. Existing direct folder connections remain usable; converting one is an explicit node action.

Version 1.22.0 separates connected files from named Render setups. Each setup selects a scene and one view layer (or all enabled layers), supports a still frame or animation range/step, and has its own render action, overrides and version counter. Bulk setup selection, duplicate variants, visible removal with Undo, readable scene/layer output directories and compositor dependency checks make multi-scene files manageable. Compositing follows the saved file unless explicitly bypassed; rendering changes frozen copies only.

Version 1.23.0 adds graph copy/paste with independent saved Blend copies, retained links/overrides and remapped connections when source and destination are copied together. Managed file renames update the actual `YYMMDD_project_node-v001.blend` filename and repair registered dependent libraries. Compact creation menus, selection-aware Folder/Frame creation, a three-option output-drop picker and hover color selection simplify graph editing.

Version 1.23.1 adds per-submission **Render anyway** confirmation for image dependency warnings. Approved images use their original paths; the queue and render version retain the warnings. Required Blend libraries remain validated.

Version 1.24.0 automatically collects available external textures into immutable render inputs. Clearly unused missing images become notices; used or uncertain images offer Locate file / Render anyway. Located replacements are project-owned and leave working Blend files untouched. Versions record collected textures, notices and unresolved warnings.

Version 1.24.1 configures available Cycles GPUs inside the background worker for GPU scenes. Rendering stays visible on the file and Render nodes until it finishes, with elapsed time, stage and device details. CPU fallback is recorded explicitly, and a worker that saves no output is reported as failed.

Version 1.25.0 adds continuous batch progress, compact queue rows, scene/layer image-sequence summaries and collapsible settings categories with hover help. Unchanged files reuse scan metadata; one Blender worker handles each batch. Immutable inputs can share disk storage within a batch while versions retain independent cleanup. GPU caches use a local fallback when their normal location is unavailable. The app version appears in the bottom-left corner.

Version 1.25.1 uses the same inline setup editor in Folder rendering, Render-node details and the Rendering workspace. Expand a view layer to edit it in place; shared settings identify their owning Render node. Collapsed rows show effective resolution, sampling and frame range. Batch overrides are a disclosure panel. Pending edits survive view switches and are saved before rendering; additional Blender settings load only when their panel is opened.

Version 1.25.2 gives folder image summaries separate scene rows, accurate view-layer counts and partial-output markers, with Images in the action row. Graph progress strips show active batches only; finished or cancelled batches remain in queue history instead of reappearing as live progress after a restart. Persistent dependency notices use small warning shields with hover details, and project Details uses collapsible sections.

Version 1.25.3 isolates background Blender processes and checks in disposable working directories. Incidental startup/thumbnail-cache files are cleaned after process exit instead of accumulating in the source or project folders.

Version 1.26.0 adds a dedicated **Outputs** browser: latest saved versions per setup, collapsed history, final/compositor pass viewing, saved-frame navigation and playback, and direct access to version folders. EXR/TIFF previews are generated on demand in a bounded machine-local cache. Output directories and original render files stay intact.

## Start

Requires Python 3.11 or newer and Blender. The backend uses only the Python standard library; there is no npm install, frontend build step, or application dependency installation.

On Windows, double-click **Launch.cmd**. It uses `PIPELINE_PYTHON` if configured, otherwise the Python launcher, the existing Codex Python runtime if available, or `python` on PATH. From a terminal on any platform:

```sh
python run.py
```

The launcher prints a local URL and opens your default browser. Keep its console open. Stop with Ctrl+C. To choose a runtime explicitly:

```sh
python run.py --blender "path/to/blender" --data-dir "path/to/local-settings"
```

This checkout starts with fresh personal settings. Choose your startup `.blend` again under **Project → Startup templates**. Existing format-3 projects can be opened from their original folders. No old projects, templates, personal settings, demo data, or renders were copied into this checkout.

## Folder guide

```text
blender-pipeline/
├── Launch.cmd                  Windows launcher
├── run.py                      Cross-platform Python entry point
├── src/blender_pipeline/        Python application
│   ├── bootstrap.py            Construct the application and its dependencies
│   ├── paths.py                Source resources and machine-local locations
│   ├── application/            Commands, operation contracts, background tasks
│   ├── project/                Files, folders, links, snapshots, templates
│   ├── storage/                Project JSON, revision checks, settings, paths
│   ├── adapters/               Blender runner, desktop, pickers, companion bridge
│   ├── rendering/              Settings, render targets, local queue
│   ├── exporting/              Format presets, frozen inputs, versioned exports
│   ├── blender/                Scripts and helpers executed inside Blender
│   └── http/                   Local HTTP adapter
├── web/                        Browser interface
│   ├── index.html              Page markup and ordered script loading
│   ├── js/                     Graph and feature controllers
│   ├── css/                    Styles, including extracted base stylesheet
│   └── icons/                  Blender SVGs and their license/provenance notices
├── addon/                      Blender companion and material assistant
├── scripts/                    Checks and add-on packaging
├── tests/                      Unit, UI, integration checks and small fixtures
└── docs/                       Architecture, development and usage guides
```

Start reading [docs/architecture.md](docs/architecture.md), then [docs/development.md](docs/development.md). See [docs/usage.md](docs/usage.md) for the normal workflow.

## Where data goes

Project files live wherever you create/open a project. The project's `.pipeline/` directory holds metadata, snapshots, templates, archives and render records.

Machine settings, recent projects, the request journal and generated companion download live outside source:

- Windows: `%LOCALAPPDATA%/BlenderPipeline`
- macOS: `~/Library/Application Support/BlenderPipeline`
- Linux: `$XDG_DATA_HOME/BlenderPipeline`, or `~/.local/share/BlenderPipeline`

`--data-dir` or `PIPELINE_DATA_DIR` overrides this location. When using a custom location, set the companion's Connection File preference to its `companion-connection.json`. Projects are not automatically moved into the settings directory.

## Checks

Node.js is needed for UI tests only:

```sh
python scripts/check.py
python scripts/check.py --blender
```

Use `--node "path/to/node"` and `--blender-executable "path/to/blender"` if needed. Checks create disposable settings and projects, not changes to your working project.

## Blender companion

Launch the app, then download **Pipeline Companion** from its interface and install that ZIP in Blender. The launcher builds this download from `addon/companion.py` into the machine data directory. Reinstall for this release: the default connection location changed.

For a distributable build, run `python scripts/package_addon.py`. Its generated ZIP goes in ignored `dist/`; it is not maintained as a second source copy.

## Current limits

The app serves one active project locally. Windows desktop launching and native pickers are the tested desktop integration; a complete macOS desktop port has not been validated. Rendering still uses local Blender processes. NAS collaboration, users/permissions, remote workers and Flamenco integration require further implementation. Blender-side checks currently target Blender 5.2 LTS.
