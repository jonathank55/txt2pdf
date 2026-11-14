# txt2pdf

Plattformunabhängiges Kommandozeilenwerkzeug zur typografischen Umwandlung von Text-, Markdown- und RTF/RTFD-Dateien in druckfertige PDFs über Typst.

## Besonderheiten

- **Keine Systemschriften nötig**: 34 quelloffene Schriftfamilien liegen direkt im Verzeichnis `Schriftarten/` im Programmordner und werden automatisch über `--font-path` eingebunden (inklusive quellenoffener Alternativen für klassische Verlagsschriften wie *Times New Roman*, *Garamond*, *Bodoni*, *Didot*, *Futura*, *Gill Sans*, *Optima*, *Baskerville* oder *Helvetica Neue*).
- **Offline-fähig**: Das Typst-Paket `@preview/droplet:0.3.1` für Großinitiale liegt direkt unter `pakete/` bei.
- **Sauberer Modulaufbau**: Strikte Trennung in `module/` (Befehlszeile, Schriftarten, Textanalyse, Markdown/Typst, RTF-Leser, Zitate, Übersetzung, Dokumentaufbau und Typst-Ausführung) sowie eigene Unit- und Integrationsprüfungen unter `tests/`.
- **Robustes Bild- und Zitatverhalten**: Fehlende Bildpfade werden mit einem Hinweis übersprungen statt den Lauf abzubrechen; DOIs, ISBNs und URLs werden bei Bedarf parallel im APA-7-Format aufgelöst und zwischengespeichert.

## Installation

### Direkt über GitHub

```bash
curl -fsSL https://raw.githubusercontent.com/jonathank55/txt2pdf/main/install.sh | bash
```

### Manuell

```bash
git clone https://github.com/jonathank55/txt2pdf.git ~/.local/share/txt2pdf
cd ~/.local/share/txt2pdf
./install.sh
```

## Voraussetzungen

- Linux oder macOS mit Python 3
- Typst (`typst` im Suchpfad, z. B. über Paketverwaltung oder Homebrew)
- Optional für `-l`/`--sprache`: Python-Paket `deepl` (`pip install deepl`) samt `DEEPL_API_KEY`

## Verwendung

```bash
txt2pdf [OPTIONEN] DATEI
```

### Layoutformate (`-f`, `--format`)

| Kürzel | Beschreibung |
| :--- | :--- |
| `atk2` | 3 Spalten, Faustina, 9pt, ohne Titellinie (Standard) |
| `atk1` | 3 Spalten, EB Garamond, 10pt, mit Titellinie |
| `atk3` | 2 Spalten, Literata, 10pt, große Ränder |
| `br2` | 2 Spalten, PT Serif, 10pt, Berichtsformat |
| `br1` | 1 Spalte, Bitter, 10pt, Berichtsformat |
| `apa` | US-Letter, Tinos, 12pt, APA-7-Aufsatzformat |

### Wichtigste Optionen

- `-f, --format FORMAT`: Layoutformat wählen (Standard: `atk2`)
- `-z, --schrift NAME`: Schriftart wählen (vollständige Liste mit `--schriftarten`)
- `-s, --groesse PT`: Textgröße von `6pt` bis `12pt` (nicht bei `apa`)
- `-r, --raender WERT`: Ränder (`k`, `m`, `g`, `r` oder Maß wie `18mm`)
- `-o, --ausgabe PFAD`: Zielpfad der erzeugten PDF-Datei
- `--links`: Linksbündiger Flattersatz statt Blocksatz
- `-t, --titel TEXT`, `-a, --autor TEXT`, `-d, --datum TEXT`: Dokumentdaten überschreiben
- `-i, --bild PFAD`: Abbildung anhängen (alternativ `##Pfad/zur/Datei` im Dokument)
- `-l, --sprache CODE`: Optionale Übersetzung via DeepL (`en`, `de`, `es`, …)
- `--vorschau`: Erzeugtes PDF direkt nach der Erstellung öffnen
- `--schriftarten`: Übersicht aller mitgelieferten quelloffenen Schriftarten und Vorbilder
- `--schriften-laden`: Fehlende Schriftarten in `Schriftarten/` nachladen
- `-h, --help`: Kompakte Hilfe anzeigen

## Tests ausführen

```bash
python3 -m unittest discover -s ~/.local/share/txt2pdf/tests -v
```
