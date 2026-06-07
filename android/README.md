# PDFApps — Android (native)

Native Android port of PDFApps. **Separate from the Mac desktop app** —  
`/Applications/PDFApps.app` on Mac is **not modified** by this project.

## Stack

- **Kotlin** + **Jetpack Compose**
- **Material 3** with the same dark theme colors as desktop (`app/constants.py`)
- **Navigation** mirrors desktop `_NAV_GROUPS` (15 tools, 6 groups)
- **PDF view:** Android `PdfRenderer` (native)
- **PDF ops (planned):** PDFBox-Android, ML Kit OCR, custom editor layer

## Build APK

### Option A — Android Studio (recommended)

1. Open folder `android/` in Android Studio
2. Wait for Gradle sync
3. **Build → Build Bundle(s) / APK(s) → Build APK(s)**
4. APK: `android/app/build/outputs/apk/debug/app-debug.apk`

### Option B — Command line

```bash
cd android
./gradlew assembleDebug
```

Install on device:

```bash
adb install app/build/outputs/apk/debug/app-debug.apk
```

## Feature parity roadmap

| Phase | Tools | Status |
|-------|-------|--------|
| **0** | Shell, sidebar, viewer, theme | ✅ This commit |
| **1** | Split, merge, rotate, extract, info | Planned |
| **2** | Compress, encrypt, watermark, n-up, page numbers, reorder | Planned |
| **3** | OCR (ML Kit) | Planned |
| **4** | Convert / import | Planned |
| **5** | Visual editor (text, snap, area move, multiline) | Planned |
| **6** | Presentation, search, print, 8 languages | Planned |

Desktop Python code in `app/` is the **reference** for behaviour — logic is reimplemented in Kotlin, not wrapped.

## Mac app (unchanged)

```bash
open /Applications/PDFApps.app
# or
./run-pdfapps.sh
```

## Repo layout

```
pdfapps-patched/
├── app/              ← Desktop Python (Mac/Win/Linux) — DO NOT REMOVE
├── android/          ← This Android project
├── install-macos-app.sh
└── docs/             ← Static website (Vercel)
```
