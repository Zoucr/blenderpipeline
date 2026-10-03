# Usage

## Projects and graph

Create a project or open an existing format-3 project folder. Each file node represents a real `.blend`; folder nodes organize the graph and filesystem. Not every folder is a render destination.

Add a file with its placeholder name, rename through its header, and use Open Blender to edit. Save in Blender before refreshing the node or submitting work. Middle-drag pans the graph; left-drag on empty space selects nodes. Right-click provides file/folder creation, grouping and archive actions. File/folder deletion requires confirmation and uses the project's recovery archive where supported.

## Linked assets

Drag a linking connection between file nodes, then choose collections, objects, materials or other supported datablocks together in the linking dialog. Choose link/override behavior appropriate to the asset. Source files remain separate. Overrides and material assignments follow Blender's library rules; source material slots may require preparation.

External libraries remain visible as external nodes. If their location is unavailable, use Map storage folder in the inspector. Mapping identifies a folder on this machine; localization is a separate operation that copies dependencies into the project.

## Snapshots and templates

Snapshots capture a saved working state. Restore only after saving/closing the working file when requested. Snapshot history and recovery live under the project, not the source checkout.

Use Project → Startup templates to capture your preferred self-contained saved `.blend`. Each new node gets an independent copy; changing the template does not change existing files. This source checkout has fresh personal settings, so choose your startup file again.

## Rendering

Connect a file's output to a folder. Open Rendering for the file or output-folder scope. Parent output folders can collect targets from subfolders. Targets, Queue and Versions are views of the same rendering workspace.

Leave settings inherited to preserve the saved scene's values. Enable a specific override to change it for the selected submission, such as samples across several scenes while retaining each resolution. Saved input changes require a fresh submission.

Rerenders receive separate version folders. Final images follow the date/scene/frame naming; additional compositor outputs include the pass name and live under the compositor folder. Deleting a render version requires the existing confirmation and ownership guards.

Rendering currently runs through local Blender processes. Flamenco and shared workplace coordination are planned architecture, not available behavior.

## Companion

Download the generated companion ZIP from the running app and install it in Blender. Its Pipeline sidebar enrolls working files, reports open/dirty status, links assets, captures snapshots and requests renders. The tool uses that live status to guard background file edits.

For a custom `--data-dir`, choose that directory's `companion-connection.json` in the add-on's Connection File preference. Install the package from this release to use the new default data location.
