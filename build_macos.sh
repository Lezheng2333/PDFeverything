#!/bin/bash
# ---------------------------------------------------------------------------
# PDFeverything — macOS .app 一键构建脚本
# 适配 macOS 14 ~ 26 (arm64 / Apple Silicon)
#
# 用法:
#   bash build_macos.sh          # 完整构建: venv → 依赖 → PyInstaller → zip
#   bash build_macos.sh --fast   # 跳过依赖安装，只做 PyInstaller → zip
# ---------------------------------------------------------------------------
set -eo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

APP_NAME="PDFeverything"
VERSION="1.4.2"
SPEC_FILE="PDFeverything.spec"
ZIP_NAME="${APP_NAME}-${VERSION}-macOS26.zip"

VENV_DIR="$PROJECT_DIR/venv"
DIST_DIR="$PROJECT_DIR/dist"
# macOS 26 TCC-safe: PyInstaller 缓存必须放在项目目录内，
# 避免访问 ~/Library/Application Support 时的权限错误。
PYINSTALLER_CACHE="$PROJECT_DIR/.pyinstaller_cache"

BOLD="\033[1m"; GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; RESET="\033[0m"
info()  { echo -e "${BOLD}▶${RESET} $*"; }
ok()    { echo -e "${GREEN}✅${RESET} $*"; }
warn()  { echo -e "${YELLOW}⚠️${RESET}  $*"; }
fail()  { echo -e "${RED}❌${RESET} $*"; exit 1; }

# ──────────────────────────────────────────────────────────────────────
step_env() {
    info "检查 macOS 环境..."
    [ "$(uname)" = "Darwin" ] || fail "此脚本只能在 macOS 上运行"
    info "macOS: $(sw_vers -productVersion) ($(uname -m))"

    info "检查虚拟环境..."
    if [ ! -d "$VENV_DIR" ]; then
        info "创建虚拟环境 venv..."
        python3 -m venv "$VENV_DIR"
    fi
    info "激活虚拟环境"
    source "$VENV_DIR/bin/activate"
    info "Python: $(python3 --version)"
    info "  Pip:  $(python3 -m pip --version | head -n1)"
}

step_deps() {
    info "安装 / 更新依赖..."
    python3 -m pip install --quiet --upgrade pip
    python3 -m pip install --quiet --upgrade -r requirements.txt
    ok "依赖就绪"
}

step_pyinstaller_env() {
    info "设置 TCC-safe PyInstaller 缓存目录..."
    export PYINSTALLER_CONFIG_DIR="$PYINSTALLER_CACHE"
    export PYINSTALLER_CACHE_DIR="$PYINSTALLER_CACHE"
    mkdir -p "$PYINSTALLER_CACHE"
    info "缓存目录: $PYINSTALLER_CACHE"
}

step_cleanup() {
    info "清理旧的构建产物..."
    rm -rf "$DIST_DIR"
    rm -rf "$PROJECT_DIR/build"
    find "$PROJECT_DIR" -maxdepth 2 -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
}

step_build() {
    info "启动 PyInstaller 构建..."
    if [ ! -f "$SPEC_FILE" ]; then
        fail "未找到 spec 文件: $SPEC_FILE"
    fi
    time pyinstaller "$SPEC_FILE" --noconfirm --clean
    ok "PyInstaller 构建完成"
}

step_verify() {
    local app_path="$DIST_DIR/${APP_NAME}.app"
    info "验证构建产物..."
    if [ ! -d "$app_path" ]; then
        fail "未找到 .app: $app_path"
    fi
    local bin="$app_path/Contents/MacOS/$APP_NAME"
    info "运行二进制 --version..."
    local version_out
    version_out=$("$bin" --version 2>&1) || fail "二进制运行失败: $version_out"
    info "  → $version_out"

    local bundle="$app_path/Contents/Info.plist"
    info "Info.plist bundle version: $(defaults read "$bundle" CFBundleShortVersionString 2>/dev/null || echo 'n/a')"
    local size_mb
    size_mb=$(du -sh "$app_path" | cut -f1)
    ok ".app 验证通过 — 大小: $size_mb"
}

step_zip() {
    info "打包为发布用 zip（保留 macOS resource fork）..."
    local zip_path="$DIST_DIR/$ZIP_NAME"
    rm -f "$zip_path"
    (cd "$DIST_DIR" && ditto -c -k --sequesterRsrc --keepParent "${APP_NAME}.app" "$ZIP_NAME")
    local zip_size
    zip_size=$(du -h "$zip_path" | cut -f1)
    ok "zip 生成完成: $ZIP_NAME ($zip_size)"
}

step_summary() {
    echo ""
    echo -e "${BOLD}═══ 构建完成 ═══${RESET}"
    echo "  App:   $DIST_DIR/${APP_NAME}.app"
    echo "  Zip:   $DIST_DIR/$ZIP_NAME"
    echo ""
    echo -e "  打开:     ${GREEN}open $DIST_DIR/${APP_NAME}.app${RESET}"
    echo -e "  CLI:      ${GREEN}$DIST_DIR/${APP_NAME}.app/Contents/MacOS/$APP_NAME --help${RESET}"
    echo ""
}

# ──────────────────────────────────────────────────────────────────────
FAST=0
for arg in "$@"; do
    case "$arg" in
        --fast|-f) FAST=1 ;;
        --help|-h)
            sed -n '2,8p' "$0"
            exit 0
            ;;
        *) echo "未知参数: $arg"; exit 2 ;;
    esac
done

START_TIME=$(date +%s)

trap 'fail "构建失败，运行耗时 $(($(date +%s)-START_TIME))s"' ERR

step_env
step_pyinstaller_env

if [ "$FAST" -eq 1 ]; then
    warn "fast 模式：跳过依赖安装"
else
    step_deps
fi

step_cleanup
step_build
step_verify
step_zip
step_summary

info "总耗时: $(($(date +%s)-START_TIME))s"
