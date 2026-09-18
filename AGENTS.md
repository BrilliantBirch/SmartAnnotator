# AGENTS.md — BrilliantAnnotator Project Rules for AI Coding Agents

> This document is the **mandatory rule set** for AI coding agents (Trae / Cursor / Copilot, etc.) working in this repository.
> Read it in full and follow it strictly before executing any task.
> All paths are relative to the project root `e:\VAI_E\BrilliantAnnotator`.
> **Do not update this document automatically**: modifications require an explicit user request.
> Scoped sub-rules: [docs/AGENTS.md](docs/AGENTS.md) covers the documentation tree (README, `docs/`, the in-app manual);
> read it whenever a change touches documentation or user-facing text.

---

## 1. Overview

| Item              | Content                                                                                                        |
| ----------------- | -------------------------------------------------------------------------------------------------------------- |
| Project name      | BrilliantAnnotator                                                                                             |
| Product version   | Single source of truth: `__version__` in [smart_annotator/__init__.py](smart_annotator/__init__.py); file version `year.month.day.build` auto-increments |
| Positioning       | PySide6-based smart annotation tool: LabelMe ↔ YOLO conversion + ONNX auto-annotation (CPU / GPU)              |
| Language          | Python 3.12.10 (strictly locked; other versions, patch versions included, are not allowed)                     |
| GUI framework     | PySide6 6.11.1 (Qt for Python)                                                                                 |
| Inference backend | ONNX Runtime 1.28.0 — CPU (`CPUExecutionProvider`) / GPU (`CUDAExecutionProvider` from `onnxruntime-gpu`)       |
| Platform          | Windows 10/11 x64                                                                                              |
| Author            | BaiBinnan                                                                                                      |

**Core capabilities**: canvas annotation editor (rectangle / point / polygon), perceptual region (ROI) drawing and
cropped-dataset export, ONNX auto-annotation for images and videos, class selection from model metadata, and
LabelMe ↔ YOLO (incl. PaddleOCR) format conversion.

---

## 2. Core Principles (CRITICAL)

**Less is more. The simplest complete solution is the best solution.**
The action hierarchy for every change is **Delete > Replace > Add**.

1. **Solve at the owner.** Put behavior in the code path that owns or observes it. For fixes, never guard a symptom with
   a flag, a staleness check, a skip-first-call branch or a `try/except` wrapped around broken logic — relocate the
   trigger and delete the wrong path. For features, extend the existing owner instead of adding a parallel abstraction
   (example: ROI normalization lives in `labelme_io`; never re-implement it in UI code).
2. **Search and reuse first.** Search the repository before creating a component, helper, workflow or utility. Reuse or
   adapt what exists and consolidate in-scope duplication in its owner. Three similar lines beat a helper nobody calls.
3. **Delete or modify existing code before creating new code.** A new file must first prove it cannot fit cleanly in an
   existing owner. Bug fixes are net-negative by default unless relocation is demonstrably impossible.
4. **Keep scope minimal.** Implement only the simplest complete solution: no speculative flags, impossible-state
   handling, compatibility shims, policy scaffolding or unrelated cleanup. Tests are out of scope unless the user asks
   for them (project rule since 2026-08-25) — rely on focused manual verification and existing coverage.
5. **Ship zero-regression, production-ready changes.** Understand what you remove instead of keeping broken code as
   insurance; delete unused imports, functions, files and stale comments; validate the changed owner end to end. Do not
   break existing features or workflows.

**Review gate:** for every addition, first answer "would deleting, relocating or extending existing code have solved
this?" If yes, that is the required approach — a new abstraction must justify itself explicitly.

---

## 3. Git, Branch and Delivery Rules

- **NEVER** run `git commit`, `git push`, `git tag` or any release step unless the user explicitly requests it.
- **NEVER** force-push, rewrite history, amend pushed commits, or revert/delete commits you did not author.
- **NEVER** run destructive commands (`git reset --hard`, `git checkout --`, `git clean -f`, `git branch -D`) unless the
  user explicitly asks; when in doubt, ask first.
- Keep commits free of residue: temporary scripts, debug dumps, generated artifacts, local configs and `tests/` (which is
  git-ignored) must never be committed; never commit `build/` outputs or user data.
- Development happens on feature branches created from `main` (`feat_*` / `fix_*` / `docs_*` / `refactor_*`, underscore
  style). Do not perform experimental work directly on `main`.
- Two remotes exist (`VAI_E_SmartAnnotator` internal server, `github`); pushing requires an explicit instruction, tags
  included.
- Commit messages follow `<type>(<scope>): <subject>` with `feat | fix | refactor | docs | chore | release`.
- Fix review feedback on the same branch; never open replacement branches or follow-up rewrites for reviewed work.
- End every task with a short report: what changed (files), how it was verified (commands / evidence), and what was
  intentionally left out.

---

## 4. Configuration

### 4.1 Python environment and virtual environment

- Interpreter: **Python 3.12.10** (strictly locked). Environment name and path are free (conda or venv).
- Create and populate an environment:

```bash
conda create -n vai_annotator python=3.12.10
conda activate vai_annotator
pip install --no-index --find-links=./VAI_Packages -r requirements.txt
```

- GPU inference runs on the ONNX Runtime CUDA Execution Provider. Packaged GPU builds do **not** bundle CUDA runtime
  DLLs: the machine must provide **CUDA Toolkit 12.9 + cuDNN 9.x** with the cuDNN `bin` directory on `PATH`.
- There is **no TensorRT / `.engine` path anymore**. Never reintroduce a TensorRT dependency or assume `.engine` files.
- Self-check: `python --version` (must print 3.12.10) and
  `python -c "import onnxruntime as ort; print(ort.get_available_providers())"`.

### 4.2 Dependency lock

- Single source of truth: [requirements.txt](requirements.txt) (CPU) and [requirements-gpu.txt](requirements-gpu.txt)
  (replaces `onnxruntime` with `onnxruntime-gpu`). Never upgrade, downgrade or hand-edit versions outside those files —
  read them for the authoritative list.
- Offline install: `pip install --no-index --find-links=./VAI_Packages -r requirements.txt`.

### 4.3 Runtime files

| File                   | Managed by            | Description                                                              |
| ---------------------- | --------------------- | ------------------------------------------------------------------------ |
| `annotate_config.json` | User import / export  | Auto-annotation configuration (`AnnotateConfig.to_dict()`)               |
| `convert_config.json`  | User import / export  | Format conversion configuration (`ConvertConfig.to_dict()`)              |
| `download_config.ini`  | `build.py`            | Release download URLs and part counts for the online installer           |
| `VAI_Packages/`        | Maintained manually   | Offline dependency wheels                                                |

User preferences (layout, shortcuts, feature switches) persist under `%APPDATA%/BrilliantAnnotator/`.

---

## 5. Interfaces (codebase map)

### 5.1 Directory structure and owners

```
smart_annotator/
├── main.py / __main__.py      # QApplication entry points (no CLI sub-commands)
├── app.py                     # MainWindow: menus, toolbar, docks, shortcuts registry, save/load pipeline, ROI wiring
├── config.py                  # Dataclass configs + enums — the single definition point for all configuration
├── version_manager.py         # File version generation
├── styles.py                  # Global QSS
├── pages/                     # base_page / convert_page (export+import) / annotate_page (model + params)
├── widgets/                   # canvas, left_toolbar, right_panel (4 sections), *_dialog, class_selector,
│                              # drag_list, file_list_model, preview, fields, buttons, cards
├── workers/                   # QThread workers: base_worker (pause/resume/stop) + annotate / single_annotate /
│                              # convert / analyze / label_scan / model_load / roi_export / update
├── core/                      # Business logic — NO Qt imports allowed
│   ├── labelme_io.py          # LabelMe JSON I/O, shape helpers, ROI field helpers
│   ├── roi_export.py          # ROI cropping: clamp/translate shapes, write cropped images + JSON
│   ├── updater.py             # Release/version checking
│   ├── annotate/              # annotator, predictor_cache, vision/ (yolo, ocr, onnxbackend),
│   │                          # formatters/ (strategy factory), utils/, video_processor
│   └── convert/               # converter, dataset_analyzer, json_converter, txt_converter,
│                              # ppocr_converter, validator
└── utils/                     # logger, files, paths, colors, render_store, tool, qt_logger
```

### 5.2 Key data structures (config.py)

```python
# AnnotateConfig (serialized to annotate_config.json)
device: DEVICE                  # CPU / GPU
model_path / rec_model_path / rec_dict_path   # main model / OCR recognition model + dictionary
selected_classes: list          # selected class ids; empty = no filtering (detect all)
conf / nms / kpt_conf           # bbox / NMS / keypoint thresholds
ocr_thresh / ocr_box_thresh / ocr_unclip_ratio  # OCR DB postprocess parameters
ocr_rec_only: bool              # OCR "recognize only" mode
frame_interval / diff_threshold # video frame extraction
task_type: MODE                 # DETECT / POSE / SEGMENT / OCR
```

Enums `MODE`, `DEVICE` and `Format` are defined **only** in `config.py`; never redefine them elsewhere.

### 5.3 Critical chains (read before modifying)

**Class selection** — model path change → `utils/files.getModelClasses()` (parses `metadata_props["names"]`) →
`ClassSelectorWidget.set_classes()` → `AnnotateConfig.selected_classes` → `Annotator._filter_by_classes()`
(filters bboxs / scores / labels / keypoints and boundary_points in sync).

**OCR role and task detection** — `utils/files.getOcrModelRole()` classifies detection vs recognition models
(static input size, input height 48, single-channel output, metadata keys); `getModelTaskType()` resolves the task with
the chain: explicit `task` key → `kpt_shape` (POSE) → multi-output (SEGMENT) → OCR structural features → `names` table (DETECT).

**GPU inference** — always the ONNX Runtime CUDA EP (`core/annotate/vision/onnxbackend.py`). Availability is decided by
the packaged build flag (`build_mode.txt`, written by `build.py`, read via `utils/paths.get_build_mode()`) plus
`onnxruntime.get_available_providers()` in `pages/annotate_page.py:_cuda_available()`. Never depend on TensorRT,
`cuda-python` or an engine conversion step. CPU builds skip CUDA detection and always disable the GPU option.

**ROI (perceptual region)** — canvas drawing / rectangle conversion → `Canvas._rois` (undo snapshots contain shapes and
rois) → save via `labelme_io.set_document_rois` (top-level `ROI` field, removed when empty) → export via
`core/roi_export.export_image_rois` (crop image, clamp/translate annotations) driven manually (`RoiExportDialog` +
`RoiExportWorker`) or automatically after a successful save (`RenderConfig.roi_auto_export`). Output:
`<work_dir>/ROI/{stem}_ROI{id}{ext}` plus a labelme JSON without the ROI field. Batch auto-annotation preserves existing
ROI through `annotator._restore_rois`. ROI data must never enter `shapes` or take part in conversion / label scanning.

**Shortcut action registry** — `_ACTION_DEFS` (app.py) and `DEFAULT_SHORTCUTS` (config.py) must always hold the **same
key set**; adding an action requires both, otherwise shortcut resolution raises `KeyError` and the shortcut dialog
misbehaves.

### 5.4 Build system invariants (build.py)

- Modes: `python build.py --mode cpu|gpu|all|online` — run `--help` for the authoritative description instead of
  duplicating it here.
- Both modes isolate the PyInstaller subprocess environment (`_build_isolated_env`): CUDA environment variables and CUDA
  paths are stripped so host CUDA installations cannot leak into artifacts.
- **Cleanup invariant:** DLL cleanup must recurse with the **exe directory as the root** — PyInstaller places CUDA
  transitive dependencies next to the exe, and traversing only dependency sub-directories missed them (this once leaked
  ~1 GB into the CPU package). CPU mode removes every CUDA DLL (`_cleanup_cpu_redundant_dlls`); GPU mode removes TensorRT
  leftovers (`_cleanup_gpu_redundant_dlls`) and the bundled CUDA runtime (`_cleanup_gpu_cuda_runtime_dlls`).
- **Must never be deleted (GPU build):** `onnxruntime_providers_cuda.dll` — end users supply the rest of the CUDA runtime.
- `_resolve_download_config()` rewrites `download_config.ini` after zips are rebuilt; keep `.part` suffixes and
  `*_parts` values consistent. `_compile_installer()` drives Inno Setup via `_find_iscc()`.

---

## 6. Where to look (symptom → owner)

| Symptom / task                                              | Owner                                                                                   |
| ----------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Shape or ROI drawing, dragging, hit-testing, cursors         | `widgets/canvas.py` (`mousePressEvent`, `_roi_press`, `_roi_at`, `_hit_roi_vertex`, `_clamp_to_image`) |
| ROI data lost or written incorrectly                         | `core/labelme_io.py` (`document_rois` / `set_document_rois`), `app.py:_write_annotation`  |
| ROI lost after re-annotation                                 | `core/annotate/annotator.py:_restore_rois`                                              |
| Cropped image or truncated annotation is wrong               | `core/roi_export.py` (`clamp_shapes_to_box`, `export_image_rois`)                        |
| Shortcut does nothing / shortcut dialog reports a conflict   | `app.py:_ACTION_DEFS` vs `config.DEFAULT_SHORTCUTS` (must match), `_apply_shortcuts`     |
| Menu entry or toolbar button missing                         | `app.py:_build_menubar`, `widgets/left_toolbar.py` (`_ICON_PAINTERS`, `_button_texts`)   |
| Saving / loading / dirty-state bugs                          | `app.py:_write_annotation`, `_load_image_by_index`, `_on_shapes_changed` (`_loading` guard) |
| Delete key deletes the wrong thing                           | `app.py:_on_delete_shortcut` (focus-based routing)                                      |
| Dock/toolbar layout not restored                             | `objectName` on QDockWidget/QToolBar, `app.py:_apply_panel_sizes`, `RenderConfig.dock_state` |
| Model class list empty or task type wrong                    | `utils/files.py` (`getModelClasses`, `getModelTaskType`, `getOcrModelRole`)             |
| GPU not used / inference slow                                | `pages/annotate_page.py:_cuda_available`, `core/annotate/vision/onnxbackend.py`, `utils/paths.get_build_mode` |
| Model reloaded on every task                                 | `core/annotate/predictor_cache.py`                                                      |
| Batch/video progress, pause, abort                           | `workers/base_worker.py`, `widgets/annotate_dialogs.py`                                 |
| Conversion (YOLO / PaddleOCR) failures                       | `core/convert/` (`json_converter`, `txt_converter`, `ppocr_converter`, `validator`)     |
| Label scan or statistics                                     | `workers/label_scan_worker.py`, `core/labelme_io.collect_labels_from_files`, `widgets/scan_stats_dialog.py` |
| In-app manual or README out of date                          | `docs/manual.md` + [docs/AGENTS.md](docs/AGENTS.md) (regenerate the PDF)                 |
| Packaging size / missing DLL                                 | `build.py` cleanup chain (see 5.4)                                                      |
| Online update check or download                              | `core/updater.py`, `workers/update_worker.py`                                           |

---

## 7. Commands and their pitfalls

```bash
# Run the application (from the project root, compliant environment)
python -m smart_annotator

# Minimum verification after any code change
python -m py_compile <modified files>
python -c "import smart_annotator"

# Optional test suite (not mandatory; run only when the user asks)
python -m pytest tests/ -v --tb=short
```

- **GUI verification must run headless**: set `QT_QPA_PLATFORM=offscreen`. In offscreen smoke tests, stub every modal
  dialog (`_confirm_destructive`, `showMessageBox`, `QDialog.exec`) or the run hangs forever.
- **Redirect `APPDATA` to a temporary directory** for any run that touches user preferences, so the real
  `%APPDATA%/BrilliantAnnotator` configuration is never modified by verification runs.
- Temporary scripts and generated data must live in the system temp directory and be deleted afterwards — never leave
  artifacts in the repository (report `git status` as evidence when asked).
- The manual PDF must be generated with the **default Windows platform plugin** — `QT_QPA_PLATFORM=offscreen` has no font
  database and renders Chinese as boxes (see [docs/AGENTS.md](docs/AGENTS.md)).
- `tests/` is git-ignored; never commit it, and never point pytest at `smart_annotator/` (module doctests are not part of CI).
- Building installers is a maintainer activity; do not run `build.py` to verify documentation or UI-only changes.

---

## 8. Coding rules (mandatory)

> This rule set is written in English, but **code artifacts stay Chinese** (see 8.3).

### 8.1 Anti-hallucination (highest priority)

1. **Read before write**: always read a file with the Read tool before modifying it; never edit from memory.
2. **Never invent APIs**: class / method / attribute / config-key names must be confirmed by Grep in this repository or
   seen explicitly in a file you have read.
3. **Never assume file paths**: confirm every path with Glob/Grep before using it.
4. **Never assume dependency behaviour**: third-party APIs follow the versions installed from `VAI_Packages/`.

### 8.2 File header comment (every .py file)

```python
# -*- coding: utf-8 -*-
"""
<file purpose>

Author: BaiBinnan
Created: YYYY-MM-DD
Updated: YYYY-MM-DD <summary of this change>
"""
```

- Every modification appends an `Updated:` line; new files must contain the complete header.
- Header content (purpose, change summary) is written in Chinese.

### 8.3 Code style

- All code comments, docstrings, log messages and UI strings are written in **Chinese**.
- Every function needs a docstring covering Args / Returns / Raises (when exceptions are possible).
- Add comments at block starts, block ends and key steps.
- Do not use syntax or standard-library features deprecated in Python 3.12.

### 8.4 Architecture conventions

- **Single config definition point**: dataclasses in `config.py`; pages collect via `collect_config()` and restore via
  `apply_config()`.
- **Threading model**: long-running work belongs to `QThread` subclasses in `workers/` reporting back through signals —
  never run inference or conversion on the UI thread.
- **`core/` stays Qt-free**: no `PySide6` import under `smart_annotator/core/`.
- **Adopt new mechanisms completely**: no forward-compatibility shims or transitional code paths during refactors.
- **Cleanup**: remove redundant code, comments, temporary test files and unused dependencies before finishing a task.

### 8.5 Extension boundaries

- New task type → extend `core/annotate/formatters/` (+ factory) and `MODE` in `config.py`; never add `if/else` task
  branches to shared code.
- New config field → the dataclass in `config.py` plus `to_dict` / `from_dict`; nothing else may define configuration.
- New long-running task → a `workers/` subclass following `BaseWorker`, surfaced through the existing modal progress
  dialog pattern.
- New configurable shortcut action → `_ACTION_DEFS` + `DEFAULT_SHORTCUTS` + the `_apply_shortcuts` map + a menu QAction.
- Do not fork the canvas rendering/interaction pipeline: extend the existing tool branches, `_render_rois` and vertex
  handling instead of duplicating them.
- ROI data lives outside `shapes`; keep the labelme JSON contract (`labelme_io`) as the single normalization point.

### 8.6 Prohibitions

- Do not enable the `optimize=2` (-OO) packaging option (it strips docstrings numpy depends on).
- Do not apply UPX to `nvinfer*.dll` (breaks NVIDIA signatures, triggers antivirus false positives).
- Do not exclude the standard-library modules `urllib` / `email` / `socket` / `inspect` / `zipfile` (PyInstaller runtime hooks).
- Do not commit `tests/`.
- Do not reintroduce TensorRT / `.engine` conversion paths.

---

## 9. Troubleshooting (build, packaging, tooling)

| Symptom                                                       | Cause                                                                                            | Fix                                                                                                      |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| CPU installer is abnormally large (>300 MB)                   | PyInstaller collected CUDA transitive dependencies of `onnxruntime-gpu` next to the exe            | Ensure `_cleanup_cpu_redundant_dlls(exe_dir)` runs with the exe directory as root                         |
| GPU build is abnormally large                                 | CUDA runtime DLLs (cuDNN / cuBLAS / cuFFT) were not removed                                        | Ensure `_cleanup_gpu_cuda_runtime_dlls(exe_dir)` ran and `onnxruntime_providers_cuda.dll` was kept        |
| GPU option is greyed out                                      | No CUDA EP available (CPU build flag or CPU-only onnxruntime), or no NVIDIA driver                 | Install `onnxruntime-gpu` plus CUDA Toolkit 12.9 + cuDNN 9.x on `PATH`, or use the GPU installer package  |
| Intel oneMKL errors                                           | Incomplete build environment (numpy `mkl_*.dll` not collected)                                     | Run PyInstaller in an environment satisfying 4.1 with all runtime dependencies installed                   |
| Manual PDF shows Chinese as boxes                             | The script ran with `QT_QPA_PLATFORM=offscreen` (no font database)                                 | Run `docs/generate_manual_pdf.py` with the default Windows platform plugin                                 |
| Installer compilation skipped ("Inno Setup script not found") | Building from an unexpected branch                                                                 | Confirm the checked-out branch and the `ISCC.exe` path returned by `_find_iscc()`                          |
| Online installer downloads the wrong package                  | `download_config.ini` out of sync with the new part count                                          | After rebuilding zips, verify `cpu_url` / `gpu_url` `.part` suffixes match `*_parts`                        |
| Zip part deletion fails                                       | Antivirus / indexing service holds a lock                                                          | `_split_zip` retries 5 times; on failure it only warns and the files can be deleted manually                |

---

## 10. Post-change verification checklist

After any code change (running tests is optional, but the following minimum verification is not):

1. `python -m py_compile <modified files>` — syntax passes.
2. `python -c "import <modified module>"` — import passes (inside an environment satisfying 4.1).
3. UI-related changes: confirm importing the touched `smart_annotator.pages.*` / `smart_annotator.widgets.*` modules succeeds,
   and run an offscreen smoke check for the affected window (see section 7).
4. Packaging-related changes: confirm `python build.py --mode cpu` succeeds and the artifact size matches the baseline.
5. Documentation changes: regenerate the PDF after editing `docs/manual.md` and follow [docs/AGENTS.md](docs/AGENTS.md).