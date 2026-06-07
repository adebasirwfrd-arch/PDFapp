#!/usr/bin/env bash
# Install patched PDFApps to /Applications as "PDFApps" (Spotlight-friendly name).
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="PDFApps"
BUNDLE_ID="com.local.pdfapps-patched"
INSTALL_DIR="/Applications"
APP_PATH="${INSTALL_DIR}/${APP_NAME}.app"
VERSION="$(grep -E 'APP_VERSION\s*=' "${DIR}/app/constants.py" | sed -E 's/.*"([^"]+)".*/\1/')"

echo "→ Installing ${APP_NAME} v${VERSION} (patched)…"

ICON_FILE="${DIR}/icon.icns"
if [[ ! -f "${ICON_FILE}" ]]; then
  for candidate in \
    "/Applications/PDFApps Patched.app/Contents/Resources/AppIcon.icns" \
    "/Applications/PDFApps.app/Contents/Resources/AppIcon.icns"; do
    if [[ -f "${candidate}" ]]; then
      cp "${candidate}" "${ICON_FILE}"
      break
    fi
  done
fi

echo "→ Menghapus instalasi lama…"
rm -rf "/Applications/PDFApps.app" \
       "/Applications/PDFApps Patched.app" \
       "${HOME}/Applications/PDFApps Patched.app" \
       "${HOME}/Desktop/PDFApps Patched.app" \
       "${HOME}/Desktop/PDFApps.app"

mkdir -p "${APP_PATH}/Contents/MacOS" "${APP_PATH}/Contents/Resources"
printf 'APPL????' > "${APP_PATH}/Contents/PkgInfo"

if [[ -f "${ICON_FILE}" ]]; then
  cp "${ICON_FILE}" "${APP_PATH}/Contents/Resources/AppIcon.icns"
fi

/usr/bin/python3 - <<PY
import plistlib
from pathlib import Path

app_path = Path("${APP_PATH}")
info = {
    "CFBundleDevelopmentRegion": "en",
    "CFBundleDisplayName": "${APP_NAME}",
    "CFBundleExecutable": "${APP_NAME}",
    "CFBundleIdentifier": "${BUNDLE_ID}",
    "CFBundleName": "${APP_NAME}",
    "CFBundlePackageType": "APPL",
    "CFBundleShortVersionString": "${VERSION}",
    "CFBundleVersion": "${VERSION}",
    "LSMinimumSystemVersion": "10.14",
    "NSHighResolutionCapable": True,
    "LSApplicationCategoryType": "public.app-category.productivity",
    "CFBundleDocumentTypes": [{
        "CFBundleTypeName": "PDF Document",
        "CFBundleTypeRole": "Editor",
        "LSItemContentTypes": ["com.adobe.pdf"],
    }],
}
if (app_path / "Contents/Resources/AppIcon.icns").is_file():
    info["CFBundleIconFile"] = "AppIcon"
(app_path / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
PY

cat > "${APP_PATH}/Contents/MacOS/${APP_NAME}" <<LAUNCHER
#!/bin/bash
DIR="${DIR}"
PY="\${DIR}/venv/bin/python"
cd "\${DIR}" || exit 1

if [ -d "/opt/homebrew/opt/expat/lib" ]; then
  export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib\${DYLD_LIBRARY_PATH:+:\$DYLD_LIBRARY_PATH}"
fi

exec "\${PY}" pdfapps.py "\$@"
LAUNCHER

chmod +x "${APP_PATH}/Contents/MacOS/${APP_NAME}"
xattr -cr "${APP_PATH}" 2>/dev/null || true
touch "${APP_PATH}"

LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [[ -x "${LSREGISTER}" ]]; then
  "${LSREGISTER}" -f -R -trusted "${APP_PATH}" 2>/dev/null || "${LSREGISTER}" -f "${APP_PATH}" 2>/dev/null || true
fi
/usr/bin/mdimport "${APP_PATH}" 2>/dev/null || true

echo ""
echo "✓ Terpasang: ${APP_PATH}"
echo "✓ Buka: Cmd+Space → ketik \"PDFApps\""
