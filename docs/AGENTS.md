# AGENTS.md — Documentation Tree Rules

> Scoped sub-rules referenced by the repository root [AGENTS.md](../AGENTS.md). Read it first; this file only covers the
> documentation tree (`README.md`, `docs/`, the in-app manual) and adds nothing that contradicts the root rules.
> Written in English; the **documents themselves are Chinese** (see "Language" below).

---

## 1. What lives where

| File                                     | Role                                                                                                    |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `README.md`                              | Product-facing entry: features, installation, quick start, data formats, contribution guide             |
| `docs/manual.md`                         | **Single source of truth for the user manual**; also rendered as the in-app manual (Help → User Manual) |
| `docs/BrilliantAnnotator_用户说明书.pdf` | Generated artifact — never edit by hand                                                                 |
| `docs/generate_manual_pdf.py`            | PDF generator (`markdown` → `QTextDocument` → `QPrinter`)                                               |
| `AGENTS.md` / `docs/AGENTS.md`           | Rules for AI coding agents (English)                                                                    |

- The in-app viewer (`smart_annotator/widgets/manual_dialog.py`) reads `docs/manual.md` through `resource_path()`; the
  packaged build copies that single file into the bundle (`--add-data <manual.md>;docs` in `build.py`). The PDF is **not**
  shipped inside the application.
- Therefore `docs/manual.md` must render cleanly with `QTextDocument.setMarkdown`: keep GitHub-flavored tables, fenced
  code blocks and plain lists; avoid HTML, footnotes, nested block quotes and exotic markdown features.

## 2. Non-negotiable rules

1. **Never hand-edit generated artifacts.** After modifying `docs/manual.md`, regenerate the PDF:
   `python docs/generate_manual_pdf.py`.
2. **Generate the PDF with the default Windows platform plugin.** `QT_QPA_PLATFORM=offscreen` has no font database and
   renders Chinese as boxes — this is the documented cause of that symptom in the root AGENTS.md troubleshooting table.
3. **Bump the manual header on every edit** (product version / document version / update date / author lines); the product
   version comes from `smart_annotator/__init__.py` (`__version__`) — never invent a version.
4. **No duplicated facts.** A fact has exactly one owner: dependency versions → `requirements.txt`; build commands →
   `build.py`; behavior → `docs/manual.md`; product pitch and contribution workflow → `README.md`. Link instead of copying.
5. **Language**: `README.md` and `docs/manual.md` are Chinese; `AGENTS.md` files are English. Do not mix.
6. **Do not create new documentation files** (no extra README/notes/CHANGELOG) unless the user explicitly asks.

## 3. Keep the manual in sync with the UI

Whenever a change alters user-visible behavior, update the matching manual sections in the same task. Typical triggers:

| Change in code                                 | Manual section to update                                                  |
| ---------------------------------------------- | ------------------------------------------------------------------------- |
| New/changed tool, shortcut or menu action      | Tool table, shortcut table (including the configurable-action count), FAQ |
| New/changed dock, panel or view option         | Interface overview, right-hand panel, view settings                       |
| New/changed save, export or import flow        | The corresponding feature chapter, data locations, FAQ                    |
| New persisted preference (render config field) | Interface overview / settings notes                                       |
| Removed feature                                | Delete its sections entirely — never leave stale instructions             |

Cross-check the shortcut table against `_ACTION_DEFS` in `app.py` and `DEFAULT_SHORTCUTS` in `config.py` (they must hold
the same key set).

## 4. README rules

- Product-facing only: features, installation, quick start, data formats, documents, contribution guide. Technical route
  details, tech-stack tables, build isolation internals and locked language/toolchain versions do **not** belong here.
- Keep the feature table and quick-start steps aligned with the current UI (menus, toolbar, docks).
- The contribution guide (Fork flow, branch naming, commit format, PR expectations, issue template) lives in
  `README.md`; agents must follow the Git rules in the root AGENTS.md instead of inventing new workflow.

## 5. Verification for documentation changes

1. Paste the edited markdown through the generator:
   `python docs/generate_manual_pdf.py` — it must print the generated PDF path and size.
2. Confirm the PDF is non-trivial and contains the new content (page count and text search are enough; font subset
   embedding is a bonus check).
3. Confirm the in-app manual still loads: construct `ManualDialog` offscreen and assert the rendered text contains the new
   headings and does **not** contain the "manual file not found" fallback message.
4. When the README changed, re-read the rendered structure (heading/table/fence counts) — most README breakage is an
   unbalanced table row or code fence.