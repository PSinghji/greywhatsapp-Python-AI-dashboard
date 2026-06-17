#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# WhatsApp Campaign Dashboard — Protected Build Script
# ═══════════════════════════════════════════════════════════════
# This script:
#   1. Copies the project to a clean build directory
#   2. Obfuscates Python files with PyArmor
#   3. Compiles critical files to .so binaries with Cython
#   4. Removes all original .py source files
#   5. Produces a deployment-ready directory with NO readable code
#
# Requirements: pip install pyarmor cython setuptools
# ═══════════════════════════════════════════════════════════════

set -e  # Exit on any error

# ─── Configuration ──────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="${PROJECT_DIR}/dist_protected"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "═══════════════════════════════════════════════════════"
echo "  WhatsApp Campaign Dashboard — Protected Build"
echo "  Timestamp: ${TIMESTAMP}"
echo "═══════════════════════════════════════════════════════"
echo ""

# ─── Step 0: Check dependencies ────────────────────────────
echo "[0/6] Checking build dependencies..."
python3 -c "import pyarmor" 2>/dev/null || { echo "ERROR: pyarmor not installed. Run: pip install pyarmor"; exit 1; }
python3 -c "import Cython" 2>/dev/null || { echo "ERROR: Cython not installed. Run: pip install cython"; exit 1; }
echo "  ✓ All dependencies found"
echo ""

# ─── Step 1: Clean previous build ──────────────────────────
echo "[1/6] Cleaning previous build..."
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"
echo "  ✓ Clean build directory created"
echo ""

# ─── Step 2: Copy project to build directory ────────────────
echo "[2/6] Copying project files..."
# Copy everything except git, pycache, venv, build artifacts
rsync -a \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='venv' \
    --exclude='.venv' \
    --exclude='dist_protected' \
    --exclude='build' \
    --exclude='build_cython' \
    --exclude='*.egg-info' \
    --exclude='.env' \
    --exclude='setup_cython.py' \
    --exclude='build_protected.sh' \
    --exclude='.github' \
    "${PROJECT_DIR}/" "${BUILD_DIR}/"
echo "  ✓ Project files copied"
echo ""

# ─── Step 3: Obfuscate with PyArmor ────────────────────────
echo "[3/6] Obfuscating Python files with PyArmor..."
cd "${BUILD_DIR}"

# PyArmor obfuscation of main entry point and all app modules
# This wraps the code so it cannot be read even if someone extracts it
pyarmor gen \
    --output "${BUILD_DIR}/obfuscated" \
    main.py

# Obfuscate the app package
pyarmor gen \
    --output "${BUILD_DIR}/obfuscated" \
    --recursive \
    app/

echo "  ✓ PyArmor obfuscation complete"
echo ""

# ─── Step 4: Compile critical files with Cython ────────────
echo "[4/6] Compiling critical files with Cython..."
cd "${PROJECT_DIR}"

# Run Cython compilation
python3 setup_cython.py build_ext --inplace --build-lib "${BUILD_DIR}/compiled" 2>&1 | tail -5

echo "  ✓ Cython compilation complete"
echo ""

# ─── Step 5: Assemble final protected directory ─────────────
echo "[5/6] Assembling final protected build..."
FINAL_DIR="${PROJECT_DIR}/dist_final"
rm -rf "${FINAL_DIR}"
mkdir -p "${FINAL_DIR}/app/api"
mkdir -p "${FINAL_DIR}/app/models"
mkdir -p "${FINAL_DIR}/app/services"
mkdir -p "${FINAL_DIR}/app/templates/pages"
mkdir -p "${FINAL_DIR}/app/static/css"
mkdir -p "${FINAL_DIR}/app/static/js"
mkdir -p "${FINAL_DIR}/uploads"

# Copy non-Python files (templates, static, config)
cp -r "${BUILD_DIR}/app/templates/" "${FINAL_DIR}/app/templates/"
cp -r "${BUILD_DIR}/app/static/" "${FINAL_DIR}/app/static/"
cp "${BUILD_DIR}/requirements.txt" "${FINAL_DIR}/"
cp "${BUILD_DIR}/.env.example" "${FINAL_DIR}/"
cp "${BUILD_DIR}/Dockerfile" "${FINAL_DIR}/" 2>/dev/null || true
cp "${BUILD_DIR}/docker-compose.yml" "${FINAL_DIR}/" 2>/dev/null || true
cp "${BUILD_DIR}/uploads/.gitkeep" "${FINAL_DIR}/uploads/" 2>/dev/null || true

# Copy PyArmor obfuscated files (these replace original .py files)
# PyArmor creates a pyarmor_runtime package that must be included
if [ -d "${BUILD_DIR}/obfuscated" ]; then
    cp -r "${BUILD_DIR}/obfuscated/"* "${FINAL_DIR}/" 2>/dev/null || true
fi

# Copy Cython compiled .so files (these replace the .py files for critical modules)
# .so files take priority over .py files when Python imports
find "${BUILD_DIR}/compiled" -name "*.so" -exec sh -c '
    for f do
        # Determine relative path
        rel=$(echo "$f" | sed "s|${BUILD_DIR}/compiled/||")
        dir=$(dirname "$rel")
        mkdir -p "${FINAL_DIR}/$dir"
        cp "$f" "${FINAL_DIR}/$dir/"
    done
' sh {} +  2>/dev/null || true

# Copy __init__.py files (needed for Python package structure, minimal content)
for init_file in $(find "${BUILD_DIR}" -name "__init__.py" -path "*/app/*"); do
    rel=$(echo "$init_file" | sed "s|${BUILD_DIR}/||")
    dir=$(dirname "$rel")
    mkdir -p "${FINAL_DIR}/$dir"
    # Write minimal __init__.py (no business logic)
    echo "# Protected build" > "${FINAL_DIR}/$rel"
done

# Ensure main.py exists (obfuscated version)
if [ ! -f "${FINAL_DIR}/main.py" ]; then
    cp "${BUILD_DIR}/obfuscated/main.py" "${FINAL_DIR}/main.py" 2>/dev/null || \
    cp "${BUILD_DIR}/main.py" "${FINAL_DIR}/main.py"
fi

# Remove any leftover .py source files for compiled modules
# (Keep only .so binaries for critical files)
CRITICAL_FILES=(
    "app/database.py"
    "app/models/schemas.py"
    "app/api/agent.py"
    "app/api/analytics.py"
    "app/api/apikeys.py"
    "app/api/campaigns.py"
    "app/api/devices.py"
    "app/api/media.py"
    "app/api/pages.py"
    "app/api/tasks.py"
    "app/api/tuning.py"
)

for f in "${CRITICAL_FILES[@]}"; do
    so_file=$(echo "$f" | sed 's/\.py$/.cpython-*.so/')
    # If .so exists, remove the .py
    if ls "${FINAL_DIR}/${so_file}" 1>/dev/null 2>&1; then
        rm -f "${FINAL_DIR}/$f"
        echo "  → Replaced $f with compiled binary"
    fi
done

echo "  ✓ Final protected build assembled"
echo ""

# ─── Step 6: Verify and report ──────────────────────────────
echo "[6/6] Build verification..."
echo ""
echo "  Protected build directory: ${FINAL_DIR}"
echo ""
echo "  File inventory:"
echo "  ─────────────────────────────────────────"
echo "  .so binaries (compiled, unreadable):"
find "${FINAL_DIR}" -name "*.so" | sed 's/^/    /'
echo ""
echo "  .py files remaining (obfuscated or minimal):"
find "${FINAL_DIR}" -name "*.py" | sed 's/^/    /'
echo ""
echo "  Templates & static (not sensitive):"
find "${FINAL_DIR}" -name "*.html" -o -name "*.css" -o -name "*.js" | sed 's/^/    /'
echo ""

# Count files
SO_COUNT=$(find "${FINAL_DIR}" -name "*.so" | wc -l)
PY_COUNT=$(find "${FINAL_DIR}" -name "*.py" | wc -l)
echo "  Summary: ${SO_COUNT} compiled binaries, ${PY_COUNT} Python files (obfuscated/minimal)"
echo ""

# Clean up intermediate build directories
rm -rf "${BUILD_DIR}"
rm -rf "${PROJECT_DIR}/build_cython"
rm -rf "${PROJECT_DIR}/build"

echo "═══════════════════════════════════════════════════════"
echo "  BUILD COMPLETE"
echo "  Deploy from: ${FINAL_DIR}"
echo "═══════════════════════════════════════════════════════"
