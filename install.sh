#!/usr/bin/env bash
set -euo pipefail

BLAU='\033[0;34m'
GRUEN='\033[0;32m'
ROT='\033[0;31m'
OHNE='\033[0m'

REPO_URL="https://github.com/jonathank55/txt2pdf.git"
DATEN_BASIS="${XDG_DATA_HOME:-$HOME/.local/share}"
ZIEL_ORDNER="$DATEN_BASIS/txt2pdf"
BIN_ORDNER="$HOME/.local/bin"

echo -e "${BLAU}==>${OHNE} Installation von txt2pdf wird gestartet..."

# 1. Python 3 prüfen
if ! command -v python3 &>/dev/null; then
    echo -e "${ROT}Fehler:${OHNE} Python 3 wurde nicht gefunden. Bitte Python 3 zuerst installieren."
    exit 1
fi

# 2. Typst prüfen und bei Bedarf über Homebrew vorschlagen/installieren
if ! command -v typst &>/dev/null; then
    echo -e "${BLAU}==>${OHNE} Typst wurde nicht gefunden."
    if command -v brew &>/dev/null; then
        echo -e "${BLAU}==>${OHNE} Installiere Typst über Homebrew..."
        brew install typst
    else
        echo -e "${ROT}Hinweis:${OHNE} Bitte Typst manuell installieren: https://github.com/typst/typst"
    fi
fi

# 3. Programmordner einrichten (direkt aus lokalem Klon oder über GitHub)
SCRIPT_QUELLE=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    SCRIPT_QUELLE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

mkdir -p "$DATEN_BASIS" "$BIN_ORDNER"

if [ -n "$SCRIPT_QUELLE" ] && [ -f "$SCRIPT_QUELLE/txt2pdf" ] && [ -d "$SCRIPT_QUELLE/module" ]; then
    if [ "$SCRIPT_QUELLE" != "$ZIEL_ORDNER" ]; then
        echo -e "${BLAU}==>${OHNE} Kopiere Programmdateien nach $ZIEL_ORDNER..."
        rm -rf "$ZIEL_ORDNER"
        mkdir -p "$ZIEL_ORDNER"
        cp -a "$SCRIPT_QUELLE"/. "$ZIEL_ORDNER"/
    fi
else
    if ! command -v git &>/dev/null; then
        echo -e "${ROT}Fehler:${OHNE} git wird für die Installation aus dem Netz benötigt."
        exit 1
    fi
    if [ -d "$ZIEL_ORDNER/.git" ]; then
        echo -e "${BLAU}==>${OHNE} Aktualisiere bestehenden Stand in $ZIEL_ORDNER..."
        git -C "$ZIEL_ORDNER" pull --ff-only
    else
        echo -e "${BLAU}==>${OHNE} Klone Repository nach $ZIEL_ORDNER..."
        rm -rf "$ZIEL_ORDNER"
        git clone "$REPO_URL" "$ZIEL_ORDNER"
    fi
fi

chmod +x "$ZIEL_ORDNER/txt2pdf"

# 4. Verknüpfung im Suchpfad anlegen (Symlink auf Hauptskript, damit module/ & Schriftarten/ gefunden werden)
ZIEL_BIN="$BIN_ORDNER/txt2pdf"
ln -sf "$ZIEL_ORDNER/txt2pdf" "$ZIEL_BIN"

# 5. Fehlende Schriftarten bei Bedarf nachladen
if [ ! -d "$ZIEL_ORDNER/Schriftarten" ] || [ -z "$(ls -A "$ZIEL_ORDNER/Schriftarten" 2>/dev/null)" ]; then
    echo -e "${BLAU}==>${OHNE} Lade fehlende quelloffene Schriftarten nach $ZIEL_ORDNER/Schriftarten..."
    python3 "$ZIEL_ORDNER/txt2pdf" --schriften-laden
fi

# 6. Optionale DeepL-Bibliothek für Übersetzungen prüfen
if ! python3 -c "import deepl" &>/dev/null; then
    echo -e "${BLAU}==>${OHNE} Optional: Für Übersetzungen via -l/--sprache bitte 'pip install deepl' installieren."
fi

# 7. PATH-Hinweis falls ~/.local/bin fehlt
if [[ ":$PATH:" != *":$BIN_ORDNER:"* ]]; then
    echo -e "${BLAU}Hinweis:${OHNE} $BIN_ORDNER ist aktuell nicht im PATH. Bitte z. B. in ~/.bashrc oder ~/.zshrc ergänzen:"
    echo "  export PATH=\"$BIN_ORDNER:\$PATH\""
fi

echo -e "${GRUEN}==>${OHNE} txt2pdf wurde erfolgreich eingerichtet ($ZIEL_BIN -> $ZIEL_ORDNER/txt2pdf)."
echo -e "${GRUEN}==>${OHNE} Hilfe anzeigen: txt2pdf -h"
