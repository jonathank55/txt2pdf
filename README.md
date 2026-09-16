# txt2pdf

Ein eigenständiges Werkzeug zur typografischen Umwandlung von Text-, Markdown- und RTF/RTFD-Dateien in DIN-A4- und US-Letter-PDFs via Typst.

## Installation

### Einzeiler via Terminal (Internet-Installation)

```bash
curl -fsSL https://raw.githubusercontent.com/jonathanklatchko/txt2pdf/main/install.sh | bash
```

### Manuelle Installation

1. Repository klonen:
   ```bash
   git clone https://github.com/jonathanklatchko/txt2pdf.git
   cd txt2pdf
   ```
2. Installationsskript ausführen:
   ```bash
   ./install.sh
   ```

## Voraussetzungen & Schriftarten

- macOS oder Linux
- Python 3 (standardmäßig vorinstalliert)
- Typst (`brew install typst`)
- Schriftart PT Serif (wird vom Installationsskript automatisch in den lokalen Schriftartenordner des Systems installiert; die Schriftdateien liegen im Unterordner `fonts/`)

## Verwendung

```bash
txt2pdf DATEI [OPTIONEN]
```

### Optionen

- `-f FORMAT` : Format-Vorgabe (`atk` für 3-Spalten-Artikel mit Initial, `br1` für 1-Spalten-Bericht, `br2` für 2-Spalten-Bericht, `apa` für 7. Edition APA-Bericht).
- `-s GRÖßE`  : Fließtext-Größe (`6pt` bis `12pt`).
- `-i BILD`   : Abbildung einbinden (Syntax `##Pfad/zur/Datei` direkt im Textdokument verwenden).
- `-a AUTOR`  : Autor manuell überschreiben.
- `-t TITEL`  : Titel manuell überschreiben.
- `-d DATUM`  : Datum manuell überschreiben.
- `-o AUSGABE`: Zieldateipfad für das PDF festlegen.
- `-h`        : Hilfe anzeigen.
