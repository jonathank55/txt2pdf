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
- Schriftarten: Garamond (EB Garamond, Cormorant Garamond), Times New Roman, PT Serif, Optima, Didot, Cochin, Big Caslon, Baskerville, Roboto, Monaco (fehlende Kernschriften werden automatisch von `install.sh` oder `txt2pdf --install-fonts` installiert)

## Verwendung

```bash
txt2pdf DATEI [OPTIONEN]
```

### Optionen

- `-f FORMAT`  : Format-Vorgabe (`atk` für 3-Spalten-Artikel mit Garamond 10pt Fließtext, zentriertem dynamisch einzeiligem Didot-Titel und Trennlinie [Standard], `br2` für 2-Spalten-Bericht mit PT Serif, `br1` für 1-Spalten-Bericht mit PT Serif, `apa` für 7. Edition APA-Bericht).
- `-z SCHRIFT` : Schriftart wählen (`Garamond`, `Times New Roman`, `PT Serif`, `Optima`, `Didot`, `Cochin`, `Big Caslon`, `Baskerville`, `Roboto`, `Monaco`).
- `-s GRÖßE`   : Fließtext-Größe (`6pt` bis `12pt`, Standard: 10pt bei `atk`, 12pt bei `br1`/`br2`/`apa`).
- `-r RÄNDER`  : Ränder (`k` für klein: 10mm x, 12mm y [Standard bei `atk`]; `m` für mittel: 16mm x, 18mm y; `g` für groß: 22mm x, 24mm y; gilt für alle Formate außer `apa`).
- `-i BILD`    : Abbildung einbinden (Syntax `##Pfad/zur/Datei` direkt im Textdokument verwenden).
- `-a AUTOR`   : Autor manuell überschreiben (bei `atk` in Didot aufrecht gerendert, bei anderen Profilen kursiv).
- `-t TITEL`   : Titel manuell überschreiben (Hauptüberschrift bei `atk` dynamisch einzeilig in Didot skaliert, bei sonstigen Berichts-Profilen 6pt größer als der Text).
- `-d DATUM`   : Datum manuell überschreiben.
- `-l SPRACHE` : Automatische Übersetzung via DeepL in die angegebene Zielsprache (`en`, `de`, etc.) vor dem Rendern.
- `-o AUSGABE` : Zieldateipfad für das PDF festlegen.
- `--install-fonts` : Überprüft und installiert fehlende Kernschriftarten automatisch.
- `-h`         : Hilfe anzeigen.
