#!/usr/bin/env bash
set -e

# Farben für Terminalausgabe
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}==>${NC} Installation von txt2pdf wird gestartet..."

# 1. Prüfe Python 3
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Fehler:${NC} Python 3 ist nicht installiert. Bitte installieren Sie Python 3."
    exit 1
fi

# 2. Prüfe Typst
if ! command -v typst &>/dev/null; then
    echo -e "${BLUE}==>${NC} Typst wurde nicht gefunden. Typst wird über Homebrew installiert..."
    if command -v brew &>/dev/null; then
        brew install typst
    else
        echo -e "${RED}Hinweis:${NC} Homebrew ist nicht installiert. Bitte installieren Sie Typst manuell: https://github.com/typst/typst"
    fi
fi

# 3. Prüfe und installiere Schriftart PT Serif
echo -e "${BLUE}==>${NC} Prüfe Schriftart PT Serif..."
FONT_INSTALLED=false

if command -v typst &>/dev/null && typst fonts 2>/dev/null | grep -qi "PT Serif"; then
    FONT_INSTALLED=true
fi

# Bestimme systemspezifischen Schriftartenordner
if [[ "$OSTYPE" == "darwin"* ]]; then
    FONTS_DIR="$HOME/Library/Fonts"
else
    FONTS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/fonts"
fi
mkdir -p "$FONTS_DIR"

if [ -f "$FONTS_DIR/PTSerif-Regular.ttf" ]; then
    FONT_INSTALLED=true
fi

SCRIPT_SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$FONT_INSTALLED" = false ]; then
    echo -e "${BLUE}==>${NC} Installiere PT Serif nach $FONTS_DIR..."
    FONT_FILES=("PTSerif-Regular.ttf" "PTSerif-Bold.ttf" "PTSerif-Italic.ttf" "PTSerif-BoldItalic.ttf")
    
    if [ -d "$SCRIPT_SRC_DIR/fonts" ] && [ -f "$SCRIPT_SRC_DIR/fonts/PTSerif-Regular.ttf" ]; then
        cp "$SCRIPT_SRC_DIR/fonts"/PTSerif*.ttf "$FONTS_DIR/"
    else
        RAW_FONT_BASE="https://raw.githubusercontent.com/jonathank55/txt2pdf/main/fonts"
        for font_file in "${FONT_FILES[@]}"; do
            echo -e "    Lade $font_file herunter..."
            curl -fsSL "$RAW_FONT_BASE/$font_file" -o "$FONTS_DIR/$font_file"
        done
    fi

    if command -v fc-cache &>/dev/null; then
        fc-cache -f "$FONTS_DIR" &>/dev/null || true
    fi
    echo -e "${GREEN}==>${NC} PT Serif wurde erfolgreich installiert."
else
    echo -e "${GREEN}==>${NC} PT Serif ist bereits vorhanden."
fi

# 3b. Prüfe und installiere Schriftart Roboto
echo -e "${BLUE}==>${NC} Prüfe Schriftart Roboto..."
ROBOTO_INSTALLED=false

if command -v typst &>/dev/null && typst fonts 2>/dev/null | grep -qi "Roboto"; then
    ROBOTO_INSTALLED=true
fi

if [ -f "$FONTS_DIR/Roboto-Regular.ttf" ] || [ -f "$FONTS_DIR/Roboto[wdth,wght].ttf" ]; then
    ROBOTO_INSTALLED=true
fi

if [ "$ROBOTO_INSTALLED" = false ]; then
    echo -e "${BLUE}==>${NC} Installiere Roboto nach $FONTS_DIR..."
    if [[ "$OSTYPE" == "darwin"* ]] && command -v brew &>/dev/null; then
        brew install --cask font-roboto 2>/dev/null || true
    fi
    if ! (command -v typst &>/dev/null && typst fonts 2>/dev/null | grep -qi "Roboto"); then
        curl -fsSL "https://raw.githubusercontent.com/google/fonts/main/ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf" -o "$FONTS_DIR/Roboto[wdth,wght].ttf" 2>/dev/null || true
        curl -fsSL "https://raw.githubusercontent.com/google/fonts/main/ofl/roboto/Roboto-Italic%5Bwdth%2Cwght%5D.ttf" -o "$FONTS_DIR/Roboto-Italic[wdth,wght].ttf" 2>/dev/null || true
    fi
    if command -v fc-cache &>/dev/null; then
        fc-cache -f "$FONTS_DIR" &>/dev/null || true
    fi
    echo -e "${GREEN}==>${NC} Roboto wurde erfolgreich eingerichtet."
else
    echo -e "${GREEN}==>${NC} Roboto ist bereits vorhanden."
fi

# 4. Prüfe und installiere DeepL Python-Bibliothek
echo -e "${BLUE}==>${NC} Prüfe DeepL-Bibliothek..."
if ! python3 -c "import deepl" &>/dev/null; then
    echo -e "${BLUE}==>${NC} Installiere DeepL Python-Bibliothek..."
    python3 -m pip install --break-system-packages deepl 2>/dev/null || python3 -m pip install deepl 2>/dev/null || true
    if python3 -c "import deepl" &>/dev/null; then
        echo -e "${GREEN}==>${NC} DeepL-Bibliothek wurde erfolgreich installiert."
    else
        echo -e "${RED}Hinweis:${NC} DeepL-Paket konnte nicht automatisch installiert werden. Für Übersetzungen bitte 'pip install deepl' ausführen."
    fi
else
    echo -e "${GREEN}==>${NC} DeepL-Bibliothek ist bereits vorhanden."
fi

# 5. Bestimme Zielverzeichnis für die Binärdatei
INSTALL_DIR="/usr/local/bin"
if [ ! -w "$INSTALL_DIR" ]; then
    INSTALL_DIR="$HOME/.local/bin"
    mkdir -p "$INSTALL_DIR"
fi

TARGET_BIN="$INSTALL_DIR/txt2pdf"

# 6. Download oder lokale Kopie
if [ -f "$SCRIPT_SRC_DIR/txt2pdf" ]; then
    cp "$SCRIPT_SRC_DIR/txt2pdf" "$TARGET_BIN"
else
    RAW_URL="https://raw.githubusercontent.com/jonathank55/txt2pdf/main/txt2pdf"
    echo -e "${BLUE}==>${NC} Lade txt2pdf herunter..."
    curl -fsSL "$RAW_URL" -o "$TARGET_BIN" || {
        echo -e "${RED}Fehler:${NC} Download von txt2pdf fehlgeschlagen."
        exit 1
    }
fi

chmod +x "$TARGET_BIN"

# 7. PATH-Prüfung
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    SHELL_PROFILE="$HOME/.zshrc"
    if [ -f "$HOME/.bashrc" ] && [ "$SHELL" = "*/bash" ]; then
        SHELL_PROFILE="$HOME/.bashrc"
    fi
    echo "export PATH=\"$INSTALL_DIR:\$PATH\"" >> "$SHELL_PROFILE"
    echo -e "${BLUE}==>${NC} $INSTALL_DIR wurde zu $SHELL_PROFILE hinzugefügt."
fi

echo -e "${GREEN}==>${NC} txt2pdf wurde erfolgreich nach $TARGET_BIN installiert."
echo -e "${GREEN}==>${NC} Aufruf im Terminal: txt2pdf -h"
