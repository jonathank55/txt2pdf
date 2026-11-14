# -*- coding: utf-8 -*-
"""Befehlszeilen-Schnittstelle, schlichtes Hilfemenü und Steuerungsablauf."""

import argparse
import os
import sys
from typing import List, Optional

from .ausgabe import drucke_erfolg, drucke_fehler
from .dokument_bauer import apa_typst_erzeugen, standard_typst_erzeugen
from .konfiguration import (
    FORMAT_ALIASE,
    STANDARD_FORMAT,
    TEXT_ENDUNGEN,
)
from .schriftarten import (
    ist_bekannte_mehrwort_schrift,
    schriftarten_uebersicht,
    schriften_herunterladen,
)
from .typst_ausfuehrung import typst_kompilieren, vorschau_oeffnen


HILFE_TEXT = """Verwendung: txt2pdf [OPTIONEN] DATEI

Wandelt Text-, Markdown- und RTF-Dateien (.txt, .md, .rtf, .rtfd) über Typst in PDFs um.

Formate (-f):
  atk2    3 Spalten, Faustina, 9pt, ohne Titellinie (Standard)
  atk1    3 Spalten, EB Garamond, 10pt, mit Titellinie
  atk3    2 Spalten, Literata, 10pt, große Ränder
  br2     2 Spalten, PT Serif, 10pt, Berichtsformat
  br1     1 Spalte, Bitter, 10pt, Berichtsformat
  apa     US-Letter, Tinos, 12pt, APA-7-Aufsatzformat

Wichtigste Optionen:
  -f, --format FORMAT     Layoutformat wählen (Standard: atk2)
  -z, --schrift NAME      Schriftart wählen (Übersicht mit --schriftarten)
  -s, --groesse PT        Textgröße von 6pt bis 12pt (nicht bei apa)
  -r, --raender WERT      Ränder: k (klein), m (mittel), g (groß), r (riesig) oder Maß
  -o, --ausgabe PFAD      Ausgabedatei (.pdf) festlegen
  --links                 Linksbündiger Flattersatz statt Blocksatz

Dokumentdaten & Extras:
  -t, --titel TEXT        Titel überschreiben
  -a, --autor TEXT        Autor überschreiben
  -d, --datum TEXT        Datum setzen
  -i, --bild PFAD         Abbildung anhängen (oder ##Pfad im Text nutzen)
  -l, --sprache CODE      Übersetzung via DeepL (z. B. en, de, es)
  --vorschau              Erzeugtes PDF nach dem Erstellen öffnen

Schriftarten & Hilfe:
  --schriftarten          Alle verfügbaren Schriftarten anzeigen
  --schriften-laden       Fehlende Schriftarten in 'Schriftarten/' nachladen
  -h, --help              Diese Hilfe anzeigen"""


_WERT_OPTIONEN = {
    "-f", "--format",
    "-z", "--schrift",
    "-s", "--groesse",
    "-r", "--raender",
    "-i", "--bild",
    "-a", "--autor",
    "-t", "--titel",
    "-d", "--datum",
    "-l", "--sprache",
    "-o", "--ausgabe",
}

_KURZE_WERT_OPTIONEN = {"-f", "--format", "-s", "--groesse", "-r", "--raender", "-l", "--sprache"}

_SCHALTER_OPTIONEN = {
    "-h", "--help",
    "--links", "--left",
    "--vorschau",
    "--schriftarten", "--fonts",
    "--schriften-laden", "--install-fonts",
}


def argumente_normalisieren(roh_argumente: List[str]) -> List[str]:
    """Löst mehrwortige unquotierte Werte (z. B. -z Open Sans oder Dateipfade mit Leerzeichen) sicher auf."""
    optionen_und_werte: List[str] = []
    positions_tokens: List[str] = []

    i = 0
    while i < len(roh_argumente):
        arg = roh_argumente[i]

        # --option=wert in ["--option", "wert"] aufteilen
        if arg.startswith("--") and "=" in arg:
            opt, wert = arg.split("=", 1)
            if opt in _WERT_OPTIONEN:
                optionen_und_werte.extend([opt, wert])
                i += 1
                continue

        if arg in _SCHALTER_OPTIONEN:
            optionen_und_werte.append(arg)
            i += 1
            continue

        if arg in _WERT_OPTIONEN:
            optionen_und_werte.append(arg)
            wert_tokens: List[str] = []
            i += 1
            while i < len(roh_argumente):
                naechstes = roh_argumente[i]
                if naechstes in _WERT_OPTIONEN or naechstes in _SCHALTER_OPTIONEN:
                    break
                if wert_tokens and (os.path.exists(naechstes) or naechstes.lower().endswith(TEXT_ENDUNGEN)):
                    break
                if wert_tokens:
                    rest = " ".join(roh_argumente[i:])
                    if os.path.exists(rest) and rest.lower().endswith(TEXT_ENDUNGEN):
                        break
                wert_tokens.append(naechstes)
                i += 1
                if arg in _KURZE_WERT_OPTIONEN:
                    break
                if arg in ("-z", "--schrift"):
                    zusammen = " ".join(wert_tokens)
                    if ist_bekannte_mehrwort_schrift(zusammen):
                        # Prüfe vorab, ob das nächste Wort noch zur Schriftart gehört (z. B. "Libre Caslon Text")
                        if i < len(roh_argumente) and ist_bekannte_mehrwort_schrift(f"{zusammen} {roh_argumente[i]}"):
                            continue
                        break
            if wert_tokens:
                optionen_und_werte.append(" ".join(wert_tokens))
            continue

        positions_tokens.append(arg)
        i += 1

    if len(positions_tokens) > 1:
        zusammen_pfad = " ".join(positions_tokens)
        positions_tokens = [zusammen_pfad]

    return optionen_und_werte + positions_tokens


def datei_umwandeln(
    eingabepfad: str,
    ausgabepfad: Optional[str] = None,
    titel: Optional[str] = None,
    autor: Optional[str] = None,
    datum: Optional[str] = None,
    schriftgroesse: Optional[str] = None,
    schrift: Optional[str] = None,
    bilder: Optional[List[str]] = None,
    format_vorgabe: str = STANDARD_FORMAT,
    zielsprache: Optional[str] = None,
    raender: Optional[str] = None,
    linksbuendig: bool = False,
    vorschau: bool = False,
) -> bool:
    """Führt die komplette Umwandlung einer Text-/RTF-Datei in ein PDF durch."""
    if not os.path.exists(eingabepfad):
        drucke_fehler(eingabepfad, "Die Quelldatei wurde nicht gefunden.")
        return False

    abs_eingabe = os.path.abspath(eingabepfad)
    basisname = os.path.splitext(os.path.basename(abs_eingabe))[0]
    abs_ausgabe = (
        os.path.join(os.path.dirname(abs_eingabe), f"{basisname}.pdf")
        if ausgabepfad is None
        else os.path.abspath(ausgabepfad)
    )

    fmt_roh = (format_vorgabe or STANDARD_FORMAT).lower().strip()
    if fmt_roh not in FORMAT_ALIASE:
        drucke_fehler(abs_eingabe, f"Unbekanntes Format '{format_vorgabe}'. Erlaubt: atk2, atk1, atk3, br2, br1, apa.")
        return False
    fmt = FORMAT_ALIASE[fmt_roh]

    try:
        if fmt == "apa":
            typst_quelltext = apa_typst_erzeugen(
                eingabepfad=abs_eingabe,
                titel=titel,
                autor=autor,
                datum=datum,
                bilder=bilder,
                schrift_arg=schrift,
                zielsprache=zielsprache,
            )
        else:
            typst_quelltext = standard_typst_erzeugen(
                eingabepfad=abs_eingabe,
                fmt=fmt,
                titel=titel,
                autor=autor,
                datum=datum,
                schriftgroesse=schriftgroesse,
                bilder=bilder,
                schrift_arg=schrift,
                zielsprache=zielsprache,
                raender=raender,
                linksbuendig=linksbuendig,
            )
    except Exception as fehler:
        drucke_fehler(abs_eingabe, "Fehler beim Verarbeiten der Quelldatei.", str(fehler))
        return False

    fehler_typst = typst_kompilieren(typst_quelltext, abs_ausgabe)
    if fehler_typst is not None:
        drucke_fehler(abs_eingabe, "Typst konnte das PDF nicht erzeugen.", fehler_typst)
        return False

    drucke_erfolg(
        quelldatei=abs_eingabe,
        ausgabedatei=abs_ausgabe,
        formatname=fmt,
        zielsprache=zielsprache,
    )
    if vorschau:
        vorschau_oeffnen(abs_ausgabe)
    return True


def _parser_erstellen() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="txt2pdf", add_help=False)
    parser.add_argument("-h", "--help", action="store_true", dest="hilfe")
    parser.add_argument("-f", "--format", dest="format_vorgabe", default=STANDARD_FORMAT)
    parser.add_argument("-z", "--schrift", dest="schrift", default=None)
    parser.add_argument("-s", "--groesse", dest="groesse", default=None)
    parser.add_argument("-r", "--raender", dest="raender", default=None)
    parser.add_argument("-i", "--bild", dest="bilder", action="append", default=[])
    parser.add_argument("-a", "--autor", dest="autor", default=None)
    parser.add_argument("-t", "--titel", dest="titel", default=None)
    parser.add_argument("-d", "--datum", dest="datum", default=None)
    parser.add_argument("-l", "--sprache", dest="zielsprache", default=None)
    parser.add_argument("-o", "--ausgabe", dest="ausgabe", default=None)
    parser.add_argument("--links", "--left", dest="linksbuendig", action="store_true", default=False)
    parser.add_argument("--vorschau", dest="vorschau", action="store_true", default=False)
    parser.add_argument("--schriftarten", "--fonts", dest="schriftarten_zeigen", action="store_true", default=False)
    parser.add_argument("--schriften-laden", "--install-fonts", dest="schriften_laden", action="store_true", default=False)
    parser.add_argument("eingabedatei", nargs="?", default=None)
    return parser


def hauptprogramm(argv: Optional[List[str]] = None) -> int:
    """Einstiegspunkt der Befehlszeile."""
    roh_args = sys.argv[1:] if argv is None else argv
    parser = _parser_erstellen()

    try:
        args = parser.parse_args(argumente_normalisieren(roh_args))
    except SystemExit:
        print(HILFE_TEXT, file=sys.stderr)
        return 2

    if args.hilfe:
        print(HILFE_TEXT)
        return 0

    if args.schriftarten_zeigen:
        print(schriftarten_uebersicht())
        return 0

    if args.schriften_laden:
        return 0 if schriften_herunterladen() else 1

    if not args.eingabedatei:
        print(HILFE_TEXT)
        return 1

    erfolg = datei_umwandeln(
        eingabepfad=args.eingabedatei,
        ausgabepfad=args.ausgabe,
        titel=args.titel,
        autor=args.autor,
        datum=args.datum,
        schriftgroesse=args.groesse,
        schrift=args.schrift,
        bilder=args.bilder,
        format_vorgabe=args.format_vorgabe,
        zielsprache=args.zielsprache,
        raender=args.raender,
        linksbuendig=args.linksbuendig,
        vorschau=args.vorschau,
    )
    return 0 if erfolg else 1
