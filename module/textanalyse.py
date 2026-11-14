# -*- coding: utf-8 -*-
"""Erkennung und Bereinigung von Titeln, Autoren, Daten, Überschriften, ISBNs und Zitaten."""

import re
from typing import List, Optional, Tuple
import unicodedata


DATUMS_MUSTER = [
    r"^(?:Datum|Date):\s*(.+)$",
    r"^(?:Verfasst\s+am\s+)?(\d{1,2}\.\s*(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|Jan|Feb|Mär|Apr|Mai|Jun|Jul|Aug|Sep|Okt|Nov|Dez)\s+\d{4})(?:.*)?$",
    r"^((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})$",
    r"^(\d{1,2}\.\d{1,2}\.\d{2,4})$",
    r"^(\d{4}-\d{2}-\d{2})$",
]

DOKUMENT_ZUSAETZE = {
    "langversion", "kurzversion", "vollversion", "entwurf", "draft", "final",
    "kopie", "copy", "neu", "alt", "überarbeitet", "korrigiert", "korrektur",
    "version", "druck", "pdf", "druckversion", "abgabe",
    "en", "de", "es", "fr", "it", "pt", "nl", "eng", "deu", "ger",
}

AUTOR_STOPPWOERTER = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "eines", "einem", "einen",
    "und", "oder", "aber", "denn", "weil", "dass", "wenn", "ob", "wie", "als",
    "im", "in", "am", "an", "auf", "aus", "bei", "mit", "nach", "von", "zu", "zum", "zur", "über", "unter", "vor", "durch", "für",
    "ist", "sind", "war", "waren", "wird", "werden", "hat", "haben", "hatte", "hatten", "kann", "können", "muss", "müssen",
    "kapitel", "chapter", "abschnitt", "section", "inhalt", "literatur", "literaturverzeichnis", "references", "quellen",
    "zusammenfassung", "abstract", "einleitung", "introduction", "fazit", "schluss", "anhang", "tabelle", "abbildung",
    "the", "a", "an", "and", "or", "but", "of", "for", "with", "from", "into", "is", "are", "was", "were",
    "wer", "wen", "wem", "wessen", "was", "wo", "woher", "wohin", "wann", "warum", "weshalb", "wieso", "welcher", "welche", "welches",
    "who", "whom", "whose", "what", "which", "where", "when", "why", "how",
    "artikel", "aufsatz", "bericht", "essay", "notiz", "notizen", "entwurf", "text", "dokument", "paper", "report", "draft", "article",
    "kolumne", "kommentar", "lehrbuch", "manuskript", "übersicht", "gliederung",
    "schwitzt", "herrscht", "denkt", "schreibt", "sagt", "geht", "kommt", "steht", "liegt", "bleibt", "sieht", "zeigt", "lebt", "stirbt", "zahlt", "kostet",
    "fire", "cal", "lab", "notes", "discussion", "urban", "planners", "planner", "advocacy", "group", "groups", "center", "centre", "team", "task", "force",
    "committee", "commission", "department", "dept", "agency", "board", "council", "union", "association", "office", "station", "society", "brigade", "division",
    "bureau", "service", "services", "police", "hospital", "institute", "institution", "foundation", "university", "college", "school", "community", "communities",
    "government", "state", "county", "city", "feuer", "wehr", "feuerwehr", "gruppe", "notizen", "labor", "diskussion", "planer", "zentrum", "amt", "abteilung",
    "behörde", "polizei", "krankenhaus", "verband", "verein", "gesellschaft", "institut", "hochschule", "universität", "stiftung", "gemeinde", "regierung", "staat", "stadt",
} | DOKUMENT_ZUSAETZE


def _sprach_und_versions_anhaenge_abspalten(text: str) -> Tuple[str, List[str]]:
    """Trennt Sprach- und Versionsmarkierungen am Ende (z. B. '(EN)', '- Langversion') sauber ab."""
    bereinigt = text.strip()
    anhaenge: List[str] = []

    while True:
        vorher = bereinigt
        # Klammer-Zusätze am Ende: (EN), (DE), (Final), [v2], etc.
        m_klammer = re.search(
            r"\s*[\(\[]\s*(?:EN|DE|ES|FR|IT|PT|NL|ENG|DEU|GER|v\d+(?:\.\d+)?|Final|Draft|Entwurf|Langversion|Kurzversion)\s*[\)\]]\s*$",
            bereinigt,
            re.IGNORECASE,
        )
        if m_klammer:
            anhaenge.insert(0, m_klammer.group(0).strip())
            bereinigt = bereinigt[: m_klammer.start()].strip()

        # Bindestrich-Zusätze am Ende: - Langversion, - Entwurf, - Final, - v2
        m_strich = re.search(
            r"\s+[-–—]\s+(Langversion|Kurzversion|Vollversion|Entwurf|Draft|Final|Kopie|Copy|v\d+(?:\.\d+)?)\s*$",
            bereinigt,
            re.IGNORECASE,
        )
        if m_strich:
            anhaenge.insert(0, m_strich.group(1).strip())
            bereinigt = bereinigt[: m_strich.start()].strip()

        if bereinigt == vorher:
            break

    return bereinigt, anhaenge


def ist_autorenname(kandidat: str) -> bool:
    """Prüft zuverlässig, ob eine Zeichenkette einen Personennamen darstellt."""
    if not kandidat:
        return False
    s = kandidat.strip()
    if len(s) < 3 or len(s) > 60:
        return False

    # Entferne optionale Sprach-/Versionsanhänge für die Prüfung, nicht jedoch reine Zusätze
    if s.lower() in DOKUMENT_ZUSAETZE:
        return False

    # Mehrwortige Versalien sind Überschriften, keine Autoren
    if s.isupper() and len(s.split()) > 1:
        return False
    if s.startswith(("-", "–", "—", "#", "*", ">", "•")):
        return False
    if s.endswith((".", "!", "?", ";", ":", "«", "»", "\"", "“", "”")):
        if not re.search(r"\b[A-ZÄÖÜ]\.$", s):
            return False

    m_praefix = re.match(r"^(?:autor|author|von|by|verfasser|written\s+by)\s*[:\-–—]?\s*(.+)$", s, re.IGNORECASE)
    if m_praefix:
        s = m_praefix.group(1).strip()

    titel_muster = r"^(?:(?:Dr\.|Prof\.|Prof\. Dr\.|PD|PhD|M\.A\.|B\.A\.|M\.Sc\.|B\.Sc\.)\s+)*"
    suffix_muster = r"(?:,\s*(?:Ph\.?D\.?|M\.?A\.?|M\.?Sc\.?|B\.?A\.?|B\.?Sc\.?|LL\.?M\.?|CFA|MD|MBA))?$"
    s_bereinigt = re.sub(titel_muster, "", s, flags=re.IGNORECASE)
    s_bereinigt = re.sub(suffix_muster, "", s_bereinigt, flags=re.IGNORECASE).strip()

    if re.search(r"\d", s_bereinigt):
        return False
    # Klammern wie "(EN)" dürfen in einem reinen Autorennamen nicht als Wortbestandteil vorkommen
    if "(" in s_bereinigt or ")" in s_bereinigt or "[" in s_bereinigt or "]" in s_bereinigt:
        return False

    if "," in s_bereinigt:
        teile = [p.strip() for p in s_bereinigt.split(",")]
        if len(teile) != 2 or len(teile[0].split()) > 2 or len(teile[1].split()) > 2:
            return False

    woerter = re.findall(r"[A-Za-zÄÖÜäöüß]+(?:-[A-Za-zÄÖÜäöüß]+)?|\b[A-ZÄÖÜ]\.", s_bereinigt)
    if not (1 <= len(woerter) <= 5):
        return False

    for w in woerter:
        w_klein = w.lower()
        if w_klein in AUTOR_STOPPWOERTER:
            return False
        if any(w_klein.endswith(endung) for endung in ("bericht", "analyse", "studie", "aufsatz", "entwurf", "gruppe", "version", "notes", "fire")):
            return False
        if not (w[0].isupper() or w_klein in ("von", "van", "de", "der", "zu")):
            return False

    return True


def titel_und_autor_aus_dateiname(basisname: str) -> Tuple[Optional[str], Optional[str]]:
    """Extrahiert Titel und Autor aus einem Dateinamen und ignoriert Sprach-/Versionsanhänge."""
    dok_praefixe = {
        "artikel", "aufsatz", "bericht", "essay", "notiz", "notizen", "entwurf", "text",
        "dokument", "paper", "report", "draft", "article", "kolumne", "kommentar", "manuskript",
    }

    kernname, _ = _sprach_und_versions_anhaenge_abspalten(basisname)

    # 1. Explizite Trennung: Titel von/by Autor
    m = re.search(r"^(.*?)\s*(?:,\s*)?\b(?:von|by|autor|author)\b\s*(.+)$", kernname, re.IGNORECASE)
    if m:
        c1 = m.group(1).strip()
        c2, _ = _sprach_und_versions_anhaenge_abspalten(m.group(2).strip())
        if ist_autorenname(c2):
            return c1, c2
        c1_sauber, _ = _sprach_und_versions_anhaenge_abspalten(c1)
        if ist_autorenname(c1_sauber):
            return c2, c1_sauber

    # 2. Autor am Ende: "Titel - Autor", "Titel / Autor", "Titel : Autor"
    m_ende = re.search(r"^(.*?)(?:\s+[-–—]\s+|\s+/\s+|\s*/\s*|\s*[:|]\s+)\s*([^/\-:|]+)$", kernname)
    if m_ende:
        t_kand = m_ende.group(1).strip()
        a_kand, _ = _sprach_und_versions_anhaenge_abspalten(m_ende.group(2).strip())
        if ist_autorenname(a_kand):
            m_p = re.match(
                r"^(?:artikel|aufsatz|bericht|essay|notizen?|entwurf|text|dokument|paper|report|draft|article|kolumne|kommentar|manuskript)\s*[:|]\s*(.+)$",
                t_kand,
                re.IGNORECASE,
            )
            if m_p:
                t_kand = m_p.group(1).strip()
            return (t_kand or None), a_kand

    # 3. Autor am Anfang: "Autor - Titel" oder "Autor / Titel"
    m_start = re.search(r"^([^/\-:|]+?)(?:\s+[-–—]\s+|\s+/\s+|\s*/\s*|\s*[:|]\s+)\s*(.*?)$", kernname)
    if m_start:
        a_kand, _ = _sprach_und_versions_anhaenge_abspalten(m_start.group(1).strip())
        t_kand = m_start.group(2).strip()
        if ist_autorenname(a_kand) and a_kand.lower() not in dok_praefixe:
            return (t_kand or None), a_kand

    return None, None


def titel_stimmt_ueberein(kandidat: str, ziel: str) -> bool:
    """Prüft, ob zwei Titel nach Normalisierung übereinstimmen."""
    if not kandidat or not ziel:
        return False
    c_sauber = re.sub(r"^[#\s:|\-]+", "", unicodedata.normalize("NFC", kandidat)).strip().lower()
    z_sauber = re.sub(r"^[#\s:|\-]+", "", unicodedata.normalize("NFC", ziel)).strip().lower()
    return c_sauber == z_sauber


def titel_und_autor_bereinigen(
    titel: str,
    autor: Optional[str] = None,
    ersatz_autor: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """Bereinigt Titel und Autor von doppelten Namensanhängen und Vertauschungen."""
    endgueltiger_autor = autor.strip() if (autor and autor.strip()) else ersatz_autor
    if endgueltiger_autor:
        endgueltiger_autor, _ = _sprach_und_versions_anhaenge_abspalten(endgueltiger_autor)

    if not titel:
        return "", endgueltiger_autor

    bereinigter_titel = titel.strip()

    # Korrektur bei vertauschtem Titel und Autor
    if bereinigter_titel and endgueltiger_autor and ist_autorenname(bereinigter_titel) and not ist_autorenname(endgueltiger_autor):
        bereinigter_titel, endgueltiger_autor = endgueltiger_autor, bereinigter_titel

    # Führendes Dokumenttyp-Präfix entfernen
    m_praefix = re.match(
        r"^(?:artikel|aufsatz|bericht|essay|notizen?|entwurf|text|dokument|paper|report|article)\s*[:|]\s*(.+)$",
        bereinigter_titel,
        re.IGNORECASE,
    )
    if m_praefix:
        bereinigter_titel = m_praefix.group(1).strip()

    zu_pruefende = [a for a in [endgueltiger_autor, ersatz_autor] if a]
    gesehen = set()
    eindeutige_autoren = []
    for a in zu_pruefende:
        if a not in gesehen:
            gesehen.add(a)
            eindeutige_autoren.append(a)

    for a in eindeutige_autoren:
        pat_ende = re.compile(
            r"[\s\-_–—|:/]*(?:(?:von|by|autor|author)\s+)?[\s\-_–—|:/]*" + re.escape(a) + r"\s*$",
            re.IGNORECASE,
        )
        if pat_ende.search(bereinigter_titel):
            if not endgueltiger_autor:
                endgueltiger_autor = a
            bereinigter_titel = pat_ende.sub("", bereinigter_titel)

        pat_mitte = re.compile(
            r"[\s\-_–—|:/]+(?:(?:von|by|autor|author)\s+)?" + re.escape(a) + r"[\s\-_–—|:/]+",
            re.IGNORECASE,
        )
        bereinigter_titel = pat_mitte.sub(" ", bereinigter_titel)

    m_trenner = re.search(
        r"^(.*?)(?:\s+[-–—]\s+|\s+/\s+|\s*/\s*|\s*[:|]\s+|(?:,\s*)?\b(?:von|by|autor|author)\b\s*)([A-Za-zÄÖÜäöüß][^/\-:|]*)$",
        bereinigter_titel,
        re.IGNORECASE,
    )
    if m_trenner:
        t_kand = m_trenner.group(1).strip()
        a_kand, _ = _sprach_und_versions_anhaenge_abspalten(m_trenner.group(2).strip())
        if ist_autorenname(a_kand):
            bereinigter_titel = t_kand
            if not endgueltiger_autor:
                endgueltiger_autor = a_kand
        else:
            t_sauber, _ = _sprach_und_versions_anhaenge_abspalten(t_kand)
            if ist_autorenname(t_sauber):
                bereinigter_titel = m_trenner.group(2).strip()
                if not endgueltiger_autor:
                    endgueltiger_autor = t_sauber

    bereinigter_titel = re.sub(r"[\s\-_–—|:/]+$", "", bereinigter_titel).strip()
    if not bereinigter_titel:
        bereinigter_titel = titel.strip()

    return bereinigter_titel, endgueltiger_autor


def metadatenvorspann_trennen(
    rohtext: str,
    standard_autor: Optional[str] = None,
    standard_datum: Optional[str] = None,
    bekannter_titel: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str], List[str]]:
    """Trennt Titel, Autor, Datum und den eigentlichen Textkörper im Dokumentkopf."""
    zeilen = rohtext.splitlines()
    start_idx = 0
    while start_idx < len(zeilen) and not zeilen[start_idx].strip():
        start_idx += 1

    gefundener_titel: Optional[str] = None
    gefundener_autor: Optional[str] = None
    gefundenes_datum: Optional[str] = standard_datum
    idx = start_idx

    datums_regexe = [re.compile(m, re.IGNORECASE) for m in DATUMS_MUSTER]

    while idx < len(zeilen) and idx < start_idx + 8:
        zeile_s = zeilen[idx].strip()
        if not zeile_s:
            idx += 1
            continue

        # 1. Explizites Titel-Präfix
        m_t = re.match(r"^(?:Titel|Title|Thema|Subject):\s*(.+)$", zeile_s, re.IGNORECASE)
        if m_t:
            if not gefundener_titel:
                gefundener_titel = m_t.group(1).strip()
            idx += 1
            continue

        # 2. Markdown-Überschrift # Titel
        if zeile_s.startswith("# ") and not zeile_s.startswith("##"):
            kandidat = zeile_s[2:].strip()
            if not bekannter_titel or titel_stimmt_ueberein(kandidat, bekannter_titel):
                if not gefundener_titel:
                    gefundener_titel = kandidat
                idx += 1
                continue
            break

        # 3. Explizites Autor-Präfix
        m_a = re.match(r"^(?:Autor|Author|Von|By|Verfasser|Written\s+by):\s*(.+)$", zeile_s, re.IGNORECASE)
        if not m_a:
            m_av = re.match(
                r"^(?:Autor|Author|Verfasser|Written\s+by|Von|By)\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß]+(?:\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]+)+)$",
                zeile_s,
            )
            if m_av and ist_autorenname(m_av.group(1)):
                m_a = m_av
        if m_a:
            if not gefundener_autor:
                gefundener_autor = m_a.group(1).strip()
            idx += 1
            continue

        # 4. Datum
        ist_datum = False
        for d_reg in datums_regexe:
            m_d = d_reg.match(zeile_s)
            if m_d:
                if not gefundenes_datum:
                    gefundenes_datum = m_d.group(1).strip() if m_d.groups() else zeile_s
                idx += 1
                ist_datum = True
                break
        if ist_datum:
            continue

        # 5. Titelzeile ohne Präfix
        if not gefundener_titel:
            if bekannter_titel and titel_stimmt_ueberein(zeile_s, bekannter_titel):
                gefundener_titel = zeile_s
                idx += 1
                continue

            hat_metadaten_danach = False
            for pruef_i in range(idx + 1, min(idx + 4, len(zeilen))):
                naechste = zeilen[pruef_i].strip()
                if naechste and (ist_autorenname(naechste) or any(r.match(naechste) for r in datums_regexe)):
                    hat_metadaten_danach = True
                    break
            if hat_metadaten_danach and len(zeile_s) <= 250 and not zeile_s.startswith(("-", "*", "•", "##", ">")):
                if not ist_autorenname(zeile_s):
                    gefundener_titel = zeile_s
                    idx += 1
                    continue

        # 6. Autor ohne Präfix
        if not standard_autor and ist_autorenname(zeile_s):
            if not gefundener_autor:
                gefundener_autor = zeile_s
                idx += 1
                continue

        break

    while idx < len(zeilen) and not zeilen[idx].strip():
        idx += 1

    rest_zeilen = zeilen[idx:]

    if gefundener_titel and ist_autorenname(gefundener_titel) and (not gefundener_autor or not ist_autorenname(gefundener_autor)):
        gefundener_titel, gefundener_autor = gefundener_autor, gefundener_titel

    endgueltiger_autor = gefundener_autor if gefundener_autor else standard_autor
    endgueltiges_datum = gefundenes_datum if gefundenes_datum else standard_datum
    return gefundener_titel, endgueltiger_autor, endgueltiges_datum, rest_zeilen


def ist_einzelner_satz(text: str) -> bool:
    """Prüft, ob ein kurzer Absatz aus genau einem Satz besteht (Überschriften-Heuristik)."""
    s = text.strip()
    if not s:
        return False
    sauber = re.sub(r"^#{1,6}\s*", "", s).strip()
    if not sauber:
        return False
    if sauber.startswith(("http://", "https://", "doi:", "10.", "##", ">", "-", "*", "•")):
        return False

    gliederung = r"^(?:(?:Kapitel|Abschnitt|Teil|Section|Chapter|§)\s+)?(?:\d+|[A-Z]|[IVXLCDM]+)(?:[\.\)]\d+)*[\.\)]?\s*(?::\s*)?"
    kern = re.sub(gliederung, "", sauber, flags=re.IGNORECASE).strip()
    if not kern:
        return False

    abk_muster = r"\b(?:z\.?\s*B|d\.?\s*h|u\.?\s*a|bzw|etc|ca|vgl|usw|Dr|Prof|Nr|Aufl|vs|Inc|e\.?\s*V)\."
    ohne_abk = re.sub(abk_muster, "ABK", kern, flags=re.IGNORECASE)
    ohne_abk = re.sub(r"\b\d+\.\d+\b", "ZAHL", ohne_abk)
    enden = list(re.finditer(r"[.!?]+['\"»”\)]*(?:\s+|$)", ohne_abk))
    if not enden:
        return True
    if len(enden) == 1 and enden[0].end() >= len(ohne_abk.rstrip()):
        return True
    return False


def isbn_bereinigen(roh: str) -> Optional[str]:
    """Bereinigt eine ISBN und behält nur Ziffern sowie ein mögliches Prüfzeichen X."""
    if not roh:
        return None
    s = re.sub(r"[^0-9X]", "", roh.upper())
    return s if len(s) in (10, 13) else None


def ist_gueltige_isbn(roh: str) -> bool:
    """Validiert ISBN-10 oder ISBN-13 anhand ihrer Prüfziffer."""
    s = isbn_bereinigen(roh)
    if not s:
        return False
    if len(s) == 10:
        summe = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(s))
        return summe % 11 == 0
    summe = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(s))
    return summe % 10 == 0


def isbns_extrahieren(text: str) -> List[str]:
    """Extrahiert alle gültigen ISBN-10 und ISBN-13 Nummern aus einem Text."""
    m13 = re.findall(r"\b(?:ISBN(?:-13)?:?\s*)?(97[89][\s\-]*(?:\d[\s\-]*){9}\d)\b", text, re.I)
    m10 = re.findall(r"\b(?:ISBN(?:-10)?:?\s*)?(\d[\s\-]*(?:\d[\s\-]*){8}[\dXx])\b", text, re.I)
    ergebnis: List[str] = []
    for kandidat in m13 + m10:
        sauber = isbn_bereinigen(kandidat)
        if sauber and ist_gueltige_isbn(sauber) and sauber not in ergebnis:
            ergebnis.append(sauber)
    return ergebnis


def ist_apa_zitat(text: str) -> bool:
    """Erkennt, ob ein Absatz einen APA-Quellennachweis darstellt."""
    s = text.strip()
    if len(s) < 10:
        return False
    if isbns_extrahieren(s):
        return True
    m_jahr = re.search(r"\(\s*(?:(?:19|20)\d{2}|n\.d\.|o\.\s*D\.)(?:,\s*[^)]+)?\s*\)", s)
    if not m_jahr:
        return False
    vorspann = s[: m_jahr.start()].strip()
    if not vorspann or len(vorspann) > 150:
        return False
    if any(k in s for k in ("http://", "https://", "doi.org", "doi:", "S.", "pp.", "Vol.", "Nr.", "Issue", "Hrsg.", "Ed.", "Eds.", "In ", "in ")):
        return True
    danach = s[m_jahr.end() :].strip()
    return danach.startswith((".", ":"))


def sprache_erkennen(rohtext: str, vorgegeben: str = "de") -> str:
    """Erkennt anhand häufiger Funktionswörter grob die Dokumentsprache (de, en oder es)."""
    if not rohtext or vorgegeben != "de":
        return vorgegeben
    woerter = re.findall(r"\b[A-Za-zÀ-ÿ]+\b", rohtext.lower())
    en_stop = {"the", "and", "in", "of", "to", "with", "is", "that", "for", "on", "as", "by", "this", "from"}
    es_stop = {"el", "la", "los", "las", "un", "una", "de", "en", "y", "que", "por", "para", "con", "del", "al"}
    de_stop = {"der", "die", "das", "und", "in", "von", "zu", "mit", "ist", "dass", "für", "auf", "als"}
    en_anzahl = sum(1 for w in woerter if w in en_stop)
    es_anzahl = sum(1 for w in woerter if w in es_stop)
    de_anzahl = sum(1 for w in woerter if w in de_stop)
    if es_anzahl > de_anzahl and es_anzahl > en_anzahl and es_anzahl >= 10:
        return "es"
    if en_anzahl > de_anzahl and en_anzahl >= 10:
        return "en"
    return vorgegeben
