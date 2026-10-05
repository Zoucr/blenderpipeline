# Usage

## Projects and graph

Create a project or open an existing format-3 project folder. Each file node represents a real `.blend`; folder nodes organize the graph and filesystem. Not every folder is a render destination.

Add a file with an automatic **Blend 01** name and use **Open Blender** to edit. Double-click its header name to rename it. New working files use `YYMMDD_project_node-v001.blend`, for example `261004_My_Project_Camera_shot-v001.blend`. Renaming a managed file updates its disk filename in the same directory, takes recovery snapshots and repairs registered dependent libraries. Close the file and its dependent Blender windows first. Imported files acquire this naming convention when renamed; the naming date stays stable. Snapshots keep their own history rather than changing the working filename on every save.

Save in Blender before refreshing or submitting work. Middle-drag pans the graph; left-drag on empty space selects nodes. Right-click offers **Blend node**, **Render node**, **Export node**, **Folder node**, and **Frame**. With nodes selected, Folder and Frame wrap the selection. Folder grouping keeps existing files at their disk locations. File/folder deletion requires confirmation and uses the project's recovery archive where supported. A node's action menu provides **Details**, hover **Change Color**, **Copy**, **Duplicate** and its relevant removal action.

Select nodes and use **Ctrl/Cmd C**, **Ctrl/Cmd V**, or **Ctrl/Cmd D** to duplicate. Paste places the selection at the pointer and gives copies `01`, `02` suffixes. Each Blend copy is independent and preserves saved linked assets and overrides. Copying source and destination together connects the copied files to each other; other dependencies retain their original source. Folder/frame copies include their members, and operation copies remap their selected source/output IDs. New copies start with fresh snapshot/output history; old renders are not copied. Copy/paste uses the latest saved files at paste time. It works within one project and leaves normal text editing shortcuts available.

## Linked assets

Drag a linking connection between file nodes, then choose collections, objects, materials or other supported datablocks together in the linking dialog. Choose link/override behavior appropriate to the asset. Source files remain separate. Overrides and material assignments follow Blender's library rules; source material slots may require preparation.

Drop an asset connector onto empty canvas to create the next Blend File at that position, then choose what to link. A collection connector preselects that collection. Dropping inside an organizational folder creates the file there. Drop the blue output connector onto empty canvas for a compact **Folder / Render / Export** menu. Its choice creates a connected node at the drop position; Render and Export select the saved active scene by default. Clicking outside dismisses the picker. Canceling creation leaves the project untouched; canceling asset selection keeps the new file without a link.

Selecting a collection or object automatically includes its assigned materials and their shader dependencies. You do not need to select those materials separately. Inherited mesh material slots stay linked to the source. In an editable object override, switch a slot to **Object** to assign a different material. The companion's **Make active material a local copy** creates a local material for that object; it stops receiving source material edits, while any linked node groups within it remain linked.

Contents and the linking picker use collapsible collections and object/empty parenting. Arrows expand branches; the linking checkboxes select assets. Selecting a parent collection marks its descendants as included. Search reveals matching branches, and type filters preserve your selection. Large expanded trees show 200 rows at a time, with a button to reveal more. Refresh existing nodes after updating the app to read their complete hierarchy.

Long file operations show a compact activity notice and a status strip below affected node headers. They show queued/running state and elapsed time while the graph remains available. Blender file operations do not report a reliable completion percentage.

Persistent notices such as unused images and outdated outputs use a small shield at the node's bottom-left. Hover for a summary of all notices; click to open Dependencies. Resolving the underlying issue clears the icon. With no node selected, project Details uses collapsible Workspace, Rendering, Project tools and attention sections; their open state is retained while switching views.

External libraries remain visible as external nodes. If their location is unavailable, use Map storage folder in the inspector. Mapping identifies a folder on this machine; localization is a separate operation that copies dependencies into the project.

## Snapshots and templates

Snapshots capture a saved working state. Restore only after saving/closing the working file when requested. Snapshot history and recovery live under the project, not the source checkout.

Use Project → Startup templates to capture your preferred self-contained saved `.blend`. Each new node gets an independent copy; changing the template does not change existing files. This source checkout has fresh personal settings, so choose your startup file again.

## Rendering

Choose **Add → Render**, or a file's **Node actions → Add Render node**. Connect Blend-file blue outputs to the Render node, then its **Images** output to a real Folder. Dropping a file output on empty canvas offers to create a Render node; dropping Images on empty canvas offers to create its Folder. Folders remain ordinary directories and organization containers, and Frames remain visual groups.

Select the Render node or the output Folder's **Rendering** tab. Expand a setup's view-layer row to edit its scene, layer, mode and settings in place. **Add setup** on the Render node selects more scene/view-layer combinations from connected files. **Shared settings** identifies the Render node whose checked overrides apply across its setups. **More Blender settings** loads the additional settings catalog when opened. **Render all** saves pending edits and submits enabled setups; each setup also has an individual Render icon. Setup overrides, shared overrides, and one-off Rendering-workspace batch overrides apply in that order.

Leave **Filename** blank for automatic date/scene naming, or enter a custom prefix. Explicit conversion preserves an existing custom prefix. Missing scenes/cameras stay visible until you choose replacements; the rendering workspace blocks a batch containing invalid targets rather than silently substituting another scene.

Each setup gets a directory such as `Outputs/Shot/Main/Beauty/Shot_r001`, followed by independent numbered versions. Automatic images use `YYMMDD_scene_layer_frame`; whole-scene setups use `All_layers`. Existing file → Folder connections keep their date/scene naming. **Rendering** opens the project-wide targets, queue and versions; a Folder's Rendering button limits it to that output tree. Render nodes can also be chosen as a scope. Parent folders include targets from output subfolders. Target rows expand into the same inline editors. **Batch overrides** expands directly above the setups; setting rows label their effective source as Saved, Setup, Shared or Batch.

Existing file → Folder connections are preserved. **Node actions → Move output into Render node** explicitly transfers that file's scene, destination and overrides. Ordinary loading never adds nodes or moves outputs. A Render node can be removed with confirmation and restored through Archived files; its completed images remain on disk.

Leave settings inherited to preserve the saved scene's values. Enable a specific override to change it for the selected submission, such as samples across several scenes while retaining each resolution. Saved input changes require a fresh submission.

Available image textures are included in the render snapshot automatically, including absolute paths, external folders and linked materials. Single files and enumerated `<UDIM>` tile sets are supported. Copies are hash guarded; changing a collected texture while a render is queued requires a fresh submission. Project-relative textures reuse the ordinary input copy. **Collected textures** in version details lists the captured references.

Missing images that are unreferenced or only used by static, disconnected image nodes produce **Unused image notices** without interrupting rendering. Other consumers, animated node trees and uncertain usage retain a warning. This check is conservative across the saved file and its libraries; it does not guess visibility or animation switch values. Sequences and tile patterns that cannot be reliably enumerated also retain a warning.

For these remaining issues, **Image dependency warnings** offers **Locate file…**, **Render anyway**, and Cancel. Locate opens the default system file picker and copies your selected replacement into the project's hidden render assets, then checks the whole submission again. It applies to rendering and never rewrites your working Blend files. Replacement references use stable file IDs and project-relative paths; a restored, readable original takes precedence. Render anyway approves only the current submission, keeps unresolved images at their original paths, and records warnings on the queue and version. Blender can still fail if it requires the missing resource. Missing Blend libraries and other required dependencies remain blocking errors.

Rerenders receive separate version folders. Final images follow the date/scene/frame naming; additional compositor outputs include the pass name and live under the compositor folder. Deleting a render version requires the existing confirmation and ownership guards.

Rendering currently runs through local Blender processes. Flamenco and shared workplace coordination are planned architecture, not available behavior.

### Scene / view-layer setups

Connect a Blend file to a Render node once. It creates a setup for the saved active scene and view layer. Reconnecting the same file does not add more entries. Select **Setups** on the node, then **Add setup**: the picker groups view layers under their scenes, marks combinations already added, and can select all enabled layers at once. **All enabled view layers** creates one whole-scene setup; selecting each layer creates independent setups. Use **Duplicate setup** for an intentional Draft/Final variant, and optionally give it a name.

The checkbox includes a setup in **Render all**; in the Rendering workspace it selects the setup for that submission. The small Render icon saves edits and runs that setup independently. Expanded rows expose scene, layer, mode and named settings categories. **Setup options** contains camera, compositor, filename, naming and duplication controls. Blank still frame uses the saved current frame; animation settings inherit the saved range and frame step. Shared overrides show their origin and replace only enabled properties. **Save changes** stores edits; **Render all** saves and submits. Drafts survive switching between the folder, Render node and workspace within the current browser session. **Add setup** and the visible × removal save immediately. Removal offers Undo and retains the source connection and rendered versions.

A common Samples override replaces saved per-view-layer sample counts in the frozen render copy. Without it, the saved layer sampling policy is retained. Explicit advanced per-layer Samples settings take precedence over the common setting; the version details record the effective sample count for each layer.

**Compositor → Follow Blender file** uses the saved scene's compositing setting and never retargets its Render Layers nodes. The tool traces connected final/File Output nodes and nested groups, and blocks a setup if its compositor requires missing or unselected layers. Choose **All enabled view layers**, edit the compositor in Blender, or choose **Bypass compositor · raw layer** to render independently. Bypassing also disables compositor File Output nodes; use Multilayer EXR to retain raw passes. Switch inputs are checked conservatively because either branch may be needed during an animation.

New setup outputs use `<Folder>/<file>/<scene>/<view layer>/<file>_r001/`, with additional readable subfolders for named variants and numeric suffixes for collisions. Version counters belong to individual setups. Filenames use `YYMMDD_scene_layer_frame`, while whole-scene setups use `All_layers`; custom prefixes remain supported. Renaming a setup keeps its allocated directory, and changing its source/scene/layer allocates a new directory. Previous images remain accessible through Versions, including after removing a setup. Existing saved setups retain all-enabled-layer behavior until you explicitly select a layer; refresh a source to read its saved layer choices.

## Dependency status

Render-node details separate **Render setups**, **Shared settings**, **Render activity**, **Versions** and **Organization** into collapsible panels. Each setup shows its effective resolution, samples and frame range while collapsed. The Folder's **Connected setups** uses the same editor and preserves the folder selection. Open a settings category directly; descriptions appear on hover and the details panel uses one scrollbar. Shared overrides replace only checked properties for all enabled setups. Other properties remain per setup or use the saved Blender scene.

**Rendering → Render queue** groups jobs by submission. The batch bar shows saved frames and completed setups, including while the next setup is starting. Each compact row expands for logs, warnings, device details and cleanup. Cancelling a setup keeps already saved frames; the remaining setups continue with a new worker if necessary. Closing the local app cancels its owned workers and pending queue.

Graph progress strips disappear once a batch finishes or is cancelled. They describe current work; past results remain under **Render queue → Finished batches** and **Versions**, including after restarting.

Folder nodes show separate compact scene rows with their actual frame ranges or image counts, distinct view-layer counts and a **Partial** marker for incomplete sequences. **Outputs** in the folder's action row opens the output browser with the latest saved version of each setup. Larger scene lists offer a more-scenes link. Older outputs remain in **Versions**; frame gaps are retained in the summary. Ordinary folders keep their organizational role.

Unchanged files are not rescanned for every setup. A batch retains one Blender process, reloads the frozen input for each setup and preserves independent settings and output versions. Finished run details separate input-preparation time, file/settings-loading time and time spent inside Blender's render operator. A GPU's first uncached setup can still take longer than later renders.

The graph automatically refreshes saved Blend-file contents. Unsaved Blender edits remain separate and require the companion to report live status; save them before queuing renders or exports. A small node badge identifies pending source updates, unavailable files/scenes, renamed/removed linked assets or outdated outputs. Click it to open **Dependencies**, see upstream sources and affected downstream files/operations, and inspect recent added/removed content.

Refreshing an unchanged destination does not clear a pending source-update warning. Saving that destination with the updated source or explicitly refreshing its libraries acknowledges the new saved dependency state. Renamed/removed assets require review and relinking; the tool does not guess replacements or rewrite overrides.

Completed render/export versions record their input hashes and file signatures. If a saved input changes, they are labelled as older saved versions. The node badge considers the latest completed version of each target, so keeping historical renders does not keep a freshly rendered target marked outdated. File timestamps provide conservative change detection, including textures and caches in recorded manifests. Older versions without a signature for an unregistered dependency cannot fully verify that input.

## Frames and exports

Right-click the graph and choose **Frame**. Select nodes first to frame the selection. Frames can contain files, folders, exports and other frames. Move the header to move the group, resize the corner, and collapse the frame to hide its members. Frames only organize the graph: no folder is created and existing disk paths stay stable. Creating a Blend file inside a frame uses its nearest parent Folder, or the project root. **Remove node…** asks for confirmation, releases the members and keeps all files; recovery is available through **Project → Archived files**.

Choose **Add → Export**, right-click **Export node**, or drag a Blend output onto empty canvas and choose **Export**. Drag its purple contents socket onto an existing Export node to connect the source. A collection socket also selects that collection. Drag the Export node's green Files output to a real Folder, or empty canvas to create one. A visual Frame is not an output directory.

Select the Export node and use its right-hand settings: source, scene, format, whole scene or selected collections, output folder and optional animation range. The collection picker shares the collapsible saved-file hierarchy. Blank range fields inherit the saved scene. **Save settings** stores the preset; **Save + Export** runs it. The node's **Export** button repeats its saved preset.

**Timing → Animation range** exposes first/last frame, with a preview of the resolved range, inclusive frame count and saved FPS. Blank limits inherit the chosen scene's saved limits; **Use scene range** clears custom limits. **Saved current frame** exports the frame last saved in Blender. Selecting Alembic for the first time suggests animation timing. Its **Format options** include transform/geometry samples per frame and shutter open/close in frame offsets; sampling controls are inactive for a still. Alembic preserves geometry animation and hierarchy, not Blender shader graphs; **Face sets** carries material assignment groups.

Expand **Format options** for scale/axes, modifiers, geometry, materials, rig or sampling controls appropriate to the chosen format. Options are retained separately for each format when you switch, and **Reset … options** resets only that format. FBX offers bake step and curve simplification; GLB offers frame step, sampled animation and material/image choices; USD offers instancing, modifier evaluation and material/texture export. FPS comes from the saved source scene. Every version shows the actual frames exported, so inherited defaults remain traceable even after the source changes.

Each run creates a distinct `<source>_<export label>_e001` directory and records the captured settings and input hashes. Versions are listed in the inspector. Working Blend files are never saved by the exporter. Save changes in Blender first; dependency inputs must pass the existing portable-input checks. Supported formats are **GLB**, **FBX**, **USD (.usdc)** and **Alembic**. Export formats preserve different subsets of Blender data: Alembic is geometry/cache interchange, and Blender procedural shader graphs are not automatically preserved in GLB or FBX.

Shared Settings nodes are still a design proposal. Settings remain built into each operation. A future preset node should be optional and useful for sharing explicit overrides across multiple compatible operations, without automatically rewriting working Blend files.

## Companion

Download the generated companion ZIP from the running app and install it in Blender. Its Pipeline sidebar enrolls working files, reports open/dirty status, links assets, captures snapshots and requests renders. The tool uses that live status to guard background file edits.

In the 3D View sidebar (**N → Pipeline**), expand **Material / override assistant** to inspect the active object's slots. It shows the assignment's ownership separately from the shader's ownership. Choose a replacement and **Assign to active slot** to affect only this object. **Use object assignment** keeps the current linked shader; **Make shader local copy** copies the material; **Restore source assignment** returns to inheritance. Read-only linked objects and system overrides get instructions rather than forced edits. Linked geometry without slots must be prepared in its source. Material edits participate in Blender undo and are saved when you save the working file.

Expand **Render through Pipeline** to choose **Current frame** or **Scene range**, plus the connected output, another project folder, or a new output. **Save checkpoint + Queue render** saves the working file and a recovery snapshot, then submits its current scene/camera using the saved Blender settings. Existing graph sample/resolution overrides remain intact. Automatic date/scene naming and separate render versions are enabled by default. The sidebar shows the latest queue status and can open its version folder. Keep the local Pipeline tool running; full queue/version management remains in its rendering interface.

For a custom `--data-dir`, choose that directory's `companion-connection.json` in the add-on's Connection File preference. Install the package from this release to use the new default data location.

## Outputs browser

Click **Outputs** on a folder node, or select its **Outputs** details tab and click **Browse outputs**. The workspace includes that folder and its physical or graph-grouped subfolders. One compact row represents each saved scene/layer/variant; its newest version with saved images opens by default. A partial render remains viewable, while a newer failed attempt with no images does not hide an earlier result. **Other versions** stays collapsed until needed.

Select a row to view final images; the pass selector also exposes compositor outputs. Previous/next, the slider and Left/Right arrows traverse the frames actually saved, including gaps. Space toggles sequence playback; Home/End selects its first/last saved frame. Fit/100% controls image size. **Open folder** jumps directly to the viewed version. The small delete control uses the existing permanent-deletion confirmation. **Back to graph** or Escape closes the workspace.

PNG/JPEG/WebP/BMP display directly. EXR/TIFF previews are generated on demand through Blender, limited to 1600 pixels and cached in machine-local settings; the original pixels and project paths remain untouched. Multilayer EXR preview uses the image Blender loads, rather than providing individual EXR channel selection. Supported videos use the browser's player; oversized or unsupported files remain accessible through Open folder. Browsing neither changes the render directory structure nor creates node thumbnails.
