# PDFApps Android — implementation status

**Mac desktop:** `/Applications/PDFApps.app` — unchanged, independent.

## UI fidelity (desktop → Android)

| Element | Desktop | Android port |
|---------|---------|--------------|
| Dark teal theme `#14B8A6` | ✅ | ✅ |
| Sidebar groups (6) | ✅ | ✅ Drawer |
| 15 tools + labels | ✅ | ✅ |
| Tabbed PDF viewer | ✅ | ✅ Single doc (tabs phase 6) |
| Status bar / workspace bar | ✅ | TopAppBar |
| Maximized window layout | ✅ | Phone/tablet adaptive |

Touch adaptation is required on small screens; colours, tool names, and group order match desktop.

## Logic port map

| Desktop module | Android target |
|----------------|----------------|
| `app/tools/split.py` | `pdf/SplitService.kt` (PDFBox) |
| `app/tools/merge.py` | `pdf/MergeService.kt` |
| `app/editor/*` | `ui/editor/*` (Compose + PDFBox) |
| `app/translations.json` | `res/values-*/strings.xml` |
| `app/viewer/*` | `ui/viewer/*` |

Python code is **not** embedded on Android.
