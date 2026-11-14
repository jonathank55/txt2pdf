# -*- coding: utf-8 -*-
"""Aufbau des vollständigen Typst-Quelltextes für Standardformate und APA 7."""

import os
import re
import time
from typing import List, Optional, Tuple

from .konfiguration import (
    FORMAT_PROFILE,
    RAND_ALIASE,
    RAND_VORGABEN,
)
from .markdown_typst import (
    textkoerper_zu_typst,
    typst_maskieren,
)
from .rtf_leser import rtf_zu_typst
from .schriftarten import (
    AUTOR_AKZENT_SCHRIFT,
    AUTOR_ATK1_SCHRIFT,
    schriftart_aufloesen,
    titel_schriftart_aufloesen,
    ueberschrift_schriftart_aufloesen,
)
from .textanalyse import (
    ist_autorenname,
    metadatenvorspann_trennen,
    sprachcode_fuer_typst,
    sprache_aus_dateiname,
    sprache_erkennen,
    titel_stimmt_ueberein,
    titel_und_autor_aus_dateiname,
    titel_und_autor_bereinigen,
)
from .uebersetzung import text_uebersetzen, textzeilen_uebersetzen
from .zitate import literaturverzeichnis_typst


def _raender_aufloesen(fmt: str, raender_arg: Optional[str]) -> Tuple[str, str, int]:
    """Löst die Seitenränder in (margin_x, margin_y, nutzbreite_mm) auf."""
    standard_schluessel = str(FORMAT_PROFILE.get(fmt, FORMAT_PROFILE["atk2"])["standard_raender"])
    margin_x, margin_y, nutzbreite = RAND_VORGABEN.get(standard_schluessel, RAND_VORGABEN["m"])

    if raender_arg is None:
        return margin_x, margin_y, nutzbreite

    roh = str(raender_arg).lower().strip()
    if roh in RAND_ALIASE:
        return RAND_VORGABEN[RAND_ALIASE[roh]]

    m_mass = re.match(r"^([0-9.]+)(mm|cm|pt|in)$", roh)
    if m_mass:
        wert = float(m_mass.group(1))
        einheit = m_mass.group(2)
        mx = f"{wert:g}{einheit}"
        my = f"{wert:g}{einheit}"
        if einheit == "mm":
            breite = max(100, int(210 - 2 * wert))
        elif einheit == "cm":
            breite = max(100, int(210 - 2 * wert * 10))
        else:
            breite = 178
        return mx, my, breite

    return margin_x, margin_y, nutzbreite


def _zeilenabstand_aufloesen(abstand_arg: Optional[str], standard_abstand: str) -> str:
    if abstand_arg is None:
        return standard_abstand
    s = str(abstand_arg).strip()
    m = re.match(r"^([0-9.]+)(em|pt|mm)?$", s)
    if not m:
        return s
    wert = float(m.group(1))
    einheit = m.group(2)
    if not einheit:
        return f"{wert * 0.35:g}em" if wert <= 2.5 else f"{wert}pt"
    return f"{wert:g}{einheit}"


def _sprach_beschriftungen(sprache: str) -> Tuple[str, str, str, str]:
    if sprache == "es":
        return "Referencias", "Página", "de", "POR "
    if sprache == "en":
        return "References", "Page", "of", "BY "
    return "Literaturverzeichnis", "Seite", "von", "VON "


def _klartext_aus_typst(typst_text: str) -> str:
    """Extrahiert reinen Lesetext aus erzeugtem Typst-Quelltext für die Spracherkennung."""
    if not typst_text:
        return ""
    ohne_direktiven = re.sub(r"(?m)^\s*#(?:set|show|let|import)\b.*$", " ", typst_text)
    bereinigt: List[str] = []
    i = 0
    n = len(ohne_direktiven)
    while i < n:
        if ohne_direktiven[i] == "#":
            j = i + 1
            while j < n and (ohne_direktiven[j].isalnum() or ohne_direktiven[j] in ("_", "-")):
                j += 1
            if j < n and ohne_direktiven[j] == "(":
                tiefe = 1
                k = j + 1
                in_anf = False
                while k < n and tiefe > 0:
                    ch = ohne_direktiven[k]
                    if ch == '"' and ohne_direktiven[k - 1] != "\\":
                        in_anf = not in_anf
                    elif not in_anf:
                        if ch == "(":
                            tiefe += 1
                        elif ch == ")":
                            tiefe -= 1
                    k += 1
                i = k
                bereinigt.append(" ")
                continue
            i = j
            bereinigt.append(" ")
            continue
        bereinigt.append(ohne_direktiven[i])
        i += 1
    text = "".join(bereinigt)
    text = re.sub(r"\\([#$@\[\]\*<>_])", r"\1", text)
    return re.sub(r"[\[\]]", " ", text)


def _effektive_sprache_ermitteln(
    zielsprache: Optional[str],
    rohtext: str,
    koerper_text: str,
    ist_rtf: bool,
    basisname: str,
    standard_sprache: str,
) -> str:
    """Ermittelt den gültigen Typst-Sprachcode für Dokumenttext und Beschriftungen."""
    if zielsprache:
        return sprachcode_fuer_typst(zielsprache, standard_sprache)
    sprach_text = _klartext_aus_typst(koerper_text) if ist_rtf else rohtext
    hinweis = sprache_aus_dateiname(basisname)
    return sprache_erkennen(sprach_text, standard_sprache, dateiname_hinweis=hinweis)


def _kopfbereich_typst_erstellen(
    fmt: str,
    dok_titel: str,
    dok_autor: Optional[str],
    dok_datum: Optional[str],
    titel_schrift: str,
    titelgroesse: str,
    zeilenabstand: str,
    max_titelbreite_mm: float,
    autor_praefix: str,
) -> str:
    """Erstellt die formatabhängige Vollbreite-Titelbox."""
    titel_esc = typst_maskieren(dok_titel)

    if fmt == "atk1":
        if dok_autor:
            sauber_a = dok_autor.strip()
            if not any(sauber_a.upper().startswith(p) for p in ("VON ", "BY ", "POR ")):
                sauber_a = f"{autor_praefix}{sauber_a}"
            autor_text = sauber_a.upper()
            autor_inline = (
                f"#v(calc.max(3mm, best-sz * 0.32))\n"
                f'        #block[#text(font: {AUTOR_ATK1_SCHRIFT}, size: 8.5pt, weight: "regular", tracking: 0.08em, fill: rgb("#000000"))[{typst_maskieren(autor_text)}]]'
            )
            if dok_datum:
                autor_inline += (
                    f"\n        #v(1.0mm)\n"
                    f'        #block[#text(font: {AUTOR_ATK1_SCHRIFT}, size: 7.5pt, fill: rgb("#000000"))[{typst_maskieren(dok_datum)}]]'
                )
        else:
            autor_inline = ""
            if dok_datum:
                autor_inline = (
                    f"\n        #v(1.0mm)\n"
                    f'        #block[#text(font: {AUTOR_ATK1_SCHRIFT}, size: 7.5pt, fill: rgb("#000000"))[{typst_maskieren(dok_datum)}]]'
                )

        return f"""// Vollbreite-Titelbox mit Trennlinie (atk1)
#place(top, scope: "parent", float: true)[
  #block(width: 100%, inset: (bottom: 2.5mm))[
    #show "_": "_" + sym.zws
    #show "/": "/" + sym.zws
    #context {{
      let max-w = {max_titelbreite_mm}mm
      let low = 10.0
      let high = 120.0
      for _ in range(16) {{
        let mid = (low + high) / 2.0
        let m = measure(text(font: {titel_schrift}, size: mid * 1pt, weight: "bold", hyphenate: false)[#strong[{titel_esc}]])
        if m.width <= max-w {{
          low = mid
        }} else {{
          high = mid
        }}
      }}
      let best-sz = low * 1pt
      align(center)[
        #block(width: 100%)[
          #set text(font: {titel_schrift}, size: best-sz, weight: "bold", hyphenate: false, fill: rgb("#000000"))
          #set par(justify: false, leading: {zeilenabstand})
          #strong[{titel_esc}]
        ]
        {autor_inline}
      ]
      v(calc.max(1.5mm, best-sz * 0.30))
      line(length: 100%, stroke: 0.3pt + rgb("#000000"))
    }}
  ]
]
"""

    if fmt in ("atk2", "atk3"):
        autor_block = ""
        if dok_autor:
            sauber_a = dok_autor.strip()
            if not any(sauber_a.upper().startswith(p) for p in ("VON ", "BY ", "POR ")):
                sauber_a = f"{autor_praefix}{sauber_a}"
            autor_text = sauber_a.upper()
            autor_block = (
                f"\n        #v(2.5mm)\n"
                f'        #block[#text(font: {AUTOR_AKZENT_SCHRIFT}, size: 8.5pt, weight: "regular", tracking: 0.08em, fill: rgb("#000000"))[{typst_maskieren(autor_text)}]]'
            )
        datum_block = (
            f'\n        #v(1.0mm)\n        #block[#text(size: 8pt, fill: rgb("#000000"))[{typst_maskieren(dok_datum)}]]'
            if dok_datum
            else ""
        )
        return f"""// Vollbreite-Titelbox ohne Trennlinie ({fmt})
#place(top, scope: "parent", float: true)[
  #block(width: 100%, inset: (bottom: 6.8mm))[
    #show "_": "_" + sym.zws
    #show "/": "/" + sym.zws
    #align(center)[
      #block(width: 100%)[
        #set text(font: {titel_schrift}, size: {titelgroesse}, weight: "bold", hyphenate: false, fill: rgb("#000000"))
        #set par(justify: false, leading: {zeilenabstand})
        #strong[{titel_esc}]
      ]{autor_block}{datum_block}
    ]
  ]
]
"""

    autor_block = ""
    if dok_autor:
        sauber_a = dok_autor.strip()
        m_von = re.match(r"^(?:von|by|por)\s+(.+)$", sauber_a, re.IGNORECASE)
        if m_von and ist_autorenname(m_von.group(1).strip()):
            sauber_a = m_von.group(1).strip()
        autor_block = (
            f'\n        #v(1.4mm)\n'
            f'        #block[#text(style: "italic", weight: "regular", fill: rgb("#000000"))[{typst_maskieren(sauber_a)}]]'
        )

    if dok_datum:
        kopf_inhalt = f"""#grid(
      columns: (1fr, auto),
      gutter: 6mm,
      align: (left + horizon, right + horizon),
      [
        #block(width: 100%)[
          #set text(font: {titel_schrift}, size: {titelgroesse}, weight: "bold", hyphenate: false, fill: rgb("#000000"))
          #set par(justify: false, leading: {zeilenabstand})
          #strong[{titel_esc}]
        ]{autor_block}
      ],
      [
        #text(fill: rgb("#000000"))[{typst_maskieren(dok_datum)}]
      ]
    )"""
    else:
        kopf_inhalt = f"""#align(left)[
      #block(width: 100%)[
        #set text(font: {titel_schrift}, size: {titelgroesse}, weight: "bold", hyphenate: false, fill: rgb("#000000"))
        #set par(justify: false, leading: {zeilenabstand})
        #strong[{titel_esc}]
      ]{autor_block}
    ]"""

    return f"""// Vollbreite-Titelbox ({fmt})
#place(top, scope: "parent", float: true)[
  #block(width: 100%, inset: (bottom: 2.5mm))[
    #show "_": "_" + sym.zws
    #show "/": "/" + sym.zws
    {kopf_inhalt}
  ]
]
"""


def _abschnitt_ueberschrift_makro(
    basis_groesse: str,
    zeilenabstand: str,
    zusatz_par: str = "",
) -> str:
    """Erzeugt das gemeinsame Typst-Makro für Abschnittsüberschriften."""
    return f"""#let render_section_heading(
  h_content,
  align_center: true,
  font_attr: none,
  font_size: none,
  above_gap: 2.8em,
  below_gap: 2.8em
) = {{
  let h_align = if align_center {{ center }} else {{ left }}
  let h_size = if font_size != none {{ font_size }} else {{ {basis_groesse} }}
  block(width: 100%, breakable: false, sticky: true, above: above_gap, below: below_gap)[
    #show "_": "_" + sym.zws
    #show "/": "/" + sym.zws
    #align(h_align)[
      #set par(justify: false, leading: {zeilenabstand}{zusatz_par})
      #if font_attr != none [
        #set text(font: font_attr, size: h_size, weight: "bold", hyphenate: false, fill: rgb("#000000"))
        #h_content
      ] else [
        #set text(size: h_size, weight: "bold", hyphenate: false, fill: rgb("#000000"))
        #h_content
      ]
    ]
  ]
}}"""


def _inhalt_und_quellen_vorbereiten(
    abs_eingabe: str,
    fmt: str,
    basisname: str,
    titel: Optional[str],
    autor: Optional[str],
    datum: Optional[str],
    standard_autor: Optional[str],
    standard_datum: Optional[str],
    titelgroesse: str,
    bildunterschrift_groesse: str,
    initial_verwenden: bool,
    titel_schrift: str,
    ueberschrift_schrift: Optional[str],
    zeilenabstand: str,
    bilder: Optional[List[str]],
    zielsprache: Optional[str],
) -> Tuple[str, str, Optional[str], Optional[str], List[str], List[str], Optional[str], bool, bool, str, str]:
    """Bereitet Textkörper, bereinigte Metadaten, URLs, Quellen und Rohtext gemeinsam für Standard und APA auf."""
    datei_titel, datei_autor = titel_und_autor_aus_dateiname(basisname)
    ist_rtf = abs_eingabe.lower().endswith((".rtf", ".rtfd"))
    rohtext = ""

    if ist_rtf:
        (
            koerper_text,
            urls,
            gefundener_titel,
            gefundener_autor,
            gefundenes_datum,
            explizite_bib,
            bib_ueberschrift,
            hat_einzuege,
        ) = rtf_zu_typst(
            abs_eingabe,
            erwarteter_titel=titel or datei_titel or basisname,
            erwarteter_autor=autor or datei_autor or standard_autor,
            erwartetes_datum=datum or standard_datum,
            bilder=bilder,
            bildunterschrift_groesse=bildunterschrift_groesse,
            titelgroesse=titelgroesse,
            initial_verwenden=initial_verwenden,
            titel_schrift=titel_schrift,
            fmt=fmt,
            zeilenabstand=zeilenabstand,
            ueberschrift_schrift=ueberschrift_schrift,
        )
        roh_titel = titel or datei_titel or basisname
        ziel_autor = autor or datei_autor or gefundener_autor or standard_autor
        dok_datum = datum or gefundenes_datum or standard_datum
        dok_titel, dok_autor = titel_und_autor_bereinigen(roh_titel, ziel_autor, ersatz_autor=datei_autor)
        klartext_kontext = koerper_text
    else:
        with open(abs_eingabe, "r", encoding="utf-8", errors="replace") as f:
            rohtext = f.read()

        dok_ordner = os.path.dirname(abs_eingabe)
        bekannter_titel = titel or datei_titel or basisname
        gefundener_titel, gefundener_autor, gefundenes_datum, koerper_zeilen = metadatenvorspann_trennen(
            rohtext,
            standard_autor=autor,
            standard_datum=datum,
            bekannter_titel=bekannter_titel,
        )

        roh_titel = titel or datei_titel or basisname
        ziel_autor = autor or datei_autor or gefundener_autor or standard_autor
        dok_datum = datum or gefundenes_datum or standard_datum
        dok_titel, dok_autor = titel_und_autor_bereinigen(roh_titel, ziel_autor, ersatz_autor=datei_autor)

        if gefundener_titel and not titel_stimmt_ueberein(gefundener_titel, dok_titel):
            koerper_zeilen = [gefundener_titel, ""] + list(koerper_zeilen)
        if gefundener_autor and (not dok_autor or gefundener_autor.lower().strip() != dok_autor.lower().strip()):
            koerper_zeilen = [gefundener_autor, ""] + list(koerper_zeilen)

        if zielsprache:
            trans_ziel = zielsprache.lower().strip()
            if dok_titel:
                dok_titel = text_uebersetzen(dok_titel, zielsprache=trans_ziel)
            koerper_zeilen = textzeilen_uebersetzen(koerper_zeilen, zielsprache=trans_ziel)

        koerper_text, urls, explizite_bib, bib_ueberschrift, hat_einzuege = textkoerper_zu_typst(
            koerper_zeilen,
            bilder=bilder,
            bildunterschrift_groesse=bildunterschrift_groesse,
            initial_verwenden=initial_verwenden,
            dokument_ordner=dok_ordner,
            titel_schrift=titel_schrift,
            ueberschrift_schrift=ueberschrift_schrift,
            fmt=fmt,
        )
        klartext_kontext = rohtext

    return (
        koerper_text,
        dok_titel,
        dok_autor,
        dok_datum,
        urls,
        explizite_bib,
        bib_ueberschrift,
        hat_einzuege,
        ist_rtf,
        rohtext,
        klartext_kontext,
    )


def apa_typst_erzeugen(
    eingabepfad: str,
    titel: Optional[str] = None,
    autor: Optional[str] = None,
    datum: Optional[str] = None,
    institution: str = "California Lutheran University",
    kurs: Optional[str] = None,
    dozent: Optional[str] = None,
    schrift_arg: Optional[str] = None,
    bilder: Optional[List[str]] = None,
    zielsprache: Optional[str] = None,
) -> str:
    """Erstellt den vollständigen Typst-Quelltext für ein APA-7-Dokument."""
    abs_eingabe = os.path.abspath(eingabepfad)
    basisname = os.path.splitext(os.path.basename(abs_eingabe))[0]
    schrift_angabe, _ = schriftart_aufloesen(schrift_arg, "apa")

    (
        apa_koerper,
        dok_titel,
        dok_autor,
        dok_datum,
        urls,
        explizite_bib,
        bib_ueberschrift,
        _,
        ist_rtf,
        rohtext,
        klartext_kontext,
    ) = _inhalt_und_quellen_vorbereiten(
        abs_eingabe=abs_eingabe,
        fmt="apa",
        basisname=basisname,
        titel=titel,
        autor=autor,
        datum=datum,
        standard_autor="Jonathan Klatchko",
        standard_datum=time.strftime("%B %d, %Y"),
        titelgroesse="12pt",
        bildunterschrift_groesse="10pt",
        initial_verwenden=False,
        titel_schrift=schrift_angabe,
        ueberschrift_schrift=schrift_angabe,
        zeilenabstand="1.15em",
        bilder=bilder,
        zielsprache=zielsprache,
    )

    effektive_sprache = _effektive_sprache_ermitteln(
        zielsprache=zielsprache,
        rohtext=rohtext,
        koerper_text=apa_koerper,
        ist_rtf=ist_rtf,
        basisname=basisname,
        standard_sprache="en",
    )
    standard_bib_titel, _, _, _ = _sprach_beschriftungen(effektive_sprache)
    end_bib_titel = bib_ueberschrift or ("References" if effektive_sprache == "en" else standard_bib_titel)

    apa_quellen = literaturverzeichnis_typst(
        urls=urls,
        explizite_eintraege=explizite_bib,
        bib_titel=end_bib_titel,
        schrift_angabe=schrift_angabe,
        schriftgroesse="12pt",
        titelgroesse="12pt",
        kontext_text=klartext_kontext,
        haengender_einzug="12.7mm",
        zeilenabstand="1.15em",
        koerper_einzug_nutzen=False,
        trennlinie_anzeigen=False,
        titel_schrift=schrift_angabe,
        fmt="apa",
    )
    if apa_quellen:
        apa_quellen = f"\n#pagebreak()\n{apa_quellen}"

    makro_block = _abschnitt_ueberschrift_makro("12pt", "1.15em", ", first-line-indent: 0pt")
    kurs_zeile = f"  #text()[{typst_maskieren(kurs)}]\n" if kurs else ""
    dozent_zeile = f"  #text()[{typst_maskieren(dozent)}]\n" if dozent else ""

    return f"""#show link: set text(fill: rgb("#0b57d0"))
#set page(
  paper: "us-letter",
  margin: (x: 25.4mm, top: 25.4mm, bottom: 25.4mm),
  header: context [
    #align(right)[#text(font: {schrift_angabe}, size: 12pt)[#counter(page).display()]]
  ]
)
#set text(
  font: {schrift_angabe},
  size: 12pt,
  weight: "regular",
  lang: "{effektive_sprache}"
)
#set par(
  justify: false,
  leading: 1.15em,
  spacing: 1.15em,
  first-line-indent: 12.7mm
)

#show heading: it => {{
  set par(leading: 1.15em, first-line-indent: 0pt)
  it
}}

{makro_block}

// APA 7 Titelseite
#v(72pt)
#align(center)[
  #show "_": "_" + sym.zws
  #show "/": "/" + sym.zws
  #set par(justify: false, leading: 1.15em, first-line-indent: 0pt)
  #text(weight: "bold", hyphenate: false)[{typst_maskieren(dok_titel)}]
  #v(24pt)
  #text()[{typst_maskieren(dok_autor or "")}]
  #linebreak()
  #text()[{typst_maskieren(institution)}]
{kurs_zeile}{dozent_zeile}  #linebreak()
  #text()[{typst_maskieren(dok_datum or "")}]
]

#pagebreak()

#align(center)[
  #show "_": "_" + sym.zws
  #show "/": "/" + sym.zws
  #set par(justify: false, leading: 1.15em, first-line-indent: 0pt)
  #text(weight: "bold", hyphenate: false)[{typst_maskieren(dok_titel)}]
]
#v(1.2em)

{apa_koerper}
{apa_quellen}
"""


def standard_typst_erzeugen(
    eingabepfad: str,
    fmt: str,
    titel: Optional[str] = None,
    autor: Optional[str] = None,
    datum: Optional[str] = None,
    sprache: str = "de",
    schriftgroesse: Optional[str] = None,
    zeilenabstand: Optional[str] = None,
    spaltensteg: Optional[str] = None,
    bilder: Optional[List[str]] = None,
    schrift_arg: Optional[str] = None,
    spalten: Optional[int] = None,
    initial_verwenden: Optional[bool] = None,
    zielsprache: Optional[str] = None,
    raender: Optional[str] = None,
    linksbuendig: bool = False,
) -> str:
    """Erstellt den vollständigen Typst-Quelltext für atk1, atk2, atk3, br1 und br2."""
    abs_eingabe = os.path.abspath(eingabepfad)
    basisname = os.path.splitext(os.path.basename(abs_eingabe))[0]
    profil = FORMAT_PROFILE.get(fmt, FORMAT_PROFILE["atk2"])

    end_spalten = spalten if spalten is not None else int(profil["spalten"])  # type: ignore[arg-type]
    end_initial = initial_verwenden if initial_verwenden is not None else bool(profil["initial"])
    end_steg = spaltensteg if spaltensteg is not None else str(profil["spaltensteg"])
    end_abstand = _zeilenabstand_aufloesen(zeilenabstand, str(profil["zeilenabstand"]))

    roh_groesse = schriftgroesse if schriftgroesse is not None else f"{profil['schriftgroesse_pt']}pt"
    m_pt = re.search(r"([\d.]+)", str(roh_groesse))
    basis_pt = max(6.0, min(float(m_pt.group(1)) if m_pt else float(profil["schriftgroesse_pt"]), 12.0))  # type: ignore[arg-type]
    end_schriftgroesse = f"{basis_pt:g}pt"

    if fmt == "atk1":
        titelgroesse = "36pt"
    elif fmt == "atk2":
        titelgroesse = f"{basis_pt + 18.0:g}pt"
    elif fmt == "atk3":
        titelgroesse = f"{basis_pt + 10.0:g}pt"
    else:
        titelgroesse = f"{basis_pt + 6.0:g}pt"
    bildunterschrift_groesse = f"{max(basis_pt - 2.0, 3.0):g}pt"
    haengender_einzug = "12.7mm" if end_spalten == 1 else "6mm"

    koerper_schrift, _ = schriftart_aufloesen(schrift_arg, fmt)
    titel_schrift = titel_schriftart_aufloesen(fmt, koerper_schrift)
    ueberschrift_schrift = ueberschrift_schriftart_aufloesen(fmt, koerper_schrift)

    (
        koerper_text,
        dok_titel,
        dok_autor,
        dok_datum,
        urls,
        explizite_bib,
        bib_ueberschrift,
        hat_einzuege,
        ist_rtf,
        rohtext,
        klartext_kontext,
    ) = _inhalt_und_quellen_vorbereiten(
        abs_eingabe=abs_eingabe,
        fmt=fmt,
        basisname=basisname,
        titel=titel,
        autor=autor,
        datum=datum,
        standard_autor=None,
        standard_datum=None,
        titelgroesse=titelgroesse,
        bildunterschrift_groesse=bildunterschrift_groesse,
        initial_verwenden=end_initial,
        titel_schrift=titel_schrift,
        ueberschrift_schrift=ueberschrift_schrift,
        zeilenabstand=end_abstand,
        bilder=bilder,
        zielsprache=zielsprache,
    )

    margin_x, margin_y, nutzbreite_mm = _raender_aufloesen(fmt, raender)
    max_titelbreite = round(nutzbreite_mm * 0.85, 1)

    effektive_sprache = _effektive_sprache_ermitteln(
        zielsprache=zielsprache,
        rohtext=rohtext,
        koerper_text=koerper_text,
        ist_rtf=ist_rtf,
        basisname=basisname,
        standard_sprache=sprache,
    )
    standard_bib_titel, seite_wort, von_wort, autor_praefix = _sprach_beschriftungen(effektive_sprache)
    end_bib_titel = bib_ueberschrift or standard_bib_titel
    bib_titelgroesse = f"{basis_pt + 4.0:g}pt"

    literatur_typst = literaturverzeichnis_typst(
        urls=urls,
        explizite_eintraege=explizite_bib,
        bib_titel=end_bib_titel,
        schrift_angabe=koerper_schrift,
        schriftgroesse=end_schriftgroesse,
        titelgroesse=bib_titelgroesse,
        kontext_text=klartext_kontext,
        haengender_einzug=haengender_einzug,
        zeilenabstand=end_abstand,
        koerper_einzug_nutzen=hat_einzuege,
        trennlinie_anzeigen=(fmt not in ("atk2", "atk3", "br1", "br2")),
        titel_schrift=titel_schrift,
        fmt=fmt,
    )

    spalten_direktive = f"#set columns(gutter: {end_steg})\n" if end_spalten > 1 else ""
    kopfbox = "" if ist_rtf else _kopfbereich_typst_erstellen(
        fmt=fmt,
        dok_titel=dok_titel,
        dok_autor=dok_autor,
        dok_datum=dok_datum,
        titel_schrift=titel_schrift,
        titelgroesse=titelgroesse,
        zeilenabstand=end_abstand,
        max_titelbreite_mm=max_titelbreite,
        autor_praefix=autor_praefix,
    )
    blocksatz_direktive = "false" if linksbuendig else "true"
    makro_block = _abschnitt_ueberschrift_makro(end_schriftgroesse, end_abstand)

    return f"""#import "@preview/droplet:0.3.1": dropcap

#show link: set text(fill: rgb("#000000"))
#show "_": "_" + sym.zws
#show "/": "/" + sym.zws

#set page(
  paper: "a4",
  margin: (x: {margin_x}, top: {margin_y}, bottom: {margin_y}),
  columns: {end_spalten},
  header: none,
  footer: context {{
    let page_num = counter(page).get().first()
    let total_pages = counter(page).final().first()
    if total_pages > 1 [
      #align(center)[
        #text(size: 8.5pt, fill: rgb("#000000"))[{seite_wort} #page_num {von_wort} #total_pages]
      ]
    ]
  }}
)

{spalten_direktive}#set text(
  font: {koerper_schrift},
  size: {end_schriftgroesse},
  weight: "regular",
  lang: "{effektive_sprache}",
  hyphenate: true,
  costs: (hyphenation: 50%, orphan: 150%, widow: 150%)
)

#set par(
  justify: {blocksatz_direktive},
  leading: {end_abstand},
  spacing: {end_abstand},
  first-line-indent: 0pt,
  linebreaks: "optimized"
)

#show heading: it => {{
  set par(leading: {end_abstand})
  it
}}

{makro_block}

{kopfbox}
{koerper_text}

{literatur_typst}
"""
