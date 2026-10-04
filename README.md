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
- Schriftarten: Kefa III, Garamond (EB Garamond, Cormorant Garamond), Times New Roman, PT Serif, Optima, Didot, Cochin, Big Caslon, Baskerville, Bodoni, Playfair Display, Faustina, Canela Text, Roboto, Monaco, Bookerly, Amazon Ember (fehlende Kernschriften werden automatisch von `install.sh` oder `txt2pdf --install-fonts` installiert)

## Verwendung

```bash
txt2pdf DATEI [OPTIONEN]
```

### Optionen

- `-f FORMAT`  : Format-Vorgabe (`atk2` für Kindle-Format mit 3 Spalten, Faustina und Amazon Ember Autorenzeile [Standard], `atk1` für 3-Spalten-Artikel mit Didot-Titel [Ränder mittel], `atk3` für 2-Spalten-Artikel mit Bookerly 10pt, riesigen Rändern und Amazon Ember Überschriften/Autorenzeile, `br2` für 2-Spalten-Bericht mit Bookerly 10pt, `br1` für 1-Spalten-Bericht mit Kefa III 10pt, `apa` für 7. Edition APA-Bericht).
- `-z SCHRIFT` : Schriftart wählen (`Kefa III`, `Bookerly`, `Amazon Ember`, `Playfair Display`, `Bodoni`, `Garamond`, `Times New Roman`, `PT Serif`, `Optima`, `Didot`, `Cochin`, `Big Caslon`, `Baskerville`, `Faustina`, `Canela Text`, `Roboto`, `Monaco`).
- `-s GRÖßE`   : Fließtext-Größe (`6pt` bis `12pt`, Standard: 10pt bei `atk1`/`atk3`/`br1`/`br2`, 9pt bei `atk2`, 12pt bei `apa`).
- `-r RÄNDER`  : Ränder (`m` für mittel: 16mm x, 18mm y [Standard bei `atk1`/`atk2`]; `k` für klein: 10mm x, 12mm y; `g` für groß: 22mm x, 24mm y [Standard bei `br2`]; `r` für riesig: 34mm x, 36mm y [Standard bei `br1`/`atk3`]; gilt für alle Formate außer `apa`).
- `-i BILD`    : Abbildung einbinden (Syntax `##Pfad/zur/Datei` direkt im Textdokument verwenden).
- `-a AUTOR`   : Autor manuell überschreiben (bei `atk` mit vorangestelltem `VON` in Calibre/Helvetica Versalien, bei anderen Profilen kursiv).
- `-t TITEL`   : Titel manuell überschreiben (Hauptüberschrift bei `atk` dynamisch einzeilig in Didot skaliert, bei sonstigen Berichts-Profilen 6pt größer als der Text).
- `-d DATUM`   : Datum manuell überschreiben.
- `-l SPRACHE` : Automatische Übersetzung via DeepL in die angegebene Zielsprache (`en`, `de`, etc.) vor dem Rendern.
- `-o AUSGABE` : Zieldateipfad für das PDF festlegen.
- `--install-fonts` : Überprüft und installiert fehlende Kernschriftarten automatisch.
- `-h`         : Hilfe anzeigen.
