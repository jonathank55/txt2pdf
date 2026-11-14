# -*- coding: utf-8 -*-
"""Plattformunabhängiger RTF- und RTFD-Leser in reinem Python."""

import codecs
import os
import re
from typing import Dict, List, Optional, Tuple

from .ausgabe import drucke_warnung
from .konfiguration import BIBLIOGRAFIE_WOERTER_MUSTER
from .markdown_typst import (
    abbildung_typst,
    bildpfad_aufloesen,
    inhalt_zu_typst,
    initial_anwenden,
    typst_maskieren,
    typst_zeichenkette_maskieren,
    ueberschrift_typst_erzeugen,
    urls_aus_text_extrahieren,
)
from .schriftarten import (
    AUTOR_AKZENT_SCHRIFT,
    initial_schriftart_aufloesen,
)
from .textanalyse import ist_apa_zitat, ist_autorenname, titel_und_autor_bereinigen


_IGNORIERTE_ZIELE = {
    "fonttbl", "colortbl", "stylesheet", "info", "pict", "object",
    "header", "footer", "headerl", "headerr", "headerf",
    "footerl", "footerr", "footerf", "listtable", "listoverridetable",
    "revtbl", "rsidtbl", "generator", "xmlnstbl", "themedata",
    "colorschememapping", "latentstyles", "datastore", "mmathPr",
    "shppict", "nonshppict", "xe", "tc", "rxe", "bkmkstart", "bkmkend",
}


class _RtfDokumentLeser:
    """Parst RTF-Quelltext direkt in strukturierte Absätze samt Auszeichnungen."""

    def __init__(self, rtf_bytes: bytes, basis_ordner: str = "", bildunterschrift_groesse: str = "6pt"):
        self.text = rtf_bytes.decode("latin1")
        self.basis_ordner = basis_ordner
        self.bildunterschrift_groesse = bildunterschrift_groesse
        self.encoding = "cp1252"

        self.dok_titel = ""
        self.dok_autor = ""
        self.dok_datum = ""
        self.urls: List[str] = []
        self.absaetze: List[Dict[str, object]] = []

        self._zeilen_puffer: List[str] = []
        self._klartext_puffer: List[str] = []
        self._leer_zaehler = 0
        self._hat_leer = False

        self._tabelle_zeilen: List[List[str]] = []
        self._aktuelle_reihe: List[str] = []

    def _zustand_neu(self) -> Dict[str, object]:
        return {
            "fett": False,
            "kursiv": False,
            "unterstrichen": False,
            "durchgestrichen": False,
            "hoch": False,
            "tief": False,
            "ausrichtung": None,
            "einzug": False,
            "uc": 1,
            "ignoriert": False,
            "ziel": "",
            "in_tabelle": False,
            "link_ziel": None,
        }

    def _span_formatieren(self, rohtext: str, zustand: Dict[str, object]) -> str:
        if not rohtext:
            return ""
        esc = typst_maskieren(rohtext).replace("—", " – ").replace("---", "--")
        if zustand.get("link_ziel"):
            url_str = str(zustand["link_ziel"])
            if url_str not in self.urls:
                self.urls.append(url_str)
            esc = f'#link("{typst_zeichenkette_maskieren(url_str)}")[{esc}]'
        if zustand.get("hoch"):
            esc = f"#super[{esc}]"
        elif zustand.get("tief"):
            esc = f"#sub[{esc}]"
        if zustand.get("durchgestrichen"):
            esc = f"#strike[{esc}]"
        if zustand.get("unterstrichen"):
            esc = f"#underline[{esc}]"
        if zustand.get("kursiv"):
            esc = f"#emph[{esc}]"
        if zustand.get("fett"):
            esc = f"#strong[{esc}]"
        return esc

    def _absatz_abschliessen(self, zustand: Dict[str, object]) -> None:
        typst_inhalt = "".join(self._zeilen_puffer).strip()
        klartext = "".join(self._klartext_puffer).strip()
        self._zeilen_puffer = []
        self._klartext_puffer = []

        if klartext or "#image(" in typst_inhalt:
            self.absaetze.append({
                "typst": typst_inhalt,
                "plain": klartext or "[Abbildung]",
                "align": zustand.get("ausrichtung"),
                "heading": False,
                "has_indent": bool(zustand.get("einzug")),
                "has_blank_before": bool(self._leer_zaehler > 0 or self._hat_leer),
                "empty_paragraphs_before": self._leer_zaehler,
            })
            self._leer_zaehler = 0
            self._hat_leer = False
        else:
            self._hat_leer = True
            self._leer_zaehler += 1

    def _tabelle_leeren(self) -> None:
        if not self._tabelle_zeilen:
            return
        spalten = max(len(r) for r in self._tabelle_zeilen)
        if spalten <= 0:
            self._tabelle_zeilen = []
            return
        tbl = [f"\n#table(\n  columns: {spalten},\n  align: left,\n"]
        for reihe in self._tabelle_zeilen:
            gefuellt = list(reihe) + [""] * (spalten - len(reihe))
            for zelle in gefuellt[:spalten]:
                tbl.append(f"  [{zelle}],\n")
        tbl.append(")\n\n")
        self.absaetze.append({
            "typst": "".join(tbl),
            "plain": "Table",
            "align": None,
            "heading": False,
            "has_indent": False,
            "has_blank_before": bool(self._leer_zaehler > 0),
            "empty_paragraphs_before": self._leer_zaehler,
        })
        self._tabelle_zeilen = []
        self._leer_zaehler = 0
        self._hat_leer = False

    def _meta_info_auslesen(self) -> None:
        """Liest Titel und Autor aus einem möglichen \\info-Block vorab aus."""
        m_info = re.search(r"\{\\info\b", self.text)
        if not m_info:
            return
        start = m_info.start()
        tiefe = 0
        ende = start
        for idx in range(start, min(len(self.text), start + 16000)):
            c = self.text[idx]
            if c == "{":
                tiefe += 1
            elif c == "}":
                tiefe -= 1
                if tiefe == 0:
                    ende = idx + 1
                    break
        info_block = self.text[start:ende]
        m_titel = re.search(r"\{\\title\s+([^}]*)\}", info_block)
        m_autor = re.search(r"\{\\author\s+([^}]*)\}", info_block)
        if m_titel:
            self.dok_titel = m_titel.group(1).strip()
        if m_autor:
            self.dok_autor = m_autor.group(1).strip()

    def parsen(self) -> None:
        self._meta_info_auslesen()

        stapel: List[Tuple[Dict[str, object], int]] = []
        zustand = self._zustand_neu()
        ueberspringen = 0

        text = self.text
        n = len(text)
        i = 0

        # Vorab-Erkennung eingebetteter HYPERLINK-Felder via Gruppen-Tiefe
        feld_puffer: Optional[List[str]] = None
        feld_tiefe = -1
        in_fldinst = False
        fldinst_puffer: List[str] = []
        aktuelle_tiefe = 0

        def _text_hinzufuegen(rohtext: str) -> None:
            if not rohtext:
                return
            if in_fldinst:
                fldinst_puffer.append(rohtext)
                return
            if zustand.get("ignoriert"):
                if zustand.get("ziel") == "nextgraphic":
                    bild_name = rohtext.strip()
                    if bild_name:
                        aufgeloest = bildpfad_aufloesen(bild_name, dokument_ordner=self.basis_ordner)
                        if aufgeloest:
                            fig = abbildung_typst(aufgeloest, bildunterschrift_groesse=self.bildunterschrift_groesse)
                            self._zeilen_puffer.append(f"\n{fig}\n")
                            self._klartext_puffer.append("[Abbildung]")
                        else:
                            drucke_warnung(f"Eingebettetes RTFD-Bild nicht gefunden: {bild_name}")
                return
            self._klartext_puffer.append(rohtext)
            self._zeilen_puffer.append(self._span_formatieren(rohtext, zustand))

        while i < n:
            ch = text[i]

            if ch in ("\r", "\n"):
                i += 1
                continue

            if ch == "{":
                aktuelle_tiefe += 1
                stapel.append((dict(zustand), ueberspringen))
                i += 1
                continue

            if ch == "}":
                if in_fldinst and aktuelle_tiefe <= feld_tiefe + 1:
                    inst_str = "".join(fldinst_puffer)
                    m_url = re.search(r'HYPERLINK\s+"([^"]+)"', inst_str)
                    if m_url and stapel:
                        # Linkziel auf umgebende Feld-Gruppe setzen
                        zustand["link_ziel"] = m_url.group(1)
                    in_fldinst = False
                    fldinst_puffer = []
                if feld_tiefe == aktuelle_tiefe:
                    feld_tiefe = -1
                    feld_puffer = None
                if stapel:
                    alter_link = zustand.get("link_ziel")
                    zustand, ueberspringen = stapel.pop()
                    # Vererbe Link innerhalb desselben {\field ...} auf {\fldrslt ...}
                    if feld_tiefe != -1 and alter_link and not zustand.get("link_ziel"):
                        zustand["link_ziel"] = alter_link
                aktuelle_tiefe = max(0, aktuelle_tiefe - 1)
                i += 1
                continue

            if ch == "\\":
                i += 1
                if i >= n:
                    break
                naechstes = text[i]

                if naechstes in ("\\", "{", "}"):
                    if ueberspringen > 0:
                        ueberspringen -= 1
                    else:
                        _text_hinzufuegen(naechstes)
                    i += 1
                    continue

                if naechstes == "*":
                    if not zustand.get("ignoriert"):
                        zustand["ignoriert"] = True
                    i += 1
                    continue

                if naechstes == "~":
                    if ueberspringen > 0:
                        ueberspringen -= 1
                    else:
                        _text_hinzufuegen(" ")
                    i += 1
                    continue

                if naechstes in ("_", "-"):
                    if ueberspringen > 0:
                        ueberspringen -= 1
                    else:
                        _text_hinzufuegen("-")
                    i += 1
                    continue

                if naechstes == "'":
                    hex_teil = text[i + 1 : i + 3]
                    if len(hex_teil) == 2 and all(c in "0123456789abcdefABCDEF" for c in hex_teil):
                        i += 3
                        if ueberspringen > 0:
                            ueberspringen -= 1
                        else:
                            # Mehrere aufeinanderfolgende Hex-Bytes ggf. als Block dekodieren (UTF-8 / cp1252)
                            byte_liste = [int(hex_teil, 16)]
                            while i + 3 < n and text[i : i + 2] == "\\'":
                                nh = text[i + 2 : i + 4]
                                if len(nh) == 2 and all(c in "0123456789abcdefABCDEF" for c in nh):
                                    byte_liste.append(int(nh, 16))
                                    i += 4
                                else:
                                    break
                            try:
                                dekodiert = bytes(byte_liste).decode(self.encoding, errors="replace")
                            except Exception:
                                dekodiert = bytes(byte_liste).decode("cp1252", errors="replace")
                            _text_hinzufuegen(dekodiert)
                        continue

                # Steuerwort lesen
                m_cmd = re.match(r"([a-zA-Z]+)(-?\d+)? ?", text[i:])
                if m_cmd:
                    wort = m_cmd.group(1)
                    param_str = m_cmd.group(2)
                    param = int(param_str) if param_str is not None else None
                    i += len(m_cmd.group(0))

                    if wort == "u" and param is not None:
                        codepoint = param if param >= 0 else 65536 + param
                        try:
                            _text_hinzufuegen(chr(codepoint))
                        except Exception:
                            pass
                        ueberspringen = int(zustand.get("uc", 1))
                        continue

                    if wort == "uc" and param is not None:
                        zustand["uc"] = max(0, param)
                        continue

                    if wort == "ansicpg" and param is not None:
                        cp_name = f"cp{param}"
                        try:
                            codecs.lookup(cp_name)
                            self.encoding = cp_name
                        except LookupError:
                            pass
                        continue

                    if wort == "mac":
                        self.encoding = "mac_roman"
                        continue

                    if wort == "field":
                        feld_tiefe = aktuelle_tiefe
                        feld_puffer = []
                        continue

                    if wort == "fldinst":
                        in_fldinst = True
                        fldinst_puffer = []
                        zustand["ignoriert"] = False
                        continue

                    if wort == "fldrslt":
                        in_fldinst = False
                        zustand["ignoriert"] = False
                        continue

                    if wort == "NeXTGraphic":
                        zustand["ignoriert"] = True
                        zustand["ziel"] = "nextgraphic"
                        continue

                    if wort in _IGNORIERTE_ZIELE:
                        zustand["ignoriert"] = True
                        zustand["ziel"] = wort
                        continue

                    if zustand.get("ignoriert"):
                        continue

                    if wort == "b":
                        zustand["fett"] = (param != 0)
                    elif wort == "i":
                        zustand["kursiv"] = (param != 0)
                    elif wort == "ul":
                        zustand["unterstrichen"] = (param != 0)
                    elif wort == "ulnone":
                        zustand["unterstrichen"] = False
                    elif wort == "strike":
                        zustand["durchgestrichen"] = (param != 0)
                    elif wort == "super":
                        zustand["hoch"] = True
                        zustand["tief"] = False
                    elif wort == "sub":
                        zustand["tief"] = True
                        zustand["hoch"] = False
                    elif wort == "nosupersub":
                        zustand["hoch"] = False
                        zustand["tief"] = False
                    elif wort == "pard":
                        zustand["ausrichtung"] = None
                        zustand["einzug"] = False
                        zustand["in_tabelle"] = False
                    elif wort == "plain":
                        zustand["fett"] = False
                        zustand["kursiv"] = False
                        zustand["unterstrichen"] = False
                        zustand["durchgestrichen"] = False
                        zustand["hoch"] = False
                        zustand["tief"] = False
                    elif wort == "qc":
                        zustand["ausrichtung"] = "center"
                    elif wort == "qr":
                        zustand["ausrichtung"] = "right"
                    elif wort in ("ql", "qj"):
                        zustand["ausrichtung"] = None
                    elif wort == "fi" and param is not None and param > 100:
                        zustand["einzug"] = True
                    elif wort == "tab":
                        if not self._klartext_puffer:
                            zustand["einzug"] = True
                        else:
                            _text_hinzufuegen(" ")
                    elif wort == "emdash":
                        _text_hinzufuegen(" – ")
                    elif wort == "endash":
                        _text_hinzufuegen(" – ")
                    elif wort == "lquote":
                        _text_hinzufuegen("‘")
                    elif wort == "rquote":
                        _text_hinzufuegen("’")
                    elif wort == "ldblquote":
                        _text_hinzufuegen("“")
                    elif wort == "rdblquote":
                        _text_hinzufuegen("”")
                    elif wort == "bullet":
                        _text_hinzufuegen("• ")
                    elif wort == "line":
                        self._zeilen_puffer.append(" #linebreak() ")
                        self._klartext_puffer.append(" ")
                    elif wort == "trowd":
                        zustand["in_tabelle"] = True
                        self._aktuelle_reihe = []
                    elif wort == "intbl":
                        zustand["in_tabelle"] = True
                    elif wort == "cell":
                        zelle_text = "".join(self._zeilen_puffer).strip()
                        self._aktuelle_reihe.append(zelle_text)
                        self._zeilen_puffer = []
                        self._klartext_puffer = []
                    elif wort == "row":
                        if self._aktuelle_reihe:
                            self._tabelle_zeilen.append(self._aktuelle_reihe)
                        self._aktuelle_reihe = []
                    elif wort == "par":
                        if zustand.get("in_tabelle"):
                            self._zeilen_puffer.append(" ")
                        else:
                            self._tabelle_leeren()
                            self._absatz_abschliessen(zustand)
                    continue

                i += 1
                continue

            # Normaler Zeichentext (effizient am Stück sammeln)
            start_txt = i
            while i < n and text[i] not in ("\\", "{", "}", "\r", "\n"):
                i += 1
            roh_stück = text[start_txt:i]
            if ueberspringen > 0:
                if len(roh_stück) <= ueberspringen:
                    ueberspringen -= len(roh_stück)
                    continue
                roh_stück = roh_stück[ueberspringen:]
                ueberspringen = 0
            _text_hinzufuegen(roh_stück)

        self._tabelle_leeren()
        self._absatz_abschliessen(zustand)


def rtf_zu_typst(
    rtf_pfad: str,
    erwarteter_titel: Optional[str] = None,
    erwarteter_autor: Optional[str] = None,
    erwartetes_datum: Optional[str] = None,
    bilder: Optional[List[str]] = None,
    bildunterschrift_groesse: str = "6pt",
    titelgroesse: str = "14pt",
    initial_verwenden: bool = True,
    titel_schrift: str = '("PT Serif", "EB Garamond", "Tinos")',
    fmt: str = "br2",
    zeilenabstand: str = "0.55em",
    ueberschrift_schrift: Optional[str] = None,
) -> Tuple[str, List[str], str, str, Optional[str], List[str], Optional[str], bool]:
    """Liest eine RTF- oder RTFD-Datei plattformunabhängig ein und erzeugt Typst-Abschnitte."""
    if os.path.isdir(rtf_pfad):
        basis_ordner = os.path.abspath(rtf_pfad)
        rtf_datei = os.path.join(basis_ordner, "TXT.rtf")
        if not os.path.exists(rtf_datei):
            kandidaten = [f for f in os.listdir(basis_ordner) if f.lower().endswith(".rtf")]
            if not kandidaten:
                raise FileNotFoundError(f"Keine RTF-Datei im RTFD-Paket gefunden: {rtf_pfad}")
            rtf_datei = os.path.join(basis_ordner, kandidaten[0])
    else:
        basis_ordner = os.path.dirname(os.path.abspath(rtf_pfad))
        rtf_datei = rtf_pfad

    with open(rtf_datei, "rb") as f:
        rohbytes = f.read()

    leser = _RtfDokumentLeser(
        rohbytes,
        basis_ordner=basis_ordner,
        bildunterschrift_groesse=bildunterschrift_groesse,
    )
    leser.parsen()

    absaetze = leser.absaetze
    gefundener_titel = leser.dok_titel
    gefundener_autor = leser.dok_autor
    gefundenes_datum = leser.dok_datum or erwartetes_datum

    titel_idx: Optional[int] = None
    titel_kandidaten = [t.lower().strip() for t in (erwarteter_titel, gefundener_titel) if t]
    for idx, p in enumerate(absaetze[:4]):
        p_klartext = str(p["plain"]).strip()
        p_klein = p_klartext.lower()
        if any(p_klein == c for c in titel_kandidaten):
            titel_idx = idx
            if not gefundener_titel:
                gefundener_titel = p_klartext
            break
        if idx == 0 and len(p_klartext) <= 350 and not p_klartext.endswith((".", "!", "?", ";", ":")):
            titel_idx = idx
            if not gefundener_titel:
                gefundener_titel = p_klartext
            break
        if p.get("heading") or (p_klartext.isupper() and len(re.findall(r"[A-Za-zÄÖÜäöüß]", p_klartext)) >= 3 and len(p_klartext) <= 200):
            titel_idx = idx
            if not gefundener_titel:
                gefundener_titel = p_klartext
            break

    typst_bloecke: List[str] = []
    klartext_absaetze: List[str] = []
    bib_eintraege: List[str] = []
    bib_ueberschrift: Optional[str] = None
    erster_fliesstext_fertig = False
    im_bib_abschnitt = False
    letztes_war_ueberschrift = False

    bib_header_re = re.compile(rf"^(?:{BIBLIOGRAFIE_WOERTER_MUSTER})\b:?\s*$", re.IGNORECASE)
    bib_praefix_re = re.compile(rf"^(?:{BIBLIOGRAFIE_WOERTER_MUSTER})\b:?\s*(.*)$", re.IGNORECASE)

    for idx, p in enumerate(absaetze):
        inhalt = re.sub(r"\](?=\()", r"]\\", str(p["typst"]))
        p_klartext = str(p["plain"]).strip()
        klartext_absaetze.append(str(p["plain"]))

        if idx == titel_idx:
            if erwarteter_titel:
                t_innen = typst_maskieren(erwarteter_titel)
            elif inhalt.startswith("#strong[") and inhalt.endswith("]"):
                t_innen = inhalt[8:-1]
            else:
                t_innen = inhalt
            abstand_titel = "1.8mm" if fmt in ("atk1", "atk2", "atk3") else "1.4mm"
            ausrichtung = "left" if fmt in ("br1", "br2") else "center"
            typst_bloecke.append(
                f"#align({ausrichtung})[\n  #block[\n"
                f'    #set text(font: {titel_schrift}, size: {titelgroesse}, weight: "bold", fill: rgb("#000000"))\n'
                f"    #set par(justify: false, leading: {zeilenabstand})\n"
                f"    #strong[{t_innen}]\n"
                f"  ]\n]\n#v({abstand_titel})"
            )
            continue

        if (
            titel_idx is not None
            and idx == titel_idx + 1
            and (
                ist_autorenname(p_klartext)
                or p.get("align") == "center"
                or p_klartext == gefundener_autor
                or bool(re.match(r"^(?:autor|author|von|by):\s*", p_klartext, re.I))
            )
        ):
            if not gefundener_autor:
                gefundener_autor = p_klartext
            if fmt == "atk3":
                sauber_a = gefundener_autor.strip()
                m_von = re.match(r"^(?:von|by|por)\s+(.+)$", sauber_a, re.IGNORECASE)
                if m_von:
                    sauber_a = m_von.group(1).strip()
                autor_text = f"VON {sauber_a}".upper()
                typst_bloecke.append(
                    f'#align(center)[\n  #block[\n    #text(font: {AUTOR_AKZENT_SCHRIFT}, size: 8.5pt, weight: "regular", tracking: 0.08em, fill: rgb("#000000"))[{typst_maskieren(autor_text)}]\n  ]\n]\n#v(1.5mm)'
                )
            elif fmt in ("br1", "br2"):
                typst_bloecke.append(
                    f'#align(left)[\n  #block[\n    #text(style: "italic", weight: "regular", fill: rgb("#000000"))[{inhalt}]\n  ]\n]\n#v(1.5mm)'
                )
            else:
                typst_bloecke.append(
                    f'#align(center)[\n  #par(justify: false)[\n    #text(style: "italic", weight: "regular", fill: rgb("#000000"))[{inhalt}]\n  ]\n]\n#v(1.5mm)'
                )
            continue

        woerter = p_klartext.split()
        alle_urls_rtf = bool(
            woerter
            and all(
                w.startswith(("http://", "https://", "doi:", "10."))
                or w.lower() in ("doi.org", "url:", "quelle:", "quellen:", "links:", "link:", "library:")
                or re.match(r"^https?://", w)
                or re.match(r"^10\.\d{4,9}/", w)
                for w in woerter
            )
        )

        m_bib = bib_praefix_re.match(p_klartext)
        if m_bib:
            im_bib_abschnitt = True
            erstes_w = p_klartext.split()[0].rstrip(":").strip()
            bib_ueberschrift = erstes_w.capitalize() if (erstes_w.isupper() and len(erstes_w) > 3) else erstes_w
            rest_rtf = m_bib.group(1).strip()
            if rest_rtf and (len(rest_rtf) >= 15 or re.search(r"https?://|\b10\.\d{4,9}/", rest_rtf)):
                bib_eintraege.append(rest_rtf)
            continue

        if im_bib_abschnitt or ist_apa_zitat(p_klartext) or alle_urls_rtf:
            if bib_header_re.match(p_klartext):
                continue
            bib_eintraege.append(p_klartext if alle_urls_rtf else inhalt)
            continue

        if re.match(r"^[=\-_*~]{3,}\s*$", p_klartext):
            continue

        leer_anzahl = int(p.get("empty_paragraphs_before", 0))  # type: ignore[arg-type]
        if letztes_war_ueberschrift:
            abstand_oben = ""
            letztes_war_ueberschrift = False
        elif leer_anzahl > 0 and typst_bloecke:
            abstand_oben = f"#v({0.8 + (leer_anzahl - 1) * 1.0:g}em)\n"
        else:
            abstand_oben = ""

        ist_md_heading = bool(re.match(r"^#{1,6}\s+", p_klartext))
        if p.get("align") == "center":
            typst_bloecke.append(f"{abstand_oben}#align(center)[\n  #par(justify: false)[\n    {inhalt}\n  ]\n]")
        elif p.get("align") == "right":
            typst_bloecke.append(f"{abstand_oben}#align(right)[\n  #par(justify: false)[\n    {inhalt}\n  ]\n]")
        elif ist_md_heading:
            saubere_h = re.sub(r"^#{1,6}\s+", "", p_klartext).strip()
            naechstes_p = absaetze[idx + 1] if idx + 1 < len(absaetze) else None
            leer_danach = int(naechstes_p.get("empty_paragraphs_before", 0)) if naechstes_p else 0  # type: ignore[arg-type]
            typst_bloecke.append(
                ueberschrift_typst_erzeugen(
                    saubere_h,
                    fmt=fmt,
                    ueberschrift_schrift=ueberschrift_schrift,
                    leerzeilen_davor=leer_anzahl,
                    leerzeilen_danach=leer_danach,
                    ist_markdown=True,
                )
            )
            letztes_war_ueberschrift = True
        else:
            if initial_verwenden and not erster_fliesstext_fertig and not inhalt.lstrip().startswith(("#table", "#align")):
                init_hoehe = 3 if fmt in ("atk2", "atk3") else 4
                init_gewicht = "regular" if fmt in ("atk2", "atk3") else "bold"
                init_schrift = initial_schriftart_aufloesen(fmt, titel_schrift)
                inhalt_init = initial_anwenden(
                    inhalt,
                    schrift_angabe=init_schrift,
                    hoehe=init_hoehe,
                    gewicht=init_gewicht,
                    abstand="2pt",
                )
                typst_bloecke.append(f"{abstand_oben}{inhalt_init}")
            else:
                if p.get("has_indent"):
                    inhalt = f"#h(3.8mm){inhalt}"
                typst_bloecke.append(f"{abstand_oben}{inhalt}")
            erster_fliesstext_fertig = True

    if titel_idx is None and erwarteter_titel:
        dok_titel_sauber, _ = titel_und_autor_bereinigen(erwarteter_titel)
        if dok_titel_sauber:
            v_gap = "1.8mm" if fmt in ("atk1", "atk2", "atk3") else "1.4mm"
            ausrichtung = "left" if fmt in ("br1", "br2") else "center"
            t_block = (
                f'#show "_": "_" + sym.zws\n#show "/": "/" + sym.zws\n'
                f"#align({ausrichtung})[\n  #block(width: 100%)[\n"
                f"    #par(justify: false, leading: {zeilenabstand})[\n"
                f'      #text(font: {titel_schrift}, size: {titelgroesse}, weight: "bold", hyphenate: false, fill: rgb("#000000"))[#strong[{typst_maskieren(dok_titel_sauber)}]]\n'
                f"    ]\n  ]\n]\n#v({v_gap})"
            )
            typst_bloecke.insert(0, t_block)
            if erwarteter_autor:
                if fmt == "atk3":
                    sauber_a = erwarteter_autor.strip()
                    m_von = re.match(r"^(?:von|by|por)\s+(.+)$", sauber_a, re.IGNORECASE)
                    if m_von:
                        sauber_a = m_von.group(1).strip()
                    autor_text = f"VON {sauber_a}".upper()
                    a_block = f'#align(center)[\n  #block[\n    #text(font: {AUTOR_AKZENT_SCHRIFT}, size: 8.5pt, weight: "regular", tracking: 0.08em, fill: rgb("#000000"))[{typst_maskieren(autor_text)}]\n  ]\n]\n#v(1.5mm)'
                elif fmt in ("br1", "br2"):
                    a_block = f'#align(left)[\n  #block[\n    #text(style: "italic", weight: "regular", fill: rgb("#000000"))[{typst_maskieren(erwarteter_autor)}]\n  ]\n]\n#v(1.5mm)'
                else:
                    a_block = f'#align(center)[\n  #par(justify: false)[\n    #text(style: "italic", weight: "regular", fill: rgb("#000000"))[{typst_maskieren(erwarteter_autor)}]\n  ]\n]\n#v(1.5mm)'
                typst_bloecke.insert(1, a_block)

    if bilder:
        for bild_p in bilder:
            aufgeloest = bildpfad_aufloesen(bild_p, dokument_ordner=basis_ordner)
            if aufgeloest:
                typst_bloecke.append(abbildung_typst(aufgeloest, bildunterschrift_groesse=bildunterschrift_groesse))
            else:
                drucke_warnung(f"Übergebene Bilddatei nicht gefunden und übersprungen: {bild_p}")

    hat_einzuege = any(bool(p.get("has_indent", False)) for p in absaetze)
    gesamt_klartext = "\n\n".join(klartext_absaetze)
    gefundene_urls = leser.urls + urls_aus_text_extrahieren(gesamt_klartext)
    eindeutige_urls: List[str] = []
    gesehen_urls = set()
    for u in gefundene_urls:
        if u and u not in gesehen_urls:
            gesehen_urls.add(u)
            eindeutige_urls.append(u)

    return (
        "\n\n".join(typst_bloecke),
        eindeutige_urls,
        gefundener_titel,
        gefundener_autor,
        gefundenes_datum,
        bib_eintraege,
        bib_ueberschrift,
        hat_einzuege,
    )
