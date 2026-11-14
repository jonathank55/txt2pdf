# -*- coding: utf-8 -*-
"""Umfassende Testsuite für alle Module von txt2pdf."""

import contextlib
import io
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

# Stellt sicher, dass das Paket über den Programmordner importiert werden kann.
PROGRAMM_ORDNER = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if PROGRAMM_ORDNER not in sys.path:
    sys.path.insert(0, PROGRAMM_ORDNER)

from module.befehlszeile import (
    argumente_normalisieren,
    datei_umwandeln,
    hauptprogramm,
)
from module.dokument_bauer import apa_typst_erzeugen, standard_typst_erzeugen
from module.konfiguration import FORMAT_PROFILE, PAKETE_ORDNER, SCHRIFTARTEN_ORDNER
from module.markdown_typst import (
    bildpfad_aufloesen,
    inhalt_zu_typst,
    textkoerper_zu_typst,
)
from module.rtf_leser import rtf_zu_typst
from module.schriftarten import SCHRIFTARTEN_KATALOG
from module.textanalyse import (
    isbns_extrahieren,
    ist_apa_zitat,
    ist_autorenname,
    ist_einzelner_satz,
    sprachcode_fuer_typst,
    sprache_aus_dateiname,
    sprache_erkennen,
    titel_und_autor_aus_dateiname,
    titel_und_autor_bereinigen,
)
from module.typst_ausfuehrung import typst_kompilieren


def _gueltiges_test_png_schreiben(zielpfad: str) -> None:
    """Erzeugt eine gültige 2x2-PNG-Bilddatei ohne externe Abhängigkeiten."""

    def _chunk(typ: bytes, daten: bytes) -> bytes:
        return (
            struct.pack(">I", len(daten))
            + typ
            + daten
            + struct.pack(">I", zlib.crc32(typ + daten) & 0xFFFFFFFF)
        )

    signatur = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
    rohzeilen = b"\x00\xff\x00\x00\x00\xff\x00\x00\x00\x00\xff\x00\x00\xff"
    idat = _chunk(b"IDAT", zlib.compress(rohzeilen))
    iend = _chunk(b"IEND", b"")
    with open(zielpfad, "wb") as f:
        f.write(signatur + ihdr + idat + iend)


class TestBefehlszeile(unittest.TestCase):
    """Prüft die Argument-Normalisierung, Hilfeausgabe und Schriftenübersicht."""

    def test_argumente_normalisieren_mehrwort_schrift_und_dateipfad(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = os.path.join(tmp, "Mein Aufsatz (EN).txt")
            with open(datei, "w", encoding="utf-8") as f:
                f.write("Inhalt")
            args = argumente_normalisieren(["-z", "Open", "Sans", "--format=br2", datei])
            self.assertEqual(args, ["-z", "Open Sans", "--format", "br2", datei])

    def test_argumente_normalisieren_unquotierte_woerter(self):
        args = argumente_normalisieren(["-f", "atk1", "Langer", "Dateiname.txt"])
        self.assertEqual(args, ["-f", "atk1", "Langer Dateiname.txt"])

    def test_hilfe_und_schriftarten_ausgabe(self):
        puffer_hilfe = io.StringIO()
        with contextlib.redirect_stdout(puffer_hilfe):
            code = hauptprogramm(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("Verwendung: txt2pdf", puffer_hilfe.getvalue())
        self.assertIn("Formate (-f):", puffer_hilfe.getvalue())

        puffer_schriften = io.StringIO()
        with contextlib.redirect_stdout(puffer_schriften):
            code_s = hauptprogramm(["--schriftarten"])
        self.assertEqual(code_s, 0)
        self.assertIn("Faustina", puffer_schriften.getvalue())
        self.assertIn("Tinos", puffer_schriften.getvalue())


class TestTextanalyse(unittest.TestCase):
    """Prüft Titel-/Autorenerkennung, Überschriften-Heuristik, ISBNs und APA-Erkennung."""

    def test_dateiname_mit_sprachzusatz_en(self):
        titel, autor = titel_und_autor_aus_dateiname(
            "Career Event Essay - Jonathan Klatchko (EN)"
        )
        self.assertEqual(titel, "Career Event Essay")
        self.assertEqual(autor, "Jonathan Klatchko")

    def test_dateiname_mit_langversion_und_autor_am_anfang(self):
        titel, autor = titel_und_autor_aus_dateiname(
            "Max Mustermann - Künstliche Intelligenz im Alltag - Langversion"
        )
        self.assertEqual(autor, "Max Mustermann")
        self.assertEqual(titel, "Künstliche Intelligenz im Alltag")

    def test_titel_und_autor_bereinigen_entfernt_vertauschung_und_doppelung(self):
        titel, autor = titel_und_autor_bereinigen(
            "Jonathan Klatchko", "Career Event Essay (EN)"
        )
        self.assertEqual(titel, "Career Event Essay")
        self.assertEqual(autor, "Jonathan Klatchko")

        titel2, autor2 = titel_und_autor_bereinigen(
            "Aufsatz: Finanzmärkte - Max Mustermann", "Max Mustermann"
        )
        self.assertEqual(titel2, "Finanzmärkte")
        self.assertEqual(autor2, "Max Mustermann")

    def test_ist_autorenname_faelle(self):
        self.assertTrue(ist_autorenname("Jonathan Klatchko"))
        self.assertTrue(ist_autorenname("von Anna-Lena Meyer"))
        self.assertFalse(ist_autorenname("EN"))
        self.assertFalse(ist_autorenname("EINLEITUNG"))
        self.assertFalse(ist_autorenname("Dies ist ein ganzer Satz."))

    def test_ist_einzelner_satz(self):
        self.assertTrue(ist_einzelner_satz("Dies ist ein kurzer Satz."))
        self.assertTrue(ist_einzelner_satz("Siehe z. B. Abschnitt 2."))
        self.assertFalse(ist_einzelner_satz("Erster Satz. Zweiter Satz."))

    def test_isbn_und_apa_zitat(self):
        gefundene = isbns_extrahieren("Quelle: ISBN 978-3-16-148410-0 und 0-306-40615-2.")
        self.assertIn("9783161484100", gefundene)
        self.assertIn("0306406152", gefundene)
        self.assertTrue(
            ist_apa_zitat(
                "Müller, A. (2023). Klimawandel in Europa. https://example.org/studie"
            )
        )
        self.assertFalse(ist_apa_zitat("Ein normaler Satz ohne Quellenangabe."))

    def test_sprache_erkennen_kurze_texte_dateiname_und_apa(self):
        self.assertEqual(
            sprache_erkennen("The quick report is for all teams and projects."),
            "en",
        )
        self.assertEqual(
            sprache_erkennen("El informe para los estudiantes sobre una nueva obra."),
            "es",
        )
        self.assertEqual(
            sprache_erkennen("Le rapport pour les équipes et une analyse claire."),
            "fr",
        )
        # Auch bei englischer APA-Voreinstellung muss deutscher Text erkannt werden.
        self.assertEqual(
            sprache_erkennen(
                "Dieser kurze Absatz zeigt die Entwicklung in der Praxis.",
                vorgegeben="en",
            ),
            "de",
        )
        self.assertEqual(sprache_aus_dateiname("Aufsatz - Autor (EN).txt"), "en")
        self.assertEqual(sprache_aus_dateiname("Bericht [FR].rtf"), "fr")
        self.assertEqual(
            sprache_erkennen(
                "Text 123",
                vorgegeben="de",
                dateiname_hinweis="Aufsatz (EN).txt",
            ),
            "en",
        )
        self.assertEqual(sprache_erkennen("Text 123", vorgegeben="es"), "es")
        self.assertEqual(sprachcode_fuer_typst("EN-US"), "en")
        self.assertEqual(sprachcode_fuer_typst("EN-GB"), "en")
        self.assertEqual(sprachcode_fuer_typst("PT-BR"), "pt")
        self.assertEqual(sprachcode_fuer_typst("deu"), "de")
        self.assertEqual(sprachcode_fuer_typst(None, standard="de"), "de")


class TestMarkdownUndTextkoerper(unittest.TestCase):
    """Prüft Markdown-Übersetzung, Bildauflösung und Regressionen im Fließtext."""

    def test_inhalt_zu_typst_sonderzeichen_und_links(self):
        ausgabe = inhalt_zu_typst(
            'Kosten #1 [A] @2 $3 & **Fett** _Kursiv_ `code("x")` [Klick](https://example.org/a"b).'
        )
        self.assertIn(r"\#", ausgabe)
        self.assertIn(r"\[", ausgabe)
        self.assertIn("#strong[Fett]", ausgabe)
        self.assertIn("#emph[Kursiv]", ausgabe)
        self.assertIn('#link("https://example.org/a\\"b")[Klick]', ausgabe)

    def test_bildpfad_aufloesen_vorhanden_und_fehlend(self):
        with tempfile.TemporaryDirectory() as tmp:
            bilder_ordner = os.path.join(tmp, "Bilder")
            os.makedirs(bilder_ordner, exist_ok=True)
            echtes_bild = os.path.join(bilder_ordner, "beispiel.png")
            _gueltiges_test_png_schreiben(echtes_bild)

            aufgeloest = bildpfad_aufloesen(
                "/Users/alt/Documents/beispiel.png", dokument_ordner=tmp
            )
            self.assertEqual(aufgeloest, os.path.abspath(echtes_bild))
            self.assertIsNone(
                bildpfad_aufloesen("/Users/alt/Documents/nicht_da.jpg", dokument_ordner=tmp)
            )

    def test_url_im_fliesstext_verschluckt_keinen_nachfolgenden_text(self):
        zeilen = [
            "# Überschrift Eins",
            "",
            "Erster Absatz vor der Quelle.",
            "",
            "https://example.org/bericht",
            "",
            "Zweiter Absatz nach der URL muss vollständig erhalten bleiben.",
            "",
            "| Spalte A | Spalte B |",
            "| :--- | ---: |",
            "| Wert 1 | 42 |",
            "",
            "Dritter Absatz nach der Tabelle.",
        ]
        typst_body, urls, bib_eintraege, _, hat_einzuege = textkoerper_zu_typst(
            zeilen, fmt="atk2"
        )
        self.assertIn("Zweiter Absatz nach der URL muss vollständig erhalten bleiben.", typst_body)
        self.assertIn("Dritter Absatz nach der Tabelle.", typst_body)
        self.assertIn("#table(", typst_body)
        self.assertIn("https://example.org/bericht", urls)
        self.assertEqual(bib_eintraege, ["https://example.org/bericht"])
        self.assertFalse(hat_einzuege)

    def test_nummerierte_listen_ohne_doppelte_nummerierung(self):
        zeilen = [
            "1. Erster Listenpunkt mit mehreren Sätzen. Zweiter Satz.",
            "2. Zweiter Listenpunkt mit mehreren Sätzen. Zweiter Satz.",
            "3) Dritter Listenpunkt mit Klammer.",
            "",
            "- Erster Stichpunkt",
            "* Zweiter Stichpunkt",
        ]
        typst_body, _, _, _, _ = textkoerper_zu_typst(zeilen, fmt="atk2")
        self.assertIn("+ Erster Listenpunkt", typst_body)
        self.assertIn("+ Zweiter Listenpunkt", typst_body)
        self.assertIn("+ Dritter Listenpunkt", typst_body)
        self.assertNotIn("+ 1.", typst_body)
        self.assertNotIn("+ 2.", typst_body)
        self.assertNotIn("+ 3)", typst_body)
        self.assertIn("- Erster Stichpunkt", typst_body)
        self.assertIn("- Zweiter Stichpunkt", typst_body)
        self.assertNotIn("- - ", typst_body)
        self.assertNotIn("- * ", typst_body)


class TestRtfLeser(unittest.TestCase):
    """Prüft die Konvertierung von RTF-Dokumenten in reinem Python."""

    def test_rtf_mit_umlauten_auszeichnungen_und_tabelle(self):
        rtf_quelltext = (
            r"{\rtf1\ansi\ansicpg1252\deff0"
            r"{\fonttbl{\f0\fnil\fcharset0 Helvetica;}}"
            r"\pard\qc\b Dokumenttitel mit \'dcmlauten\b0\par"
            r"\pard\ql Erster Absatz mit \i Kursiv\i0 , \ul Unterstrichen\ulnone  und \'e4\'f6\'fc\'df.\par"
            r"\trowd\cellx2000\cellx4000\pard\intbl Kopf A\cell Kopf B\cell\row"
            r"\trowd\cellx2000\cellx4000\pard\intbl Wert 1\cell Wert 2\cell\row"
            r"}"
        )
        with tempfile.TemporaryDirectory() as tmp:
            rtf_pfad = os.path.join(tmp, "test.rtf")
            with open(rtf_pfad, "wb") as f:
                f.write(rtf_quelltext.encode("latin1"))

            inhalt, urls, titel, autor, datum, bib, _, _ = rtf_zu_typst(
                rtf_pfad,
                erwarteter_titel="Dokumenttitel mit Ümlauten",
                erwarteter_autor="Max Mustermann",
                titel_schrift='("Faustina", "PT Serif")',
                fmt="atk2",
            )
            self.assertIn("Kursiv", inhalt)
            self.assertIn("#emph[Kursiv]", inhalt)
            self.assertIn("#underline[Unterstrichen]", inhalt)
            self.assertIn("äöüß", inhalt)
            self.assertIn("#table(", inhalt)
            self.assertEqual(urls, [])
            self.assertEqual(bib, [])

            pdf_pfad = os.path.join(tmp, "test.pdf")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                ok = datei_umwandeln(eingabepfad=rtf_pfad, ausgabepfad=pdf_pfad)
            self.assertTrue(ok)
            self.assertTrue(os.path.isfile(pdf_pfad))


class TestSchriftartenUndOfflineTypst(unittest.TestCase):
    """Prüft alle lokal hinterlegten Schriftarten und die Offline-Kompilierung aller Formate."""

    def test_alle_schriftarten_physisch_vorhanden(self):
        self.assertTrue(os.path.isdir(SCHRIFTARTEN_ORDNER))
        self.assertTrue(os.path.isdir(PAKETE_ORDNER))
        for schluessel, eintrag in SCHRIFTARTEN_KATALOG.items():
            unterordner, _, dateien = eintrag["quelle"]  # type: ignore[misc]
            for datei in dateien:
                pfad = os.path.join(SCHRIFTARTEN_ORDNER, unterordner, datei)
                self.assertTrue(
                    os.path.isfile(pfad),
                    f"Schriftdatei für '{schluessel}' fehlt: {pfad}",
                )

    def test_alle_sechs_formate_kompilieren_offline_mit_bild(self):
        text = (
            "Career Event Essay\n"
            "Jonathan Klatchko\n"
            "14. November 2026\n\n"
            "Erster Absatz beginnt mit einem echten Buchstaben, damit das Initial sauber funktioniert. "
            "Dieser Satz enthält **Fettdruck**, _Kursivschrift_ und ein echtes Leerzeichen.\n\n"
            "Zwischenüberschrift\n\n"
            "Zweiter Absatz mit ausreichend Fließtext für Spaltensatz, Silbentrennung und Randabstände. "
            "Außerdem prüfen wir eine eingebundene Abbildung und eine saubere Aufzählung:\n\n"
            "- Punkt eins\n"
            "- Punkt zwei\n\n"
            "## beispiel.png\n\n"
            "## /nicht/vorhanden/alt_macos_bild.jpg\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            bild_pfad = os.path.join(tmp, "beispiel.png")
            _gueltiges_test_png_schreiben(bild_pfad)

            txt_pfad = os.path.join(tmp, "Aufsatz - Jonathan Klatchko (EN).txt")
            with open(txt_pfad, "w", encoding="utf-8") as f:
                f.write(text)

            alter_cache = os.environ.get("TYPST_PACKAGE_CACHE_PATH")
            leerer_cache = os.path.join(tmp, "leerer_paketcache")
            os.makedirs(leerer_cache, exist_ok=True)
            os.environ["TYPST_PACKAGE_CACHE_PATH"] = leerer_cache
            try:
                for fmt in FORMAT_PROFILE:
                    pdf_pfad = os.path.join(tmp, f"ausgabe_{fmt}.pdf")
                    puffer_out = io.StringIO()
                    puffer_err = io.StringIO()
                    with contextlib.redirect_stdout(puffer_out), contextlib.redirect_stderr(puffer_err):
                        ok = datei_umwandeln(
                            eingabepfad=txt_pfad,
                            ausgabepfad=pdf_pfad,
                            format_vorgabe=fmt,
                        )
                    self.assertTrue(
                        ok,
                        f"Format '{fmt}' fehlgeschlagen:\nSTDOUT:\n{puffer_out.getvalue()}\nSTDERR:\n{puffer_err.getvalue()}",
                    )
                    self.assertTrue(os.path.isfile(pdf_pfad))
                    self.assertGreater(os.path.getsize(pdf_pfad), 1000)
            finally:
                if alter_cache is None:
                    os.environ.pop("TYPST_PACKAGE_CACHE_PATH", None)
                else:
                    os.environ["TYPST_PACKAGE_CACHE_PATH"] = alter_cache

    def test_silbentrennung_einspaltig_flattersatz_rtf_und_apa(self):
        def _trennungen_im_pdf(pdf_pfad: str) -> int:
            ergebnis = subprocess.run(
                ["pdftotext", "-bbox", pdf_pfad, "-"],
                capture_output=True,
                text=True,
                check=True,
            )
            return len(
                re.findall(r"<word[^>]*>[^<]*\xad[^<]*</word>", ergebnis.stdout)
            )

        englischer_text = (
            "Internationalization Report\n\n"
            + " ".join(
                [
                    "Comprehensive organizational internationalization and telecommunications "
                    "infrastructure require extraordinary administrative responsibilities "
                    "across environmental transportation networks and scientific institutions."
                ]
                * 12
            )
        )
        deutscher_text = (
            "Verwaltungsvereinfachung in der Praxis\n\n"
            + " ".join(
                [
                    "Das Bundesverfassungsgericht betont das Verantwortungsbewusstsein "
                    "öffentlicher Arbeitsgemeinschaften bei Infrastrukturmaßnahmen und "
                    "der wissenschaftlichen Informationsverarbeitung in der Bundesrepublik."
                ]
                * 12
            )
        )

        with tempfile.TemporaryDirectory() as tmp:
            en_txt = os.path.join(tmp, "bericht_en.txt")
            de_txt = os.path.join(tmp, "bericht_de.txt")
            en_rtf = os.path.join(tmp, "bericht_en.rtf")
            with open(en_txt, "w", encoding="utf-8") as f:
                f.write(englischer_text)
            with open(de_txt, "w", encoding="utf-8") as f:
                f.write(deutscher_text)
            with open(en_rtf, "w", encoding="utf-8") as f:
                f.write(
                    "{\\rtf1\\ansi\\deff0\n"
                    "{\\fonttbl{\\f0 Times New Roman;}}\n"
                    "\\f0\\fs24 Internationalization Report\\par\n"
                    "Comprehensive organizational internationalization and "
                    "telecommunications infrastructure are essential for all teams "
                    "across environmental transportation networks.\\par\n}"
                )

            typst_en = standard_typst_erzeugen(en_txt, "br1")
            self.assertIn('lang: "en"', typst_en)
            self.assertIn("costs: (hyphenation: 50%, orphan: 150%, widow: 150%)", typst_en)

            typst_de = standard_typst_erzeugen(
                de_txt, "br1", initial_verwenden=True
            )
            self.assertIn('lang: "de"', typst_de)
            self.assertIn("justify: auto,", typst_de)

            typst_rtf = standard_typst_erzeugen(en_rtf, "br1")
            self.assertIn('lang: "en"', typst_rtf)

            de_apa_txt = os.path.join(tmp, "bericht_apa_de.txt")
            with open(de_apa_txt, "w", encoding="utf-8") as f:
                f.write(
                    deutscher_text
                    + "\n\nMüller, A. (2023). Klimawandel in Europa. "
                    "Zeitschrift für Praxis, 12(3), 45–60.\n"
                )
            typst_apa = apa_typst_erzeugen(de_apa_txt)
            self.assertIn('lang: "de"', typst_apa)
            self.assertIn("Literaturverzeichnis", typst_apa)

            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                typst_ziel = standard_typst_erzeugen(
                    de_txt, "br1", zielsprache="EN-US"
                )
            self.assertIn('lang: "en"', typst_ziel)
            self.assertNotIn('lang: "en-us"', typst_ziel)

            ziel_pdf = os.path.join(tmp, "ziel_en_us.pdf")
            puffer_out = io.StringIO()
            puffer_err = io.StringIO()
            with contextlib.redirect_stdout(puffer_out), contextlib.redirect_stderr(puffer_err):
                fehler = typst_kompilieren(typst_ziel, ziel_pdf)
            self.assertIsNone(
                fehler,
                f"Typst-Kompilierung mit EN-US fehlgeschlagen: {fehler}\n{puffer_out.getvalue()}\n{puffer_err.getvalue()}",
            )
            self.assertTrue(os.path.isfile(ziel_pdf))

            hat_pdftotext = shutil.which("pdftotext") is not None
            pruefungen = [
                (en_txt, "br1", False, "en_br1_blocksatz"),
                (en_txt, "br1", True, "en_br1_flattersatz"),
                (de_txt, "atk2", False, "de_atk2_blocksatz"),
                (de_txt, "br1", False, "de_br1_blocksatz"),
                (de_txt, "br1", True, "de_br1_flattersatz"),
            ]
            for eingabe, fmt, links, name in pruefungen:
                pdf_pfad = os.path.join(tmp, f"{name}.pdf")
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    ok = datei_umwandeln(
                        eingabepfad=eingabe,
                        ausgabepfad=pdf_pfad,
                        format_vorgabe=fmt,
                        linksbuendig=links,
                    )
                self.assertTrue(ok, f"Umwandlung für '{name}' fehlgeschlagen")
                if hat_pdftotext:
                    anzahl = _trennungen_im_pdf(pdf_pfad)
                    self.assertGreater(
                        anzahl,
                        0,
                        f"Keine Silbentrennung im erzeugten PDF '{name}' gefunden",
                    )


if __name__ == "__main__":
    unittest.main()
