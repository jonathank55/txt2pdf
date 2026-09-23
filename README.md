# txt2pdf

Ein eigenständiges Werkzeug zur typografischen Umwandlung von Text-, Markdown- und RTF/RTFD-Dateien in DIN-A4- und US-Letter-PDFs via Typst.

## Installation

### Einzeiler via Terminal (Internet-Installation)

```bash
curl -fsSL https://raw.githubusercontent.com/jonathank55/txt2pdf/main/install.sh | bash
```

### Manuelle Installation

1. Repository klonen:
   ```bash
   git clone https://github.com/jonathank55/txt2pdf.git
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
- DeepL Python-Bibliothek (`pip install deepl`, wird von `install.sh` automatisch eingerichtet)
- Schriftarten: Times New Roman, PT Serif, Optima, Didot, Cochin, Big Caslon, Baskerville, Roboto, Monaco (fehlende Kernschriften werden automatisch von `install.sh` oder `txt2pdf --install-fonts` installiert)

## Verwendung

```bash
txt2pdf DATEI [OPTIONEN]
```

### Optionen

- `-f FORMAT`  : Format-Vorgabe (`br2` für 2-Spalten-Bericht mit Optima [Standard], `br1` für 1-Spalten-Bericht mit PT Serif, `atk1` für 3-Spalten-Artikel mit Cochin ohne Trennlinie, `atk2` für 3-Spalten-Artikel mit PT Serif und Trennlinie, `apa` für 7. Edition APA-Bericht).
- `-z SCHRIFT` : Schriftart wählen (`Times New Roman`, `PT Serif`, `Optima`, `Didot`, `Cochin`, `Big Caslon`, `Baskerville`, `Roboto`, `Monaco`).
- `-s GRÖßE`   : Fließtext-Größe (`6pt` bis `12pt`).
- `-i BILD`    : Abbildung einbinden (Syntax `##Pfad/zur/Datei` direkt im Textdokument verwenden).
- `-a AUTOR`   : Autor manuell überschreiben (wird kursiv in Schwarz mit vergrößertem typografischem Abstand gerendert).
- `-t TITEL`   : Titel manuell überschreiben (Hauptüberschriften sind verbindlich 10pt bei `atk1` bzw. 6pt bei sonstigen Profilen größer als der Text).
- `-d DATUM`   : Datum manuell überschreiben.
- `-l SPRACHE` : Automatische Übersetzung via DeepL in die angegebene Zielsprache (`en`, `de`, etc.) vor dem Rendern.
- `-o AUSGABE` : Zieldateipfad für das PDF festlegen.
- `--install-fonts` : Überprüft und installiert fehlende Kernschriftarten automatisch.
- `-h`         : Hilfe anzeigen.
