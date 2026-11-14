# -*- coding: utf-8 -*-
"""Suche nach Typst, sichere PDF-Kompilierung und plattformübergreifende Vorschau."""

import os
import shutil
import subprocess
import sys
import time
from typing import List, Optional

from .ausgabe import drucke_warnung
from .konfiguration import PAKETE_ORDNER, SCHRIFTARTEN_ORDNER


def typst_programm_finden() -> Optional[str]:
    """Findet die ausführbare Typst-Datei plattformübergreifend."""
    gefunden = shutil.which("typst")
    if gefunden:
        return gefunden

    kandidaten = [
        "/opt/homebrew/bin/typst",
        "/home/linuxbrew/.linuxbrew/bin/typst",
        "/usr/local/bin/typst",
        "/usr/bin/typst",
        os.path.expanduser("~/.cargo/bin/typst"),
        os.path.expanduser("~/.local/bin/typst"),
    ]
    for pfad in kandidaten:
        if os.path.isfile(pfad) and os.access(pfad, os.X_OK):
            return pfad
    return None


def typst_kompilieren(typst_quelltext: str, ausgabe_pdf: str) -> Optional[str]:
    """Kompiliert Typst-Quelltext zu einer PDF-Datei. Gibt bei Erfolg None zurück, sonst die Fehlermeldung."""
    typst_prog = typst_programm_finden()
    if not typst_prog:
        return (
            "Typst wurde nicht gefunden. Bitte Typst installieren und sicherstellen, "
            "dass 'typst' im PATH liegt."
        )

    abs_ausgabe = os.path.abspath(ausgabe_pdf)
    os.makedirs(os.path.dirname(abs_ausgabe), exist_ok=True)
    temp_typ = f"{abs_ausgabe}.tmp_{os.getpid()}_{int(time.time() * 1000)}.typ"

    befehl: List[str] = [typst_prog, "compile"]
    if sys.platform == "win32":
        laufwerk, _ = os.path.splitdrive(abs_ausgabe)
        if laufwerk:
            befehl.extend(["--root", f"{laufwerk}\\"])
    else:
        befehl.extend(["--root", "/"])

    if os.path.isdir(SCHRIFTARTEN_ORDNER):
        befehl.extend(["--font-path", SCHRIFTARTEN_ORDNER])
    if os.path.isdir(PAKETE_ORDNER):
        befehl.extend(["--package-path", PAKETE_ORDNER])

    befehl.extend([temp_typ, abs_ausgabe])

    try:
        with open(temp_typ, "w", encoding="utf-8") as f:
            f.write(typst_quelltext)

        ergebnis = subprocess.run(
            befehl,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired:
        return "Zeitüberschreitung beim Kompilieren durch Typst."
    except OSError as fehler:
        return f"Start von Typst fehlgeschlagen: {fehler}"
    finally:
        if os.path.exists(temp_typ):
            try:
                os.remove(temp_typ)
            except OSError:
                pass

    if ergebnis.returncode == 0 and os.path.exists(abs_ausgabe) and os.path.getsize(abs_ausgabe) > 0:
        if ergebnis.stderr.strip():
            # Mögliche verbleibende Hinweise von Typst transparent durchreichen
            for zeile in ergebnis.stderr.strip().splitlines():
                if zeile.strip().startswith("warning:"):
                    drucke_warnung(zeile.strip())
        return None

    return ergebnis.stderr.strip() or f"Typst beendet mit Rückgabecode {ergebnis.returncode}."


def vorschau_oeffnen(pdf_pfad: str) -> None:
    """Öffnet die erzeugte PDF-Datei im Standardbetrachter des Betriebssystems."""
    try:
        if sys.platform == "win32":
            os.startfile(pdf_pfad)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", pdf_pfad], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            oeffner = shutil.which("xdg-open")
            if oeffner:
                subprocess.Popen([oeffner, pdf_pfad], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                drucke_warnung("Vorschau konnte nicht geöffnet werden ('xdg-open' fehlt).")
    except Exception as fehler:
        drucke_warnung(f"Vorschau konnte nicht geöffnet werden: {fehler}")
