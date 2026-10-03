# Development guide

## First read

Read `src/blender_pipeline/bootstrap.py`, `application/commands.py`, then the feature module you want to change. For the browser, start with `web/index.html` to see load order and `web/js/ui_runtime.js` to see lifecycle extension rules. The [architecture guide](architecture.md) explains ownership and remaining boundaries.

## Run and debug

```sh
python run.py --no-browser --data-dir /path/to/disposable/settings
```

Open the printed URL yourself. A supplied Blender path overrides saved executable settings. Use browser developer tools for frontend issues and the console/recorded project logs for Blender subprocess errors. Starting from a different terminal directory is supported; resource paths are rooted in `paths.py`.

## Add a backend operation

1. Put behavior in its owning module; filesystem identity goes through the resolver and metadata writes through the repository.
2. Add one `Command` entry in `application/commands.py`, with direct/queued permissions. Queue operations that inspect or change Blender files.
3. Call `run(action, args)` from the interface. The existing API wrapper adds project/revision/request context.
4. Add a meaningful regression for the invariant you changed. Run a Blender check if saved files, links or rendering change.

Do not add project behavior to the HTTP handler or a second command dictionary. `Application.dispatch()` is usable without HTTP. Keep client selection/navigation outside shared project metadata.

## Extend the interface

Feature scripts register middleware:

```js
PipelineUI.use('inspect', 'my-feature', 1800, function(next) {
  next();
  // Present this feature after the existing inspector.
});
```

Names must be unique within a channel. Lower order values are closer to the base; higher values wrap them. Return/await `next()` where its result matters. `PipelineUI.describe()` lists registrations. Existing bands are graph 100, workspace 200, data 300, workflow 400, templates 500, collections 600, icons 700, navigation 800, sessions 1100, linking 1200, folders/tree 1300, rendering 1500 and disclosure 1600.

For a new JS/CSS file, add its `/js/...` or `/css/...` reference to `web/index.html` at the correct dependency position. Static resources are served only from those directories and `web/icons/`. Use `PipelineUI.background()` for recurring work; it owns non-overlapping polls and lifecycle cleanup. Keep controllers explicit about their state and helper dependencies.

## Check changes

```sh
python scripts/check.py
python scripts/check.py --blender --blender-executable /path/to/blender
```

The fast command runs Python contracts, syntax/lifecycle checks for every production JS file, actual graph pointer handlers, desktop launch mocks and link-selection validation. The Blender command also exercises file creation/inspection, mixed links and overrides, material persistence, folders, templates, external libraries, actual companion operators, rendering, startup inheritance and archive recovery.

Every command receives disposable machine settings. Blender integration fixtures generate their own `.blend` files and do not depend on a developer's Desktop, old demos or previous test runs. A failure stops the suite.

For one integration check, set `PYTHONPATH` to the checkout's `src` directory and `PIPELINE_DATA_DIR` to a disposable directory, then run the desired script in `tests/integration/`. Optionally set `BLENDER_EXECUTABLE`.

## Package the companion

```sh
python scripts/package_addon.py
python scripts/package_addon.py --output /path/to/Pipeline_Companion.zip
```

Generated packages belong in `dist/` or a chosen output location. Do not commit ZIPs, `.blend` files, personal settings or screenshots as application source. Preserve the Blender icon license/provenance notices in `web/icons/`.

## Scope of the organization

This release introduces package imports, explicit application construction, separate data/resource paths, source-only add-on packaging, organized checks and developer documentation. Existing feature mixins and shared JS bindings remain and are documented. Refactor those incrementally with behavior checks; do not maintain compatibility shims for the old flat source layout.
