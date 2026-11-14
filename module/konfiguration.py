# -*- coding: utf-8 -*-
"""Zentrale Pfade, Formatprofile, Randvorgaben und Plattform-Hilfsfunktionen."""

import os
import sys
from typing import Dict, Tuple

# Ermittelt den echten Programmordner unabhängig von Symlinks und Arbeitsverzeichnis.
PROGRAMM_ORDNER = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SCHRIFTARTEN_ORDNER = os.path.join(PROGRAMM_ORDNER, "Schriftarten")
PAKETE_ORDNER = os.path.join(PROGRAMM_ORDNER, "pakete")


def cache_ordner_ermitteln() -> str:
    """Gibt das plattformgerechte Cache-Verzeichnis für txt2pdf zurück."""
    if sys.platform == "win32":
        basis = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(basis, "txt2pdf", "Cache")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Caches/txt2pdf")
    xdg_cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(xdg_cache, "txt2pdf")


def konfig_ordner_ermitteln() -> str:
    """Gibt das plattformgerechte Konfigurationsverzeichnis für txt2pdf zurück."""
    if sys.platform == "win32":
        basis = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(basis, "txt2pdf")
    xdg_konfig = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(xdg_konfig, "txt2pdf")


CACHE_ORDNER = cache_ordner_ermitteln()
ZITATE_CACHE_DATEI = os.path.join(CACHE_ORDNER, "zitate_zwischenspeicher.json")
KONFIG_ORDNER = konfig_ordner_ermitteln()

BILD_ENDUNGEN: Tuple[str, ...] = (
    ".png", ".jpg", ".jpeg", ".webp", ".pdf", ".gif", ".svg", ".tiff", ".tif"
)
TEXT_ENDUNGEN: Tuple[str, ...] = (".txt", ".md", ".rtf", ".rtfd")

STANDARD_FORMAT = "atk2"

FORMAT_ALIASE: Dict[str, str] = {
    "atk2": "atk2",
    "artikel2": "atk2",
    "atk1": "atk1",
    "atk": "atk1",
    "artikel1": "atk1",
    "artikel": "atk1",
    "atk3": "atk3",
    "artikel3": "atk3",
    "br2": "br2",
    "bericht2": "br2",
    "br1": "br1",
    "bericht1": "br1",
    "apa": "apa",
}

FORMAT_PROFILE: Dict[str, Dict[str, object]] = {
    "atk2": {
        "name": "atk2",
        "beschreibung": "3 Spalten, Faustina, 9pt, ohne Titellinie (Standard)",
        "spalten": 3,
        "initial": True,
        "spaltensteg": "5.5mm",
        "schriftgroesse_pt": 9.0,
        "zeilenabstand": "0.55em",
        "standard_raender": "m",
    },
    "atk1": {
        "name": "atk1",
        "beschreibung": "3 Spalten, EB Garamond, 10pt, mit Titellinie",
        "spalten": 3,
        "initial": True,
        "spaltensteg": "5.5mm",
        "schriftgroesse_pt": 10.0,
        "zeilenabstand": "0.55em",
        "standard_raender": "m",
    },
    "atk3": {
        "name": "atk3",
        "beschreibung": "2 Spalten, Literata, 10pt, große Ränder",
        "spalten": 2,
        "initial": True,
        "spaltensteg": "6.0mm",
        "schriftgroesse_pt": 10.0,
        "zeilenabstand": "0.55em",
        "standard_raender": "r",
    },
    "br2": {
        "name": "br2",
        "beschreibung": "2 Spalten, PT Serif, 10pt, Berichtsformat",
        "spalten": 2,
        "initial": False,
        "spaltensteg": "6.0mm",
        "schriftgroesse_pt": 10.0,
        "zeilenabstand": "0.55em",
        "standard_raender": "g",
    },
    "br1": {
        "name": "br1",
        "beschreibung": "1 Spalte, Bitter, 10pt, Berichtsformat",
        "spalten": 1,
        "initial": False,
        "spaltensteg": "0mm",
        "schriftgroesse_pt": 10.0,
        "zeilenabstand": "0.55em",
        "standard_raender": "r",
    },
    "apa": {
        "name": "apa",
        "beschreibung": "US-Letter, Tinos, 12pt, APA-7-Aufsatzformat",
        "spalten": 1,
        "initial": False,
        "spaltensteg": "0mm",
        "schriftgroesse_pt": 12.0,
        "zeilenabstand": "1.15em",
        "standard_raender": "apa",
    },
}

RAND_VORGABEN: Dict[str, Tuple[str, str, int]] = {
    "k": ("10mm", "12mm", 190),
    "m": ("16mm", "18mm", 178),
    "g": ("22mm", "24mm", 166),
    "r": ("34mm", "36mm", 142),
}

RAND_ALIASE: Dict[str, str] = {
    "k": "k",
    "klein": "k",
    "small": "k",
    "m": "m",
    "mittel": "m",
    "medium": "m",
    "standard": "m",
    "g": "g",
    "gross": "g",
    "groß": "g",
    "large": "g",
    "r": "r",
    "riesig": "r",
    "huge": "r",
    "giant": "r",
    "xl": "r",
}

BIBLIOGRAFIE_WOERTER_MUSTER = (
    r"Literaturverzeichnis|Quellenverzeichnis|Works Cited|Bibliography|"
    r"Literatur|Quellen|References|Library|Verzeichnis|Referencias|"
    r"Bibliografía|Fuentes"
)
