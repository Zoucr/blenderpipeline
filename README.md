# Blender Pipeline

A local, browser-based workspace for Blender projects: file and folder nodes, linked assets, snapshots, startup templates, and versioned renders. Version 1.18.0 reorganizes the working application into a source tree. It does not add a shared server or Flamenco integration.

Version 1.18.1 preserves assigned materials when linking collections and objects as overrides, including after reopening. Reinstall the generated companion (1.6.1) to receive the same fix in Blender and the corrected local-material-copy action.

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
│   ├── blender/                Scripts and helpers executed inside Blender
│   └── http/                   Local HTTP adapter
├── web/                        Browser interface
│   ├── index.html              Page markup and ordered script loading
│   ├── js/                     Graph and feature controllers
│   ├── css/                    Styles, including extracted base stylesheet
│   └── icons/                  Blender SVGs and their license/provenance notices
├── addon/companion.py           Blender add-on source
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
