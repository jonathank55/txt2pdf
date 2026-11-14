# -*- coding: utf-8 -*-
"""Verwaltung der quelloffenen Schriftarten im Programmordner und deren Typst-Zuordnung."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import shutil
import subprocess
from typing import Dict, List, Optional, Set, Tuple
import urllib.parse
import urllib.request

from .ausgabe import drucke_hinweis, drucke_warnung
from .konfiguration import SCHRIFTARTEN_ORDNER

GOOGLE_FONTS_BASIS = "https://raw.githubusercontent.com/google/fonts/main"

# Jede Schriftart enthält:
# - anzeigename: Lesbarer Name der quelloffenen Schriftfamilie
# - typst_angabe: Typst-Tupel ausschließlich aus Schriften, die in Schriftarten/ liegen
# - typ: "Serifen", "Serifenlos", "Dicktengleich" oder "Zierschrift"
# - ersatz_fuer: Welche proprietären Vorbilder damit abgebildet werden
# - quelle: (Unterordner, Repo-Pfad, [Dateien])
SCHRIFTARTEN_KATALOG: Dict[str, Dict[str, object]] = {
    "faustina": {
        "anzeigename": "Faustina",
        "typst_angabe": '("Faustina", "EB Garamond", "PT Serif")',
        "typ": "Serifen",
        "ersatz_fuer": "Faustina (Original)",
        "quelle": ("Faustina", "ofl/faustina", ["Faustina[wght].ttf", "Faustina-Italic[wght].ttf"]),
    },
    "open sans": {
        "anzeigename": "Open Sans",
        "typst_angabe": '("Open Sans", "Inter", "Roboto")',
        "typ": "Serifenlos",
        "ersatz_fuer": "Amazon Ember, Lucida Grande",
        "quelle": ("OpenSans", "ofl/opensans", ["OpenSans[wdth,wght].ttf", "OpenSans-Italic[wdth,wght].ttf"]),
    },
    "ibm plex sans": {
        "anzeigename": "IBM Plex Sans",
        "typst_angabe": '("IBM Plex Sans", "Open Sans", "Roboto")',
        "typ": "Serifenlos",
        "ersatz_fuer": "Neutrale Arbeitsschrift (Serifenlos)",
        "quelle": ("IBMPlexSans", "ofl/ibmplexsans", ["IBMPlexSans[wdth,wght].ttf", "IBMPlexSans-Italic[wdth,wght].ttf"]),
    },
    "tinos": {
        "anzeigename": "Tinos",
        "typst_angabe": '("Tinos", "PT Serif")',
        "typ": "Serifen",
        "ersatz_fuer": "Times New Roman",
        "quelle": ("Tinos", "ofl/tinos", ["Tinos-Regular.ttf", "Tinos-Bold.ttf", "Tinos-Italic.ttf", "Tinos-BoldItalic.ttf"]),
    },
    "eb garamond": {
        "anzeigename": "EB Garamond",
        "typst_angabe": '("EB Garamond", "Cormorant Garamond", "PT Serif")',
        "typ": "Serifen",
        "ersatz_fuer": "Garamond",
        "quelle": ("EBGaramond", "ofl/ebgaramond", ["EBGaramond[wght].ttf", "EBGaramond-Italic[wght].ttf"]),
    },
    "cormorant garamond": {
        "anzeigename": "Cormorant Garamond",
        "typst_angabe": '("Cormorant Garamond", "EB Garamond", "PT Serif")',
        "typ": "Serifen",
        "ersatz_fuer": "Klassische Garamond-Zierschrift",
        "quelle": ("CormorantGaramond", "ofl/cormorantgaramond", ["CormorantGaramond[wght].ttf", "CormorantGaramond-Italic[wght].ttf"]),
    },
    "pt serif": {
        "anzeigename": "PT Serif",
        "typst_angabe": '("PT Serif", "EB Garamond", "Tinos")',
        "typ": "Serifen",
        "ersatz_fuer": "PT Serif (Original)",
        "quelle": ("PTSerif", "ofl/ptserif", ["PT_Serif-Web-Regular.ttf", "PT_Serif-Web-Bold.ttf", "PT_Serif-Web-Italic.ttf", "PT_Serif-Web-BoldItalic.ttf"]),
    },
    "bitter": {
        "anzeigename": "Bitter",
        "typst_angabe": '("Bitter", "PT Serif")',
        "typ": "Serifen",
        "ersatz_fuer": "Kefa III",
        "quelle": ("Bitter", "ofl/bitter", ["Bitter[wght].ttf", "Bitter-Italic[wght].ttf"]),
    },
    "literata": {
        "anzeigename": "Literata",
        "typst_angabe": '("Literata", "PT Serif")',
        "typ": "Serifen",
        "ersatz_fuer": "Literaria / Literata (Original)",
        "quelle": ("Literata", "ofl/literata", ["Literata[opsz,wght].ttf", "Literata-Italic[opsz,wght].ttf"]),
    },
    "jost": {
        "anzeigename": "Jost",
        "typst_angabe": '("Jost", "Inter", "Roboto")',
        "typ": "Serifenlos",
        "ersatz_fuer": "Futura",
        "quelle": ("Jost", "ofl/jost", ["Jost[wght].ttf", "Jost-Italic[wght].ttf"]),
    },
    "gfs didot": {
        "anzeigename": "GFS Didot",
        "typst_angabe": '("GFS Didot", "Bodoni Moda", "Libre Bodoni", "PT Serif")',
        "typ": "Zierschrift",
        "ersatz_fuer": "Didot",
        "quelle": ("GFSDidot", "ofl/gfsdidot", ["GFSDidot-Regular.ttf"]),
    },
    "bodoni moda": {
        "anzeigename": "Bodoni Moda",
        "typst_angabe": '("Bodoni Moda", "Libre Bodoni", "PT Serif")',
        "typ": "Zierschrift",
        "ersatz_fuer": "Bodoni 72 / Bodoni",
        "quelle": ("BodoniModa", "ofl/bodonimoda", ["BodoniModa[opsz,wght].ttf", "BodoniModa-Italic[opsz,wght].ttf"]),
    },
    "libre bodoni": {
        "anzeigename": "Libre Bodoni",
        "typst_angabe": '("Libre Bodoni", "Bodoni Moda", "PT Serif")',
        "typ": "Zierschrift",
        "ersatz_fuer": "Bodoni",
        "quelle": ("LibreBodoni", "ofl/librebodoni", ["LibreBodoni[wght].ttf", "LibreBodoni-Italic[wght].ttf"]),
    },
    "libre baskerville": {
        "anzeigename": "Libre Baskerville",
        "typst_angabe": '("Libre Baskerville", "PT Serif")',
        "typ": "Serifen",
        "ersatz_fuer": "Baskerville",
        "quelle": ("LibreBaskerville", "ofl/librebaskerville", ["LibreBaskerville[wght].ttf", "LibreBaskerville-Italic[wght].ttf"]),
    },
    "libre caslon text": {
        "anzeigename": "Libre Caslon Text",
        "typst_angabe": '("Libre Caslon Text", "Libre Caslon Display", "PT Serif")',
        "typ": "Serifen",
        "ersatz_fuer": "Big Caslon",
        "quelle": ("LibreCaslonText", "ofl/librecaslontext", ["LibreCaslonText[wght].ttf", "LibreCaslonText-Italic[wght].ttf"]),
    },
    "libre caslon display": {
        "anzeigename": "Libre Caslon Display",
        "typst_angabe": '("Libre Caslon Display", "Libre Caslon Text", "PT Serif")',
        "typ": "Zierschrift",
        "ersatz_fuer": "Big Caslon Display",
        "quelle": ("LibreCaslonDisplay", "ofl/librecaslondisplay", ["LibreCaslonDisplay-Regular.ttf"]),
    },
    "playfair display": {
        "anzeigename": "Playfair Display",
        "typst_angabe": '("Playfair Display", "Libre Baskerville", "PT Serif")',
        "typ": "Zierschrift",
        "ersatz_fuer": "Playfair Display (Original)",
        "quelle": ("PlayfairDisplay", "ofl/playfairdisplay", ["PlayfairDisplay[wght].ttf", "PlayfairDisplay-Italic[wght].ttf"]),
    },
    "crimson pro": {
        "anzeigename": "Crimson Pro",
        "typst_angabe": '("Crimson Pro", "EB Garamond", "PT Serif")',
        "typ": "Serifen",
        "ersatz_fuer": "Cochin",
        "quelle": ("CrimsonPro", "ofl/crimsonpro", ["CrimsonPro[wght].ttf", "CrimsonPro-Italic[wght].ttf"]),
    },
    "fraunces": {
        "anzeigename": "Fraunces",
        "typst_angabe": '("Fraunces", "Faustina", "PT Serif")',
        "typ": "Zierschrift",
        "ersatz_fuer": "Canela Text",
        "quelle": ("Fraunces", "ofl/fraunces", ["Fraunces[SOFT,WONK,opsz,wght].ttf", "Fraunces-Italic[SOFT,WONK,opsz,wght].ttf"]),
    },
    "newsreader": {
        "anzeigename": "Newsreader",
        "typst_angabe": '("Newsreader 16pt", "PT Serif")',
        "typ": "Serifen",
        "ersatz_fuer": "Publico Text",
        "quelle": ("Newsreader", "ofl/newsreader", ["Newsreader[opsz,wght].ttf", "Newsreader-Italic[opsz,wght].ttf"]),
    },
    "charis sil": {
        "anzeigename": "Charis SIL",
        "typst_angabe": '("Charis SIL", "PT Serif")',
        "typ": "Serifen",
        "ersatz_fuer": "Charter",
        "quelle": ("CharisSIL", "ofl/charissil", ["CharisSIL-Regular.ttf", "CharisSIL-Bold.ttf", "CharisSIL-Italic.ttf", "CharisSIL-BoldItalic.ttf"]),
    },
    "lora": {
        "anzeigename": "Lora",
        "typst_angabe": '("Lora", "Literata", "PT Serif")',
        "typ": "Serifen",
        "ersatz_fuer": "Iowan Old Style",
        "quelle": ("Lora", "ofl/lora", ["Lora[wght].ttf", "Lora-Italic[wght].ttf"]),
    },
    "arsenal": {
        "anzeigename": "Arsenal",
        "typst_angabe": '("Arsenal", "Philosopher", "Open Sans")',
        "typ": "Serifenlos",
        "ersatz_fuer": "Optima",
        "quelle": ("Arsenal", "ofl/arsenal", ["Arsenal-Regular.ttf", "Arsenal-Bold.ttf", "Arsenal-Italic.ttf", "Arsenal-BoldItalic.ttf"]),
    },
    "philosopher": {
        "anzeigename": "Philosopher",
        "typst_angabe": '("Philosopher", "Arsenal", "Open Sans")',
        "typ": "Serifenlos",
        "ersatz_fuer": "Optima (Variante)",
        "quelle": ("Philosopher", "ofl/philosopher", ["Philosopher-Regular.ttf", "Philosopher-Bold.ttf", "Philosopher-Italic.ttf", "Philosopher-BoldItalic.ttf"]),
    },
    "nunito sans": {
        "anzeigename": "Nunito Sans",
        "typst_angabe": '("Nunito Sans 12pt", "Open Sans", "Roboto")',
        "typ": "Serifenlos",
        "ersatz_fuer": "Avenir Next",
        "quelle": ("NunitoSans", "ofl/nunitosans", ["NunitoSans[YTLC,opsz,wdth,wght].ttf", "NunitoSans-Italic[YTLC,opsz,wdth,wght].ttf"]),
    },
    "cabin": {
        "anzeigename": "Cabin",
        "typst_angabe": '("Cabin", "Open Sans", "Roboto")',
        "typ": "Serifenlos",
        "ersatz_fuer": "Gill Sans",
        "quelle": ("Cabin", "ofl/cabin", ["Cabin[wdth,wght].ttf", "Cabin-Italic[wdth,wght].ttf"]),
    },
    "pt sans": {
        "anzeigename": "PT Sans",
        "typst_angabe": '("PT Sans", "Open Sans", "Roboto")',
        "typ": "Serifenlos",
        "ersatz_fuer": "Verdana",
        "quelle": ("PTSans", "ofl/ptsans", ["PT_Sans-Web-Regular.ttf", "PT_Sans-Web-Bold.ttf", "PT_Sans-Web-Italic.ttf", "PT_Sans-Web-BoldItalic.ttf"]),
    },
    "inter": {
        "anzeigename": "Inter",
        "typst_angabe": '("Inter", "Arimo", "Roboto")',
        "typ": "Serifenlos",
        "ersatz_fuer": "Helvetica Neue, Calibre",
        "quelle": ("Inter", "ofl/inter", ["Inter[opsz,wght].ttf", "Inter-Italic[opsz,wght].ttf"]),
    },
    "arimo": {
        "anzeigename": "Arimo",
        "typst_angabe": '("Arimo", "Inter", "Roboto")',
        "typ": "Serifenlos",
        "ersatz_fuer": "Arial",
        "quelle": ("Arimo", "ofl/arimo", ["Arimo[wght].ttf", "Arimo-Italic[wght].ttf"]),
    },
    "roboto": {
        "anzeigename": "Roboto",
        "typst_angabe": '("Roboto", "Inter", "Open Sans")',
        "typ": "Serifenlos",
        "ersatz_fuer": "Roboto (Original)",
        "quelle": ("Roboto", "ofl/roboto", ["Roboto[wdth,wght].ttf", "Roboto-Italic[wdth,wght].ttf"]),
    },
    "jetbrains mono": {
        "anzeigename": "JetBrains Mono",
        "typst_angabe": '("JetBrains Mono", "PT Mono")',
        "typ": "Dicktengleich",
        "ersatz_fuer": "Monaco, Menlo",
        "quelle": ("JetBrainsMono", "ofl/jetbrainsmono", ["JetBrainsMono[wght].ttf", "JetBrainsMono-Italic[wght].ttf"]),
    },
    "pt mono": {
        "anzeigename": "PT Mono",
        "typst_angabe": '("PT Mono", "JetBrains Mono")',
        "typ": "Dicktengleich",
        "ersatz_fuer": "Courier New",
        "quelle": ("PTMono", "ofl/ptmono", ["PTM55FT.ttf"]),
    },
    "noto serif malayalam": {
        "anzeigename": "Noto Serif Malayalam",
        "typst_angabe": '("Noto Serif Malayalam", "PT Serif")',
        "typ": "Serifen",
        "ersatz_fuer": "Malayalam MN",
        "quelle": ("NotoSerifMalayalam", "ofl/notoserifmalayalam", ["NotoSerifMalayalam[wght].ttf"]),
    },
    "mukta mahee": {
        "anzeigename": "Mukta Mahee",
        "typst_angabe": '("Mukta Mahee", "Roboto")',
        "typ": "Serifenlos",
        "ersatz_fuer": "Mukta Mahee (Original)",
        "quelle": ("MuktaMahee", "ofl/muktamahee", ["MuktaMahee-Regular.ttf", "MuktaMahee-Bold.ttf"]),
    },
}

# Zuordnung klassischer bzw. abgekürzter Namen auf die quelloffenen Einträge.
SCHRIFT_ALIASE: Dict[str, str] = {
    "kefa iii": "bitter",
    "kefa": "bitter",
    "kefaiii": "bitter",
    "times new roman": "tinos",
    "times": "tinos",
    "ptserif": "pt serif",
    "serif": "pt serif",
    "optima": "arsenal",
    "sans": "roboto",
    "monaco": "jetbrains mono",
    "mono": "jetbrains mono",
    "menlo": "jetbrains mono",
    "courier": "pt mono",
    "courier new": "pt mono",
    "didot": "gfs didot",
    "gfsdidot": "gfs didot",
    "cochin": "crimson pro",
    "crimson": "crimson pro",
    "big caslon": "libre caslon text",
    "caslon": "libre caslon text",
    "libre caslon": "libre caslon text",
    "librecaslon": "libre caslon text",
    "baskerville": "libre baskerville",
    "librebaskerville": "libre baskerville",
    "garamond": "eb garamond",
    "ebgaramond": "eb garamond",
    "cormorant": "cormorant garamond",
    "canela text": "fraunces",
    "canela": "fraunces",
    "gill sans": "cabin",
    "gillsans": "cabin",
    "gill": "cabin",
    "avenir next": "nunito sans",
    "avenirnext": "nunito sans",
    "avenir": "nunito sans",
    "nunitosans": "nunito sans",
    "lucida grande": "open sans",
    "lucidagrande": "open sans",
    "lucida": "open sans",
    "futura": "jost",
    "malayalam mn": "noto serif malayalam",
    "malayalammn": "noto serif malayalam",
    "malayalam": "noto serif malayalam",
    "mukta": "mukta mahee",
    "muktamahee": "mukta mahee",
    "publico text": "newsreader",
    "publicotext": "newsreader",
    "publico": "newsreader",
    "verdana": "pt sans",
    "ptsans": "pt sans",
    "charter": "charis sil",
    "charis": "charis sil",
    "iowan old style": "lora",
    "iowanoldstyle": "lora",
    "iowan": "lora",
    "literaria": "literata",
    "amazon ember": "open sans",
    "amazonember": "open sans",
    "ember": "open sans",
    "opensans": "open sans",
    "ibm plex": "ibm plex sans",
    "calibre": "inter",
    "helvetica": "inter",
    "helvetica neue": "inter",
    "arial": "arimo",
    "bodoni": "bodoni moda",
    "bodoni 72": "bodoni moda",
    "bodoni72": "bodoni moda",
    "librebodoni": "libre bodoni",
    "playfair": "playfair display",
    "playfairdisplay": "playfair display",
    "jetbrains": "jetbrains mono",
    "ptmono": "pt mono",
}

FORMAT_KOERPER_SCHRIFT: Dict[str, str] = {
    "atk2": "faustina",
    "atk1": "eb garamond",
    "atk3": "literata",
    "br2": "pt serif",
    "br1": "bitter",
    "apa": "tinos",
}

INLINE_CODE_SCHRIFT = '("PT Mono", "JetBrains Mono")'
AUTOR_ATK1_SCHRIFT = '("Inter", "Arimo", "Roboto")'
AUTOR_AKZENT_SCHRIFT = '("Open Sans", "IBM Plex Sans", "Inter")'


def _normalisiere_schluessel(text: str) -> str:
    return " ".join(text.strip().lower().split())


def verfuegbare_typst_schriften() -> Set[str]:
    """Ermittelt alle für Typst aktuell erreichbaren Schriftfamilien."""
    typst_prog = shutil.which("typst")
    if not typst_prog:
        return set()
    befehl = [typst_prog, "fonts"]
    if os.path.isdir(SCHRIFTARTEN_ORDNER):
        befehl.extend(["--font-path", SCHRIFTARTEN_ORDNER])
    try:
        erg = subprocess.run(befehl, capture_output=True, text=True, timeout=10)
        if erg.returncode == 0:
            return {z.strip().lower() for z in erg.stdout.splitlines() if z.strip()}
    except Exception:
        pass
    return set()


def schriftart_aufloesen(schrift_arg: Optional[str], fmt: str = "atk2") -> Tuple[str, str]:
    """Löst die Typst-Schriftangabe und den Anzeigenamen für den Fließtext auf."""
    standard_schluessel = FORMAT_KOERPER_SCHRIFT.get(fmt, "faustina")

    if schrift_arg:
        bereinigt = _normalisiere_schluessel(schrift_arg)
        if bereinigt not in ("", "none", "auto", "default", "standard"):
            schluessel = SCHRIFT_ALIASE.get(bereinigt, bereinigt)
            if schluessel in SCHRIFTARTEN_KATALOG:
                eintrag = SCHRIFTARTEN_KATALOG[schluessel]
                return str(eintrag["typst_angabe"]), str(eintrag["anzeigename"])

            # Prüfe, ob eine benutzerdefinierte Systemschrift tatsächlich existiert.
            bekannte = verfuegbare_typst_schriften()
            if bereinigt in bekannte:
                sauberer_name = schrift_arg.strip().replace('"', '\\"')
                return f'("{sauberer_name}", "PT Serif", "Open Sans")', schrift_arg.strip()

            drucke_warnung(
                f"Schriftart '{schrift_arg}' nicht gefunden. "
                f"Verwende Standardschrift '{SCHRIFTARTEN_KATALOG[standard_schluessel]['anzeigename']}'."
            )

    eintrag = SCHRIFTARTEN_KATALOG[standard_schluessel]
    return str(eintrag["typst_angabe"]), str(eintrag["anzeigename"])


def titel_schriftart_aufloesen(fmt: str, koerper_typst_angabe: str) -> str:
    """Löst die Schriftart für die Hauptüberschrift (Titel) auf."""
    if fmt == "atk1":
        return str(SCHRIFTARTEN_KATALOG["gfs didot"]["typst_angabe"])
    if fmt == "atk3":
        return str(SCHRIFTARTEN_KATALOG["jost"]["typst_angabe"])
    return koerper_typst_angabe


def ueberschrift_schriftart_aufloesen(fmt: str, koerper_typst_angabe: Optional[str] = None) -> Optional[str]:
    """Löst die Schriftart für Zwischenüberschriften auf."""
    if fmt == "atk3":
        return AUTOR_AKZENT_SCHRIFT
    if fmt == "atk2":
        return koerper_typst_angabe
    return None


def initial_schriftart_aufloesen(fmt: str, titel_typst_angabe: str) -> str:
    """Löst die Schriftart für das große Textinitial (Drop Cap) auf."""
    if fmt == "atk2":
        return str(SCHRIFTARTEN_KATALOG["libre baskerville"]["typst_angabe"])
    return titel_typst_angabe


def ist_bekannte_mehrwort_schrift(text: str) -> bool:
    """Prüft, ob ein Argumentanfang einer bekannten Schriftart entspricht."""
    bereinigt = _normalisiere_schluessel(text)
    return bereinigt in SCHRIFTARTEN_KATALOG or bereinigt in SCHRIFT_ALIASE


def alle_schrift_schluessel() -> Set[str]:
    """Gibt alle bekannten Schriftnamen und Aliase in Kleinschreibung zurück."""
    return set(SCHRIFTARTEN_KATALOG.keys()) | set(SCHRIFT_ALIASE.keys())


def schriften_herunterladen() -> bool:
    """Prüft und lädt fehlende quelloffene Schriftarten direkt in den Ordner 'Schriftarten/'."""
    os.makedirs(SCHRIFTARTEN_ORDNER, exist_ok=True)
    drucke_hinweis(f"Prüfe Schriftarten in: {SCHRIFTARTEN_ORDNER}")

    aufgaben: List[Tuple[str, str, str]] = []
    for eintrag in SCHRIFTARTEN_KATALOG.values():
        unterordner, repo_pfad, dateiliste = eintrag["quelle"]  # type: ignore[misc]
        ziel_unterordner = os.path.join(SCHRIFTARTEN_ORDNER, unterordner)
        os.makedirs(ziel_unterordner, exist_ok=True)
        for dateiname in dateiliste:
            zielpfad = os.path.join(ziel_unterordner, dateiname)
            if not os.path.exists(zielpfad) or os.path.getsize(zielpfad) < 1000:
                url = f"{GOOGLE_FONTS_BASIS}/{repo_pfad}/{urllib.parse.quote(dateiname)}"
                aufgaben.append((url, zielpfad, dateiname))

    if not aufgaben:
        drucke_hinweis("Alle quelloffenen Schriftarten sind vollständig vorhanden.")
        return True

    drucke_hinweis(f"Lade {len(aufgaben)} fehlende Schriftdatei(en) herunter...")
    fehler_anzahl = 0

    def _datei_laden(eintrag_aufgabe: Tuple[str, str, str]) -> str:
        url, zielpfad, dateiname = eintrag_aufgabe
        anfrage = urllib.request.Request(url, headers={"User-Agent": "txt2pdf/2.0"})
        with urllib.request.urlopen(anfrage, timeout=20) as antwort:
            daten = antwort.read()
        temp_pfad = f"{zielpfad}.tmp"
        with open(temp_pfad, "wb") as aus:
            aus.write(daten)
        os.replace(temp_pfad, zielpfad)
        return dateiname

    with ThreadPoolExecutor(max_workers=6) as pool:
        zukunft = {pool.submit(_datei_laden, a): a for a in aufgaben}
        for fertig in as_completed(zukunft):
            _, _, dateiname = zukunft[fertig]
            try:
                fertig.result()
            except Exception as fehler:
                fehler_anzahl += 1
                drucke_warnung(f"Download fehlgeschlagen ({dateiname}): {fehler}")

    if fehler_anzahl == 0:
        drucke_hinweis("Alle fehlenden Schriftarten wurden erfolgreich geladen.")
        return True
    drucke_warnung(f"{fehler_anzahl} Schriftdatei(en) konnten nicht geladen werden.")
    return False


def schriftarten_uebersicht() -> str:
    """Erstellt eine schlichte, übersichtliche Auflistung aller verfügbaren Schriftarten."""
    zeilen = [
        "Verfügbare Schriftarten (-z NAME):",
        "",
        "  Name                  Stil           Entspricht / Hinweis",
        "  --------------------  -------------  ------------------------------",
    ]
    for schluessel in sorted(SCHRIFTARTEN_KATALOG.keys(), key=lambda k: str(SCHRIFTARTEN_KATALOG[k]["anzeigename"])):
        eintrag = SCHRIFTARTEN_KATALOG[schluessel]
        name = str(eintrag["anzeigename"])
        typ = str(eintrag["typ"])
        ersatz = str(eintrag["ersatz_fuer"])
        zeilen.append(f"  {name:<20}  {typ:<13}  {ersatz}")
    zeilen.append("")
    zeilen.append("Hinweis: Frühere Namen (z. B. 'Times New Roman', 'Garamond', 'Futura',")
    zeilen.append("         'Didot', 'Kefa III', 'Amazon Ember') werden automatisch auf das")
    zeilen.append("         jeweilige quelloffene Gegenstück umgeleitet.")
    return "\n".join(zeilen)
