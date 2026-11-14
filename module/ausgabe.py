# -*- coding: utf-8 -*-
"""Schlichte, konsistente Terminal-Ausgaben ohne aufdringliche Formatierungen."""

import os
import shutil
import sys


def _farben_erlaubt(datenstrom) -> bool:
    """Prüft, ob ANSI-Farbcodes sicher ausgegeben werden dürfen."""
    if os.environ.get("NO_COLOR"):
        return False
    return bool(hasattr(datenstrom, "isatty") and datenstrom.isatty())


def _stil(text: str, code: str, datenstrom) -> str:
    if not _farben_erlaubt(datenstrom):
        return text
    return f"{code}{text}\033[0m"


def trennlinie(zeichen: str = "─", standardbreite: int = 72) -> str:
    """Erzeugt eine dezente Trennlinie passend zur aktuellen Terminalbreite."""
    try:
        spalten = shutil.get_terminal_size((standardbreite, 20)).columns
        return zeichen * max(40, min(spalten, 100))
    except Exception:
        return zeichen * standardbreite


def drucke_erfolg(
    quelldatei: str,
    ausgabedatei: str,
    formatname: str,
    zielsprache: str = None,
) -> None:
    """Gibt eine knappe, sachliche Erfolgsmeldung auf stdout aus."""
    linie = _stil(trennlinie(), "\033[0;34m", sys.stdout)
    titel = _stil("txt2pdf", "\033[1m", sys.stdout)
    status = _stil("Erstellt", "\033[0;32m", sys.stdout)
    print(f"\n{titel}")
    print(linie)
    print(f"Quelle:   {quelldatei}")
    print(f"Ausgabe:  {ausgabedatei}")
    print(f"Format:   {formatname}")
    if zielsprache:
        print(f"Sprache:  {zielsprache}")
    print(f"Status:   {status}")
    print(f"{linie}\n")


def drucke_fehler(quelldatei: str, meldung: str, details: str = "") -> None:
    """Gibt eine sachliche Fehlermeldung auf stderr aus."""
    linie = _stil(trennlinie(), "\033[0;31m", sys.stderr)
    titel = _stil("txt2pdf — Fehler", "\033[1;31m", sys.stderr)
    print(f"\n{titel}", file=sys.stderr)
    print(linie, file=sys.stderr)
    if quelldatei:
        print(f"Quelle:   {quelldatei}", file=sys.stderr)
    print(f"Ursache:  {meldung}", file=sys.stderr)
    if details:
        print(f"Details:\n{details.strip()}", file=sys.stderr)
    print(f"{linie}\n", file=sys.stderr)


def drucke_warnung(meldung: str) -> None:
    """Gibt eine knappe Warnung auf stderr aus."""
    praefix = _stil("Hinweis:", "\033[1;33m", sys.stderr)
    print(f"{praefix} {meldung}", file=sys.stderr)


def drucke_hinweis(meldung: str) -> None:
    """Gibt eine schlichte Statuszeile auf stdout aus."""
    print(meldung)
