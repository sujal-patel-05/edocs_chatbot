# Architecture & Ingestion Decisions

## Decision 1: CHM Discovery Findings & Deviations (Phase 1)
- **No .hhk Keyword Index File**: The source `eDocs.chm` does not include an internal `.hhk` index file. Therefore, keyword and synonym mapping will be synthesized from the TOC hierarchy, `<meta name="keywords">` tags, section headings, and the extracted field/record mnemonics rather than relying on a separate binary/text index.
- **DITA Metadata (`ZOOMCATEGORY` instead of `DC.Type`)**: DITA `DC.Type` meta tags are absent. Instead, Zoom Search metadata `<meta name="ZOOMCATEGORY" content="...">` is consistently populated on pages (9,936 instances). Values map cleanly to domain types:
  - `concept` -> `concept`
  - `reference` -> `reference`
  - `task` -> `task`
  - `Records and Fields` -> `reference` (flagged for structured field extraction)
  - `Parameters` -> `reference` (parameter reference)
  - `PowerOn Lexicon` -> `reference` (PowerOn code reference)
  - `Reports` -> `reference` (report reference)
  - `Specfiles` -> `reference` (specfile reference)
  - `Video` -> `concept` / `media`
  - `topic` -> `concept`
- **Encoding**: 100% of the 7,038 HTML files in release 2023.00 are encoded in UTF-8. The multi-step fallback decoder will remain active to support potential legacy Windows-1252 files in past/future releases.
- **Orphan Pages Handling**: 64 orphan pages (not in TOC) were detected. These include release summaries and specific upgrade topics (`_WhatsNew_C.html`, `2023.00/...`). These pages contain valid documentation and will be indexed with synthetic breadcrumbs derived from file paths and titles, flagged with `orphan=True`.
