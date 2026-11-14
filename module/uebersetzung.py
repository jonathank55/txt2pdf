# -*- coding: utf-8 -*-
"""Optionale Textübersetzung über das DeepL-SDK oder direkt über die DeepL-REST-Schnittstelle."""

import json
import os
import re
from typing import List, Optional
import urllib.parse
import urllib.request

from .ausgabe import drucke_warnung
from .konfiguration import BIBLIOGRAFIE_WOERTER_MUSTER, KONFIG_ORDNER


def _deepl_schluessel_laden() -> Optional[str]:
    schluessel = os.environ.get("DEEPL_AUTH_KEY") or os.environ.get("DEEPL_API_KEY")
    if schluessel:
        return schluessel.strip()

    kandidaten = [
        os.path.join(KONFIG_ORDNER, "deepl.key"),
        os.path.expanduser("~/.config/deepl/key"),
    ]
    for pfad in kandidaten:
        if os.path.exists(pfad):
            try:
                with open(pfad, "r", encoding="utf-8") as f:
                    inhalt = f.read().strip()
                    if inhalt:
                        return inhalt
            except OSError:
                pass
    return None


def _zielsprache_normieren(zielsprache: str) -> str:
    norm = zielsprache.upper().strip()
    if norm == "EN":
        return "EN-US"
    if norm == "PT":
        return "PT-PT"
    return norm


def text_uebersetzen(text: str, zielsprache: str = "en") -> str:
    """Übersetzt einen Textblock via DeepL-SDK oder direkt per HTTPS-Anfrage."""
    if not text or not text.strip():
        return text

    schluessel = _deepl_schluessel_laden()
    norm_ziel = _zielsprache_normieren(zielsprache)

    # 1. Offizielles SDK nutzen, falls installiert und Schlüssel vorliegt
    if schluessel:
        try:
            import deepl  # type: ignore
            uebersetzer = deepl.Translator(schluessel)
            erg = uebersetzer.translate_text(text, target_lang=norm_ziel)
            return erg.text if hasattr(erg, "text") else str(erg)
        except ImportError:
            pass
        except Exception as fehler:
            drucke_warnung(f"DeepL-SDK-Warnung: {fehler}")

        # 2. Direkte REST-Anfrage mit Standardbibliothek (benötigt keine Fremdpakete)
        endpunkt = (
            "https://api-free.deepl.com/v2/translate"
            if schluessel.endswith(":fx")
            else "https://api.deepl.com/v2/translate"
        )
        daten = urllib.parse.urlencode({"text": text, "target_lang": norm_ziel}).encode("utf-8")
        anfrage = urllib.request.Request(
            endpunkt,
            data=daten,
            headers={
                "Authorization": f"DeepL-Auth-Key {schluessel}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(anfrage, timeout=15) as antwort:
                antwort_json = json.loads(antwort.read().decode("utf-8"))
                eintraege = antwort_json.get("translations", [])
                if eintraege and eintraege[0].get("text"):
                    return str(eintraege[0]["text"])
        except Exception as fehler:
            drucke_warnung(f"DeepL-Übersetzung fehlgeschlagen: {fehler}")
            return text

    drucke_warnung(
        "Kein DeepL-Schlüssel gefunden (DEEPL_AUTH_KEY oder ~/.config/txt2pdf/deepl.key). "
        "Text bleibt unübersetzt."
    )
    return text


def textzeilen_uebersetzen(zeilen: List[str], zielsprache: str) -> List[str]:
    """Übersetzt Textzeilen absatzweise und schützt Bildpfade, URLs sowie Literaturköpfe."""
    ziel = zielsprache.lower().strip()
    ergebnis: List[str] = []
    block: List[str] = []

    bib_re = re.compile(rf"^(?:{BIBLIOGRAFIE_WOERTER_MUSTER})\b", re.IGNORECASE)

    def _block_leeren() -> None:
        nonlocal block
        if block:
            zusammen = "\n".join(block)
            ergebnis.extend(text_uebersetzen(zusammen, zielsprache=ziel).split("\n"))
            block = []

    for zeile in zeilen:
        s = zeile.strip()
        if s.startswith(("##", "http://", "https://", "doi.org")):
            _block_leeren()
            ergebnis.append(zeile)
        elif bib_re.match(s):
            _block_leeren()
            if ziel.startswith("en"):
                ergebnis.append("REFERENCES")
            elif ziel.startswith("es"):
                ergebnis.append("REFERENCIAS")
            else:
                ergebnis.append("LITERATURVERZEICHNIS")
        elif not s:
            _block_leeren()
            ergebnis.append("")
        else:
            block.append(zeile)

    _block_leeren()
    return ergebnis
