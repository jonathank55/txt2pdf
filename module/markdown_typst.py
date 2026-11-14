# -*- coding: utf-8 -*-
"""Konvertierung von Text-, Markdown-, Tabellen-, Bild- und Listenblöcken in Typst-Quelltext."""

import ntpath
import os
import re
from typing import Dict, List, Optional, Tuple
import urllib.parse

from .ausgabe import drucke_warnung
from .konfiguration import BIBLIOGRAFIE_WOERTER_MUSTER, BILD_ENDUNGEN
from .schriftarten import (
    INLINE_CODE_SCHRIFT,
    initial_schriftart_aufloesen,
)
from .textanalyse import (
    isbns_extrahieren,
    ist_apa_zitat,
    ist_autorenname,
    ist_einzelner_satz,
)


def typst_maskieren(zeile: str) -> str:
    """Maskiert Typst-Steuerzeichen außerhalb beabsichtigter Typst-Aufrufe."""
    ergebnis = zeile
    for zeichen in ("#", "$", "@", "[", "]", "*", "<", ">"):
        ergebnis = ergebnis.replace(zeichen, f"\\{zeichen}")
    return ergebnis.replace("//", r"\/\/").replace("/*", r"\/\*").replace("*/", r"\*\/")


def typst_zeichenkette_maskieren(wert: str) -> str:
    """Maskiert Backslashes und Anführungszeichen für Typst-Zeichenkettenliterale."""
    return wert.replace("\\", "\\\\").replace('"', '\\"')


def urls_aus_text_extrahieren(text: str) -> List[str]:
    """Extrahiert alle eindeutigen HTTP/HTTPS-URLs aus einem Dokument."""
    md_urls = re.findall(r"\[(?:[^\]]+)\]\((https?://[^\s\)]+)\)", text)
    nackte_urls = re.findall(r'https?://[^\s<>\"\'\[\]]+', text)

    alle: List[str] = []
    gesehen = set()
    for url_roh in md_urls + nackte_urls:
        sauber = url_bereinigen(url_roh)
        if sauber and sauber not in gesehen:
            gesehen.add(sauber)
            alle.append(sauber)
    return alle


def url_bereinigen(url_roh: str) -> str:
    """Entfernt nachgestellte Satzzeichen und unbalancierte Schlussklammern aus URLs."""
    u = url_roh.strip().rstrip('.,;:>"\'')
    while u.endswith(")") and u.count(")") > u.count("("):
        u = u[:-1]
    return u


def inhalt_zu_typst(text: str) -> str:
    """Wandelt Markdown-Auszeichnungen (Links, Code, Fett, Kursiv, Durchgestrichen) sicher in Typst um."""
    links: List[str] = []

    def _speichere_md_link(m: re.Match) -> str:
        beschriftung = m.group(1)
        url = url_bereinigen(m.group(2))
        idx = len(links)
        links.append(f'#link("{typst_zeichenkette_maskieren(url)}")[{typst_maskieren(beschriftung)}]')
        return f"TYPSTLINKPLH{idx}ENDE"

    def _speichere_nackte_url(m: re.Match) -> str:
        roh = m.group(0)
        url = url_bereinigen(roh)
        rest = roh[len(url) :]
        idx = len(links)
        links.append(f'#link("{typst_zeichenkette_maskieren(url)}")[{typst_maskieren(url)}]')
        return f"TYPSTLINKPLH{idx}ENDE{rest}"

    def _speichere_doi(m: re.Match) -> str:
        praefix = m.group(1)
        doi_wert = url_bereinigen(m.group(2))
        rest = m.group(2)[len(doi_wert) :]
        url = f"https://doi.org/{doi_wert}"
        idx = len(links)
        links.append(f'{typst_maskieren(praefix)}#link("{typst_zeichenkette_maskieren(url)}")[{typst_maskieren(url)}]')
        return f"TYPSTLINKPLH{idx}ENDE{rest}"

    text = re.sub(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", _speichere_md_link, text)
    text = re.sub(r'https?://[^\s<>"\'\[\]]+', _speichere_nackte_url, text)
    text = re.sub(r'\b(doi:\s*)(10\.\d{4,9}/[^\s<>"\'\[\]]+)', _speichere_doi, text, flags=re.I)

    codes: List[str] = []

    def _speichere_code(m: re.Match) -> str:
        innen = m.group(1)
        idx = len(codes)
        innen_esc = typst_zeichenkette_maskieren(innen)
        codes.append(
            f'#box(fill: rgb("#f4f4f4"), inset: (x: 2.5pt, y: 0pt), baseline: 0%, radius: 1.5pt)'
            f'[#text(font: {INLINE_CODE_SCHRIFT}, size: 0.88em)["{innen_esc}"]]'
        )
        return f"TYPSTCODEPLH{idx}ENDE"

    text = re.sub(r"`([^`\n]+)`", _speichere_code, text)

    fett_kursive: List[str] = []

    def _speichere_fett_kursiv(m: re.Match) -> str:
        idx = len(fett_kursive)
        fett_kursive.append(f"#strong[#emph[{typst_maskieren(m.group(1))}]]")
        return f"TYPSTFKPLH{idx}ENDE"

    text = re.sub(r"\*\*\*(.+?)\*\*\*", _speichere_fett_kursiv, text)
    text = re.sub(r"___(.+?)___", _speichere_fett_kursiv, text)

    fette: List[str] = []

    def _speichere_fett(m: re.Match) -> str:
        idx = len(fette)
        fette.append(f"#strong[{typst_maskieren(m.group(1))}]")
        return f"TYPSTFETTPLH{idx}ENDE"

    text = re.sub(r"\*\*(.+?)\*\*", _speichere_fett, text)
    text = re.sub(r"__(.+?)__", _speichere_fett, text)

    kursive: List[str] = []

    def _speichere_kursiv(m: re.Match) -> str:
        idx = len(kursive)
        kursive.append(f"#emph[{typst_maskieren(m.group(1))}]")
        return f"TYPSTKURSPLH{idx}ENDE"

    text = re.sub(r"(?<!\*)\*(?!\s|\*)(.+?)(?<!\s|\*)\*(?!\*)", _speichere_kursiv, text)
    text = re.sub(r"(?<![a-zA-Z0-9_])_(?!\s|_)(.+?)(?<!\s|_)_(?![a-zA-Z0-9_])", _speichere_kursiv, text)

    durchgestrichene: List[str] = []

    def _speichere_durchgestrichen(m: re.Match) -> str:
        idx = len(durchgestrichene)
        durchgestrichene.append(f"#strike[{typst_maskieren(m.group(1))}]")
        return f"TYPSTSTRIKEPLH{idx}ENDE"

    text = re.sub(r"~~(.+?)~~", _speichere_durchgestrichen, text)

    # Gedankenstriche vereinheitlichen
    text = text.replace("—", " – ").replace("---", "--")
    text = re.sub(r"\s*–\s*", " – ", text)

    # Verbleibende Steuerzeichen inkl. einzelner * und _ maskieren
    for z in ("#", "$", "@", "[", "]", "<", ">", "*", "_"):
        text = text.replace(z, f"\\{z}")
    text = text.replace("//", r"\/\/").replace("/*", r"\/\*").replace("*/", r"\*\/")

    for idx, wert in enumerate(durchgestrichene):
        text = text.replace(f"TYPSTSTRIKEPLH{idx}ENDE", wert)
    for idx, wert in enumerate(kursive):
        text = text.replace(f"TYPSTKURSPLH{idx}ENDE", wert)
    for idx, wert in enumerate(fette):
        text = text.replace(f"TYPSTFETTPLH{idx}ENDE", wert)
    for idx, wert in enumerate(fett_kursive):
        text = text.replace(f"TYPSTFKPLH{idx}ENDE", wert)
    for idx, wert in enumerate(codes):
        text = text.replace(f"TYPSTCODEPLH{idx}ENDE", wert)
    for idx, wert in enumerate(links):
        text = text.replace(f"TYPSTLINKPLH{idx}ENDE", wert)

    return text


def bildpfad_aufloesen(roh_pfad: str, dokument_ordner: str = "") -> Optional[str]:
    """Löst lokale, relative oder aus fremden Systemen stammende Bildpfade zuverlässig auf."""
    if not roh_pfad:
        return None

    bereinigt = roh_pfad.strip().strip("\"'")
    if bereinigt.startswith("file://"):
        bereinigt = urllib.parse.unquote(bereinigt[7:])

    unescaped = bereinigt.replace(r"\ ", " ").replace(r"\:", ":")
    basis_name = ntpath.basename(unescaped) or os.path.basename(unescaped)

    kandidaten: List[str] = [unescaped, bereinigt]
    if dokument_ordner:
        kandidaten.extend([
            os.path.join(dokument_ordner, unescaped),
            os.path.join(dokument_ordner, bereinigt),
        ])
        if basis_name:
            kandidaten.extend([
                os.path.join(dokument_ordner, basis_name),
                os.path.join(dokument_ordner, "Bilder", basis_name),
                os.path.join(dokument_ordner, "bilder", basis_name),
                os.path.join(dokument_ordner, "images", basis_name),
                os.path.join(dokument_ordner, "assets", basis_name),
            ])
    arbeitsordner = os.getcwd()
    kandidaten.append(os.path.join(arbeitsordner, unescaped))
    if basis_name:
        kandidaten.append(os.path.join(arbeitsordner, basis_name))

    for kandidat in kandidaten:
        if kandidat and os.path.isfile(kandidat):
            return os.path.abspath(kandidat)

    return None


def abbildung_typst(
    bildpfad: str,
    beschriftung: str = "",
    quelle: str = "",
    bildunterschrift_groesse: str = "6pt",
) -> str:
    """Erzeugt einen gerahmten Typst-Abbildungsblock mit optionaler Bildunterschrift."""
    abs_pfad = typst_zeichenkette_maskieren(os.path.abspath(bildpfad))
    beschriftung_esc = typst_maskieren(beschriftung) if beschriftung else ""
    quelle_esc = typst_maskieren(quelle) if quelle else ""
    quellen_zusatz = f" _Quelle: {quelle_esc}._" if quelle_esc else ""

    unterschrift_block = ""
    if beschriftung_esc or quellen_zusatz:
        unterschrift_block = (
            f'\n      #v(1.4mm)\n'
            f'      #text(size: {bildunterschrift_groesse}, fill: rgb("#000000"))[\n'
            f'        {beschriftung_esc}{quellen_zusatz}\n'
            f'      ]'
        )

    return (
        f"\n#align(center)[\n"
        f'  #block(width: 100%, stroke: 0.35pt + rgb("#000000"), radius: 2pt, clip: true)[\n'
        f'    #image("{abs_pfad}", width: 100%, fit: "contain")\n'
        f"  ]{unterschrift_block}\n"
        f"]\n#v(2.5mm)\n"
    )


def absatz_zu_typst(zeilen_im_absatz: List[str]) -> str:
    """Wandelt die Zeilen eines Absatzes unter Wahrung manueller Zeilenumbrüche in Typst um."""
    if not zeilen_im_absatz:
        return ""
    if len(zeilen_im_absatz) == 1:
        return inhalt_zu_typst(zeilen_im_absatz[0].strip())

    saubere_zeilen = [z.strip() for z in zeilen_im_absatz if z.strip()]
    if not saubere_zeilen:
        return ""

    hat_explizite_umbrueche = any(
        orig.endswith("  ") or orig.rstrip().endswith("\\") for orig in zeilen_im_absatz
    )
    alle_kurz = all(len(z) < 65 for z in saubere_zeilen)

    if hat_explizite_umbrueche or alle_kurz:
        formatiert: List[str] = []
        for orig in zeilen_im_absatz:
            s_z = orig.strip()
            if not s_z:
                continue
            if s_z.endswith("\\"):
                s_z = s_z[:-1].strip()
            formatiert.append(inhalt_zu_typst(s_z))
        return " #linebreak()\n".join(formatiert)

    teile: List[str] = []
    for orig in zeilen_im_absatz:
        s_z = orig.strip()
        if not s_z:
            continue
        umbruch = orig.endswith("  ") or orig.rstrip().endswith("\\")
        if s_z.endswith("\\"):
            s_z = s_z[:-1].strip()
        esc = inhalt_zu_typst(s_z)
        if umbruch:
            esc += " #linebreak()"
        teile.append(esc)
    return " ".join(teile)


def initial_anwendbar(rohzeilen: List[str]) -> bool:
    """Prüft, ob ein Absatz für ein großes Anfangsinitial (Drop Cap) geeignet ist."""
    rohtext = "\n".join(rohzeilen).strip()
    if not rohtext:
        return False
    if not re.search(r"[A-Za-zÄÖÜäöüß]", rohtext):
        return False
    # Beginn sollte ein Buchstabe oder Anführungszeichen vor einem Buchstaben sein
    if not re.match(r'^[\s„"«»\'`*_\[]*[A-Za-zÄÖÜäöüß]', rohtext):
        return False
    if re.match(r"^#{1,6}\s+", rohtext):
        return False
    if rohtext.startswith(("##", ">")):
        return False
    if re.match(r"^[=\-_*~]{3,}\s*$", rohtext):
        return False
    if rohtext.startswith("|") or (rohtext.endswith("|") and "|" in rohtext[1:-1]):
        return False
    if rohtext.startswith(("- ", "* ", "• ")) or re.match(r"^\d+[\.\)]\s+", rohtext):
        return False
    if ist_autorenname(rohtext):
        return False
    if re.match(rf"^(?:{BIBLIOGRAFIE_WOERTER_MUSTER})\b:?\s*$", rohtext, re.IGNORECASE):
        return False
    if ist_apa_zitat(rohtext):
        return False
    return True


def initial_anwenden(
    inhalt: str,
    schrift_angabe: Optional[str] = None,
    hoehe: int = 4,
    gewicht: str = "bold",
    abstand: str = "2pt",
) -> str:
    """Umschließt den ersten Fließtextabsatz mit einem droplet-Initial."""
    s = inhalt.strip()
    if not s or s.startswith(("#dropcap", "#table", "- ", "#grid", "#align")):
        return s
    schrift = schrift_angabe if schrift_angabe else '("Libre Baskerville", "PT Serif")'
    gewicht_zusatz = f', weight: "{gewicht}"' if gewicht else ""
    return (
        f"#dropcap(\n"
        f"  height: {hoehe},\n"
        f"  gap: {abstand},\n"
        f"  justify: true,\n"
        f"  transform: it => text(font: {schrift}{gewicht_zusatz}, it)\n"
        f")[{s}]"
    )


def tabelle_zu_typst(tabellen_zeilen: List[str]) -> str:
    """Konvertiert eine Markdown-Tabelle in eine Typst-Tabelle."""
    if len(tabellen_zeilen) < 2:
        return ""

    kopf = [c.strip() for c in tabellen_zeilen[0].strip().strip("|").split("|")]
    if not kopf:
        return ""
    spalten = len(kopf)

    ausrichtungen: List[str] = []
    daten_start = 1

    if len(tabellen_zeilen) > 1 and re.match(r"^[\s:\-\|]+$", tabellen_zeilen[1]):
        daten_start = 2
        trenner = [c.strip() for c in tabellen_zeilen[1].strip().strip("|").split("|")]
        for t in trenner:
            t_sauber = t.strip()
            if t_sauber.startswith(":") and t_sauber.endswith(":"):
                ausrichtungen.append("center")
            elif t_sauber.endswith(":"):
                ausrichtungen.append("right")
            else:
                ausrichtungen.append("left")

    while len(ausrichtungen) < spalten:
        ausrichtungen.append("left")
    ausrichtung_feld = ", ".join(ausrichtungen[:spalten])

    zellen: List[str] = [f"[#strong[{inhalt_zu_typst(h)}]]" for h in kopf]
    for zeile in tabellen_zeilen[daten_start:]:
        s_zeile = zeile.strip()
        if not s_zeile or "|" not in s_zeile:
            continue
        werte = [c.strip() for c in s_zeile.strip("|").split("|")]
        while len(werte) < spalten:
            werte.append("")
        for wert in werte[:spalten]:
            zellen.append(f"[{inhalt_zu_typst(wert)}]")

    zellen_block = ",\n      ".join(zellen)
    return (
        f"#align(left)[\n"
        f"  #block(width: 100%, inset: (y: 0.8em))[\n"
        f"    #set text(size: 8.5pt)\n"
        f"    #set par(justify: false)\n"
        f"    #table(\n"
        f"      columns: {spalten},\n"
        f"      align: (col, row) => ({ausrichtung_feld}).at(calc.min(col, {spalten - 1})),\n"
        f'      stroke: (x, y) => if y == 0 {{ (bottom: 0.8pt + rgb("#000000")) }} else {{ (bottom: 0.3pt + rgb("#bbbbbb")) }},\n'
        f'      fill: (col, row) => if row == 0 {{ rgb("#f4f4f4") }} else {{ none }},\n'
        f"      {zellen_block}\n"
        f"    )\n"
        f"  ]\n"
        f"]\n"
    )


def ueberschrift_typst_erzeugen(
    ueberschrift_text: str,
    fmt: str,
    ueberschrift_schrift: Optional[str],
    leerzeilen_davor: int,
    leerzeilen_danach: int,
    ist_markdown: bool = False,
) -> str:
    """Erzeugt einen konsistenten Typst-Überschriftenblock entsprechend des Formats."""
    h_text = inhalt_zu_typst(ueberschrift_text) if ist_markdown or any(z in ueberschrift_text for z in ("*", "_", "`", "—", "[")) else typst_maskieren(ueberschrift_text)
    h_schrift_arg = ueberschrift_schrift if ueberschrift_schrift else "none"
    enger_abstand = "1.15em" if fmt == "apa" else "0.55em"

    hat_abstand_davor = leerzeilen_davor > 0
    hat_abstand_danach = leerzeilen_danach > 0
    extra_danach = max(0, leerzeilen_danach - 1)

    if fmt in ("atk1", "atk2", "atk3"):
        oben = (f"{2.8 + (leerzeilen_davor - 1) * 1.0:g}em" if leerzeilen_davor > 1 else "2.8em") if hat_abstand_davor else enger_abstand
        unten = (f"{2.8 + extra_danach * 1.0:g}em" if extra_danach > 0 else "2.8em") if hat_abstand_danach else enger_abstand
        zentriert = "true"
    elif fmt in ("br1", "br2"):
        oben = (f"{2.0 + (leerzeilen_davor - 1) * 1.0:g}em" if leerzeilen_davor > 1 else "2.0em") if hat_abstand_davor else enger_abstand
        unten = (f"{1.0 + extra_danach * 1.0:g}em" if extra_danach > 0 else "1.0em") if hat_abstand_danach else enger_abstand
        zentriert = "false"
    else:
        oben = (f"{1.2 + (leerzeilen_davor - 1) * 1.0:g}em" if leerzeilen_davor > 1 else "1.2em") if hat_abstand_davor else enger_abstand
        unten = "0pt" if fmt == "apa" else ((f"{1.2 + extra_danach * 1.0:g}em" if extra_danach > 0 else "1.2em") if hat_abstand_danach else enger_abstand)
        zentriert = "false" if fmt == "apa" else "true"

    return (
        f"#render_section_heading([{h_text}], align_center: {zentriert}, "
        f"font_attr: {h_schrift_arg}, above_gap: {oben}, below_gap: {unten})\n"
    )


def _ist_reine_quellzeile(zeile_str: str) -> bool:
    s = zeile_str.strip()
    if not s:
        return False
    if s.startswith(("http://", "https://", "doi:", "10.")) or re.match(r"^https?://", s) or re.match(r"^10\.\d{4,9}/", s):
        return True
    if isbns_extrahieren(s):
        return True
    return ist_apa_zitat(s)


def _ist_bilddirektive(zeile: str) -> bool:
    """Erkennt ##Pfad/zur/Bilddatei.ext im Unterschied zu einer Markdown-H2-Überschrift."""
    if not zeile.startswith("##") or zeile.startswith("###"):
        return False
    ziel = zeile[2:].strip().strip("\"'")
    if not ziel:
        return False
    if ziel.startswith(("file://", "/", "~/", "./", "../")) or re.match(r"^[A-Za-z]:[\\/]", ziel):
        return True
    return ziel.lower().endswith(BILD_ENDUNGEN)


def textkoerper_zu_typst(
    rohzeilen: List[str],
    bilder: Optional[List[str]] = None,
    bildunterschrift_groesse: str = "6pt",
    initial_verwenden: bool = True,
    dokument_ordner: str = "",
    titel_schrift: Optional[str] = None,
    ueberschrift_schrift: Optional[str] = None,
    fmt: str = "atk2",
) -> Tuple[str, List[str], List[str], Optional[str], bool]:
    """Parst reine Text- und Markdownzeilen in Typst-Elemente samt Quellen- und Bilderfassung."""
    gesamter_rohtext = "\n".join(rohzeilen)
    alle_urls = urls_aus_text_extrahieren(gesamter_rohtext)

    bib_exakt_re = re.compile(rf"^(?:{BIBLIOGRAFIE_WOERTER_MUSTER})\b:?\s*$", re.IGNORECASE)
    bib_praefix_re = re.compile(rf"^({BIBLIOGRAFIE_WOERTER_MUSTER})\b:?\s+(.+)$", re.IGNORECASE)

    absaetze: List[Dict[str, object]] = []
    aktuelle_zeilen: List[str] = []
    aktueller_einzug = False
    aktueller_abstand = 0
    leerzeilen_zaehler = 0

    def _absatz_abschliessen():
        nonlocal aktuelle_zeilen, aktueller_einzug, aktueller_abstand
        if aktuelle_zeilen:
            absaetze.append({
                "text": "\n".join(aktuelle_zeilen),
                "raw_lines": list(aktuelle_zeilen),
                "has_indent": aktueller_einzug,
                "blank_lines_before": aktueller_abstand,
                "has_blank_before": aktueller_abstand > 0,
            })
            aktuelle_zeilen = []
            aktueller_einzug = False
            aktueller_abstand = 0

    for zeile in rohzeilen:
        s = zeile.strip()
        if not s:
            _absatz_abschliessen()
            leerzeilen_zaehler += 1
            continue

        ist_eingerueckt = zeile.startswith(("\t", "  ")) or (len(zeile) > len(zeile.lstrip()) and bool(s))

        if bib_exakt_re.match(s):
            _absatz_abschliessen()
            absaetze.append({
                "text": s,
                "raw_lines": [zeile],
                "has_indent": False,
                "blank_lines_before": leerzeilen_zaehler,
                "has_blank_before": leerzeilen_zaehler > 0,
            })
            leerzeilen_zaehler = 0
            continue

        m_pref = bib_praefix_re.match(s)
        if m_pref:
            _absatz_abschliessen()
            absaetze.append({
                "text": m_pref.group(1).strip(),
                "raw_lines": [m_pref.group(1).strip()],
                "has_indent": False,
                "blank_lines_before": leerzeilen_zaehler,
                "has_blank_before": leerzeilen_zaehler > 0,
            })
            leerzeilen_zaehler = 0
            rest_zeile = m_pref.group(2).strip()
            if rest_zeile:
                absaetze.append({
                    "text": rest_zeile,
                    "raw_lines": [rest_zeile],
                    "has_indent": ist_eingerueckt,
                    "blank_lines_before": 0,
                    "has_blank_before": False,
                })
            continue

        ist_listenpunkt = bool(re.match(r"^[-*•]\s+|^\d+[\.\)]\s+", s))
        if ist_listenpunkt:
            if aktuelle_zeilen and not any(re.match(r"^[-*•]\s+|^\d+[\.\)]\s+", cl.strip()) for cl in aktuelle_zeilen):
                _absatz_abschliessen()
            if not aktuelle_zeilen:
                aktueller_abstand = leerzeilen_zaehler
                leerzeilen_zaehler = 0
            aktuelle_zeilen.append(zeile)
            continue

        if aktuelle_zeilen and any(re.match(r"^[-*•]\s+|^\d+[\.\)]\s+", cl.strip()) for cl in aktuelle_zeilen):
            _absatz_abschliessen()

        ist_md_ueberschrift = bool(re.match(r"^#{1,6}\s+", s))
        ist_tabelle = s.startswith("|") or (s.endswith("|") and "|" in s[1:-1])
        if ist_tabelle and aktuelle_zeilen and not any("|" in cl for cl in aktuelle_zeilen):
            _absatz_abschliessen()

        ist_bild = _ist_bilddirektive(s)
        ist_isolierter_kandidat = not ist_eingerueckt and ist_einzelner_satz(s) and len(s) <= 250

        if ist_bild or s.startswith(">") or ist_md_ueberschrift or ist_isolierter_kandidat:
            if not ist_tabelle:
                _absatz_abschliessen()
                absaetze.append({
                    "text": s,
                    "raw_lines": [zeile],
                    "has_indent": False,
                    "blank_lines_before": leerzeilen_zaehler,
                    "has_blank_before": leerzeilen_zaehler > 0,
                })
                leerzeilen_zaehler = 0
                continue

        if re.match(r"^[=\-_*~]{3,}\s*$", s):
            _absatz_abschliessen()
            absaetze.append({
                "text": s,
                "raw_lines": [zeile],
                "has_indent": False,
                "blank_lines_before": leerzeilen_zaehler,
                "has_blank_before": leerzeilen_zaehler > 0,
                "is_separator": True,
            })
            leerzeilen_zaehler = 0
            continue

        if ist_eingerueckt and aktuelle_zeilen:
            _absatz_abschliessen()
            aktueller_einzug = True

        if not aktuelle_zeilen:
            aktueller_einzug = ist_eingerueckt
            aktueller_abstand = leerzeilen_zaehler
            leerzeilen_zaehler = 0
        aktuelle_zeilen.append(zeile)

    _absatz_abschliessen()

    typst_elemente: List[str] = []
    explizite_bib_eintraege: List[str] = []
    bib_ueberschrift: Optional[str] = None
    erster_fliesstext_fertig = False
    im_literaturverzeichnis = False
    letztes_war_fliesstext = False
    letztes_war_ueberschrift = False

    for i, p_info in enumerate(absaetze):
        para = str(p_info["text"])
        hat_einzug = bool(p_info["has_indent"])
        leer_davor = int(p_info.get("blank_lines_before", 0))  # type: ignore[arg-type]
        roh_zeilen = list(p_info.get("raw_lines", para.splitlines()))  # type: ignore[arg-type]
        zeilen_im_absatz = para.splitlines()
        erste_zeile = zeilen_im_absatz[0].strip()
        flachtext = " ".join(z.strip() for z in zeilen_im_absatz).strip()
        einzeilig = len(zeilen_im_absatz) == 1

        if letztes_war_ueberschrift or fmt == "apa":
            abstand_oben = ""
            letztes_war_ueberschrift = False
        elif leer_davor > 0 and typst_elemente:
            abstand_oben = f"#v({0.8 + (leer_davor - 1) * 1.0:g}em)\n"
        else:
            abstand_oben = ""

        # 1. Trennlinie
        if p_info.get("is_separator") or (einzeilig and re.match(r"^[=\-_*~]{3,}\s*$", flachtext)):
            oben = "#v(0.8em)\n" if typst_elemente else ""
            typst_elemente.append(f'{oben}#line(length: 100%, stroke: 0.5pt + rgb("#000000"))\n#v(0.8em)\n')
            letztes_war_fliesstext = False
            continue

        # 2. Markdown-Tabelle
        ist_tabelle = (
            len(zeilen_im_absatz) >= 2
            and all("|" in z.strip() for z in zeilen_im_absatz if z.strip())
            and any(re.match(r"^[\s:\-\|]+$", z.strip()) for z in zeilen_im_absatz[1:3])
        )
        if ist_tabelle:
            tbl_code = tabelle_zu_typst(zeilen_im_absatz)
            if tbl_code:
                typst_elemente.append(f"{abstand_oben}{tbl_code}")
                letztes_war_fliesstext = False
                continue

        # 3. Inline-Abbildung (##Pfad/zur/Datei)
        if einzeilig and _ist_bilddirektive(erste_zeile):
            ziel_roh = erste_zeile[2:].strip()
            aufgeloest = bildpfad_aufloesen(ziel_roh, dokument_ordner=dokument_ordner)
            if aufgeloest:
                fig_code = abbildung_typst(aufgeloest, bildunterschrift_groesse=bildunterschrift_groesse)
                typst_elemente.append(f"{abstand_oben}{fig_code}")
            else:
                drucke_warnung(f"Bilddatei nicht gefunden und übersprungen: {ziel_roh}")
            letztes_war_fliesstext = False
            continue

        # 4. Blockzitat (> ...)
        if erste_zeile.startswith(">"):
            zitat_text = " ".join(re.sub(r"^>\s*", "", z).strip() for z in zeilen_im_absatz)
            zitat_typst = inhalt_zu_typst(zitat_text)
            typst_elemente.append(
                f'{abstand_oben}#block(width: 100%, inset: (left: 4.5mm, y: 2.2mm), stroke: (left: 2pt + rgb("#000000")), above: 1.2em, below: 1.6em)'
                f'[#par(leading: 0.52em)[#text(style: "italic", fill: rgb("#000000"))[{zitat_typst}]]]\n'
            )
            letztes_war_fliesstext = False
            continue

        # 5. Explizite Literaturverzeichnis-Überschrift
        m_bib_kopf = bib_praefix_re.match(flachtext)
        if bib_exakt_re.match(flachtext) or m_bib_kopf:
            im_literaturverzeichnis = True
            erstes_wort = flachtext.split()[0].rstrip(":").strip()
            if erstes_wort.isupper() and len(erstes_wort) > 3:
                bib_ueberschrift = erstes_wort.capitalize()
            elif erstes_wort:
                bib_ueberschrift = erstes_wort

            if m_bib_kopf:
                rest_bib = m_bib_kopf.group(2).strip()
                kandidat_urls = re.findall(
                    r'https?://[^\s<>"\'\[\]]+|\bdoi:\s*10\.\d{4,9}/[^\s<>"\'\[\]]+|\b10\.\d{4,9}/[^\s<>"\'\[\]]+',
                    rest_bib,
                )
                if kandidat_urls:
                    for ku in kandidat_urls:
                        explizite_bib_eintraege.append(ku.strip())
                elif len(rest_bib) >= 15 and not bib_exakt_re.match(rest_bib):
                    explizite_bib_eintraege.append(rest_bib)
            letztes_war_fliesstext = False
            continue

        # 6. Überschriften-Erkennung (Markdown #..###### oder isolierter Satz)
        m_md_kopf = re.match(r"^(#{1,6})\s+(.+)$", erste_zeile)
        if m_md_kopf and im_literaturverzeichnis:
            # Eine neue Markdown-Überschrift nach den Quellen beendet den Quellenabschnitt wieder.
            im_literaturverzeichnis = False

        ist_num_listenpunkt = False
        if re.match(r"^\d+[\.\)]\s+", erste_zeile):
            ziffern_zeilen = sum(bool(re.match(r"^\d+[\.\)]\s+", z.strip())) for z in zeilen_im_absatz)
            if ziffern_zeilen > 1:
                ist_num_listenpunkt = True
            else:
                dezimal = bool(re.match(r"^\d+\.\d+", erste_zeile))
                versalien = flachtext.isupper() and len(flachtext.split()) > 1
                kapitel_praefix = bool(re.match(r"^(?:Kapitel|Abschnitt|Teil|Section|Chapter|§)\s+", erste_zeile, re.IGNORECASE))
                naechster = absaetze[i + 1] if i + 1 < len(absaetze) else None
                vorheriger = absaetze[i - 1] if i > 0 else None
                naechster_num = bool(naechster and re.match(r"^\d+[\.\)]\s+", str(naechster["text"]).splitlines()[0].strip()))
                vorheriger_num = bool(vorheriger and re.match(r"^\d+[\.\)]\s+", str(vorheriger["text"]).splitlines()[0].strip()))
                if (naechster_num or vorheriger_num) and not (dezimal or versalien or kapitel_praefix):
                    ist_num_listenpunkt = True

        ist_isolierter_satz = (
            not hat_einzug
            and not erste_zeile.startswith(("\t", "  "))
            and not p_info.get("is_separator")
            and not erste_zeile.startswith(("##", ">", "-", "*", "•"))
            and not ist_num_listenpunkt
            and not ist_apa_zitat(flachtext)
            and not im_literaturverzeichnis
            and len(zeilen_im_absatz) <= 2
            and len(flachtext) <= 300
            and ist_einzelner_satz(flachtext)
        )

        if m_md_kopf or ist_isolierter_satz:
            saubere_ueberschrift = m_md_kopf.group(2).strip() if m_md_kopf else re.sub(r"^#{1,6}\s*", "", flachtext).strip()
            naechster_p = absaetze[i + 1] if i + 1 < len(absaetze) else None
            leer_danach = int(naechster_p.get("blank_lines_before", 0)) if naechster_p else 0  # type: ignore[arg-type]
            typst_elemente.append(
                ueberschrift_typst_erzeugen(
                    saubere_ueberschrift,
                    fmt=fmt,
                    ueberschrift_schrift=ueberschrift_schrift,
                    leerzeilen_davor=leer_davor,
                    leerzeilen_danach=leer_danach,
                    ist_markdown=bool(m_md_kopf),
                )
            )
            letztes_war_ueberschrift = True
            letztes_war_fliesstext = False
            continue

        # 7. Zitate / Quellen im Literaturverzeichnis oder isolierte Quellblöcke
        alle_sind_quellen = bool(zeilen_im_absatz and all(_ist_reine_quellzeile(z) for z in zeilen_im_absatz))
        if im_literaturverzeichnis or ist_apa_zitat(flachtext) or alle_sind_quellen:
            # Hinweis: Isolierte URL/Zitatzeilen mitten im Text vermerken wir fürs Quellenverzeichnis,
            # setzen aber im_literaturverzeichnis NICHT dauerhaft auf True, damit Fließtext danach nicht verloren geht!
            kandidat_zeilen = [z.strip() for z in zeilen_im_absatz if z.strip()]
            for z in kandidat_zeilen:
                if bib_exakt_re.match(z):
                    continue
                urls_in_zeile = re.findall(
                    r'https?://[^\s<>"\'\[\]]+|\bdoi:\s*10\.\d{4,9}/[^\s<>"\'\[\]]+|\b10\.\d{4,9}/[^\s<>"\'\[\]]+',
                    z,
                )
                if urls_in_zeile and (len(urls_in_zeile) > 1 or alle_sind_quellen):
                    for einzel_u in urls_in_zeile:
                        explizite_bib_eintraege.append(einzel_u.strip())
                else:
                    explizite_bib_eintraege.append(z)
            letztes_war_fliesstext = False
            continue

        # 8. Aufzählungslisten & nummerierte Listen
        ist_stichpunkt = erste_zeile.startswith(("- ", "* ", "• "))
        ist_nummeriert = bool(re.match(r"^\d+[\.\)]\s+", erste_zeile))
        if ist_stichpunkt or ist_nummeriert:
            listen_zeilen: List[str] = []
            for z in zeilen_im_absatz:
                s_z = z.strip()
                if not s_z:
                    continue
                if re.match(r"^\d+[\.\)]\s+", s_z):
                    listen_zeilen.append(f"+ {inhalt_zu_typst(re.sub(r'^\\d+[\\.\\)]\\s+', '', s_z))}\n")
                elif s_z.startswith(("- ", "* ", "• ")):
                    listen_zeilen.append(f"- {inhalt_zu_typst(re.sub(r'^[-*•]\\s+', '', s_z))}\n")
                else:
                    listen_zeilen.append(f"  {inhalt_zu_typst(s_z)}\n")
            typst_elemente.append(f"{abstand_oben}{''.join(listen_zeilen)}")
            letztes_war_fliesstext = False
            continue

        # 9. Regulärer Fließtextabsatz (optional mit Initial beim ersten Absatz)
        absatz_typst = absatz_zu_typst(roh_zeilen)
        initial_moeglich = initial_verwenden and not erster_fliesstext_fertig and initial_anwendbar(roh_zeilen)

        if initial_moeglich:
            init_hoehe = 3 if fmt in ("atk2", "atk3") else 4
            init_gewicht = "regular" if fmt in ("atk2", "atk3") else "bold"
            init_schrift = initial_schriftart_aufloesen(fmt, titel_schrift or "")
            absatz_typst = initial_anwenden(
                absatz_typst,
                schrift_angabe=init_schrift,
                hoehe=init_hoehe,
                gewicht=init_gewicht,
                abstand="2pt",
            )
            erster_fliesstext_fertig = True
            if abstand_oben:
                absatz_typst = f"{abstand_oben}{absatz_typst}"
            typst_elemente.append(absatz_typst + "\n")
        else:
            if hat_einzug and fmt != "apa":
                absatz_typst = f"#h(3.8mm){absatz_typst}"

            nahtlos_verbinden = (
                leer_davor == 0
                and letztes_war_fliesstext
                and typst_elemente
                and not typst_elemente[-1].lstrip().startswith("#dropcap")
            )
            if nahtlos_verbinden:
                vorheriger_block = typst_elemente.pop().rstrip("\n")
                typst_elemente.append(f"{vorheriger_block} #linebreak()\n{absatz_typst}\n")
            else:
                if abstand_oben:
                    absatz_typst = f"{abstand_oben}{absatz_typst}"
                typst_elemente.append(absatz_typst + "\n")
            erster_fliesstext_fertig = True
        letztes_war_fliesstext = True

    if bilder:
        for bild_p in bilder:
            aufgeloest = bildpfad_aufloesen(bild_p, dokument_ordner=dokument_ordner)
            if aufgeloest:
                typst_elemente.append(abbildung_typst(aufgeloest, bildunterschrift_groesse=bildunterschrift_groesse))
            else:
                drucke_warnung(f"Übergebene Bilddatei nicht gefunden und übersprungen: {bild_p}")

    hat_einzuege = any(bool(p.get("has_indent", False)) for p in absaetze)
    return "\n".join(typst_elemente), alle_urls, explizite_bib_eintraege, bib_ueberschrift, hat_einzuege
