# -*- coding: utf-8 -*-
"""APA-7-Quellennachweise, Metadatenauflösung für DOIs/ISBNs/Webseiten und Literaturverzeichnis."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
import json
import os
import re
import threading
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request

from .konfiguration import BIBLIOGRAFIE_WOERTER_MUSTER, ZITATE_CACHE_DATEI
from .markdown_typst import (
    typst_maskieren,
    typst_zeichenkette_maskieren,
    ueberschrift_typst_erzeugen,
    url_bereinigen,
)
from .textanalyse import isbn_bereinigen, isbns_extrahieren

_CACHE_SPERRE = threading.Lock()


def zitate_cache_laden() -> Dict[str, dict]:
    """Lädt zwischengespeicherte Zitationsmetadaten threadsicher."""
    with _CACHE_SPERRE:
        if os.path.exists(ZITATE_CACHE_DATEI):
            try:
                with open(ZITATE_CACHE_DATEI, "r", encoding="utf-8") as f:
                    daten = json.load(f)
                    return daten if isinstance(daten, dict) else {}
            except Exception:
                return {}
        return {}


def zitate_cache_speichern(cache: Dict[str, dict]) -> None:
    """Speichert Zitationsmetadaten atomar im Cache-Verzeichnis."""
    with _CACHE_SPERRE:
        try:
            os.makedirs(os.path.dirname(ZITATE_CACHE_DATEI), exist_ok=True)
            temp_datei = f"{ZITATE_CACHE_DATEI}.tmp"
            with open(temp_datei, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            os.replace(temp_datei, ZITATE_CACHE_DATEI)
        except Exception:
            pass


def autorenname_nach_apa(rohname: str) -> str:
    """Wandelt einen Personennamen in das APA-Format 'Nachname, I.' um."""
    s = unescape(rohname).strip().rstrip(".,;:")
    s = re.sub(r"^(?:Prof\.|Dr\.|PD|Dipl\.-[A-Za-z]+|M\.Sc\.|B\.Sc\.|Dr\. med\.)\s+", "", s, flags=re.I).strip()
    if not s:
        return ""
    if "," in s:
        teile = [p.strip() for p in s.split(",", 1)]
        nachname = teile[0]
        vorname = teile[1]
        vornamen = [t for t in vorname.split() if t and not t.endswith(".")]
        initialen_alt = [t for t in vorname.split() if t and t.endswith(".")]
        initialen = " ".join([f"{t[0]}." for t in vornamen] + initialen_alt)
        return f"{nachname}, {initialen}".strip()

    woerter = s.split()
    if len(woerter) == 1:
        return woerter[0]
    praefixe = {"an", "der", "von", "van", "de", "den", "zu", "ter", "vom", "di", "del", "da"}
    if len(woerter) >= 3 and woerter[-3].lower() in praefixe:
        nachname = " ".join(woerter[-3:])
        vor_woerter = woerter[:-3]
    elif len(woerter) >= 2 and woerter[-2].lower() in praefixe:
        nachname = " ".join(woerter[-2:])
        vor_woerter = woerter[:-2]
    else:
        nachname = woerter[-1]
        vor_woerter = woerter[:-1]
    initialen = " ".join(f"{t[0]}." for t in vor_woerter if t)
    return f"{nachname}, {initialen}".strip()


def autorenliste_nach_apa(autoren: List[str]) -> str:
    """Formatiert eine Liste von Autoren gemäß APA 7."""
    bereinigt: List[str] = []
    gesehen = set()
    for a in autoren:
        apa = autorenname_nach_apa(a)
        if apa and apa.lower() not in gesehen:
            gesehen.add(apa.lower())
            bereinigt.append(apa)
    if not bereinigt:
        return ""
    if len(bereinigt) == 1:
        return bereinigt[0]
    if len(bereinigt) <= 20:
        return ", ".join(bereinigt[:-1]) + " & " + bereinigt[-1]
    return ", ".join(bereinigt[:19]) + ", ... " + bereinigt[-1]


def _ist_ungueltiger_autor(autor: Optional[str]) -> bool:
    if not autor:
        return True
    a_klein = autor.lower().strip().rstrip(".")
    if a_klein in ("doi.org", "dx.doi.org", "doi", "crossref", "datacite", "o. a.", "ohne autor", "n. a.", "untitled", "unknown"):
        return True
    return bool(re.match(r"^10\.\d{4,9}/", a_klein))


def _ist_ungueltiger_titel(titel: Optional[str]) -> bool:
    if not titel:
        return True
    t_klein = titel.strip().rstrip(".").lower()
    if t_klein in ("untitled", "ohne titel", "doi.org", "dx.doi.org"):
        return True
    return bool(re.match(r"^(?:s\d{4,5}|\d{4,6}\.\d+|10\.\d{4,9})", t_klein))


def _autoren_aus_json_ld(html_text: str) -> List[str]:
    autoren: List[str] = []
    skripte = re.findall(r"<script[^>]+type=[\'\"]application/ld\+json[\'\"][^>]*>(.*?)</script>", html_text, re.I | re.S)
    for s in skripte:
        try:
            daten = json.loads(s.strip())
            eintraege = daten if isinstance(daten, list) else [daten]
            for eintrag in eintraege:
                if not isinstance(eintrag, dict):
                    continue
                auth = eintrag.get("author") or eintrag.get("creator")
                if isinstance(auth, list):
                    for a in auth:
                        if isinstance(a, dict) and a.get("name"):
                            autoren.append(str(a["name"]))
                        elif isinstance(a, str):
                            autoren.append(a)
                elif isinstance(auth, dict) and auth.get("name"):
                    autoren.append(str(auth["name"]))
                elif isinstance(auth, str):
                    autoren.append(auth)
        except Exception:
            pass
    return autoren


def _autoren_aus_html(html_text: str) -> List[str]:
    autoren: List[str] = []
    gesehen = set()

    for a in _autoren_aus_json_ld(html_text):
        a_sauber = a.strip()
        if a_sauber and a_sauber.lower() not in gesehen:
            gesehen.add(a_sauber.lower())
            autoren.append(a_sauber)

    meta_muster = [
        r"<meta[^>]+(?:name|property)=[\'\"](?:citation_author|dc\.creator|author|article:author|dc\.contributor\.author|byl|sailthru\.author|parsely-author)[\'\"][^>]+content=[\'\"]([^\'\"]+)[\'\"]",
        r"<meta[^>]+content=[\'\"]([^\'\"]+)[\'\"][^>]+(?:name|property)=[\'\"](?:citation_author|dc\.creator|author|article:author|dc\.contributor\.author)[\'\"]",
    ]
    stopp = ("redaktion", "admin", "editorial", "team", "verlag", "press")
    for pat in meta_muster:
        for m in re.finditer(pat, html_text, re.I):
            wert = unescape(m.group(1)).strip()
            teile = [sp.strip() for sp in wert.split(";") if sp.strip()] if ";" in wert else [wert]
            for sp in teile:
                if sp and sp.lower() not in gesehen and len(sp) <= 80:
                    if not any(sw in sp.lower() for sw in stopp):
                        gesehen.add(sp.lower())
                        autoren.append(sp)
    return autoren


def _strukturierte_autoren_formatieren(autoren_daten: List[dict], familien_feld: str, vorname_feld: str) -> str:
    """Einheitliche Formatierung strukturierter Autorenlisten aus CSL-JSON, Crossref und DataCite."""
    liste: List[str] = []
    for a in autoren_daten[:20]:
        fam = str(a.get(familien_feld) or "").strip()
        giv = str(a.get(vorname_feld) or "").strip()
        if fam:
            init = f"{giv[0]}." if giv else ""
            liste.append(f"{fam}, {init}".strip())
        elif a.get("name") or a.get("literal"):
            lit = str(a.get("name") or a.get("literal")).strip()
            ist_org = any(w in lit.lower() for w in ("institut", "institute", "organization", "organisation", "gmbh", "association", "office", "rki", "who", "bundesamt", "center", "centre"))
            if ist_org:
                liste.append(lit)
            elif " " in lit or "," in lit:
                apa_lit = autorenname_nach_apa(lit)
                if apa_lit:
                    liste.append(apa_lit)
    if len(autoren_daten) > 20:
        letzter = autoren_daten[-1]
        l_fam = str(letzter.get(familien_feld) or "").strip()
        l_giv = str(letzter.get(vorname_feld) or "").strip()
        l_init = f"{l_giv[0]}." if l_giv else ""
        return ", ".join(liste[:19]) + ", ... " + f"{l_fam}, {l_init}".strip()
    if len(liste) > 1:
        return ", ".join(liste[:-1]) + " & " + liste[-1]
    return liste[0] if liste else ""


def doi_metadaten_abrufen(doi_str: str, saubere_url: str) -> Optional[Dict[str, str]]:
    """Ruft Metadaten zu einer DOI über CSL-JSON, Crossref und DataCite ab."""
    doi_sauber = doi_str.strip().strip("/")
    benutzer_kennung = "txt2pdf/2.0"

    # 1. CSL-JSON via doi.org
    try:
        anfrage = urllib.request.Request(
            f"https://doi.org/{doi_sauber}",
            headers={"Accept": "application/vnd.citationstyles.csl+json", "User-Agent": benutzer_kennung},
        )
        with urllib.request.urlopen(anfrage, timeout=4.0) as antwort:
            daten = json.loads(antwort.read().decode("utf-8"))
            titel = str(daten.get("title") or "")
            if daten.get("subtitle"):
                titel = f"{titel}: {daten['subtitle']}"
            auth_str = _strukturierte_autoren_formatieren(daten.get("author", []), "family", "given")
            jahr = ""
            if "issued" in daten and "date-parts" in daten["issued"] and daten["issued"]["date-parts"]:
                jahr = str(daten["issued"]["date-parts"][0][0])
            quelle = daten.get("container-title") or daten.get("publisher") or ""
            if isinstance(quelle, list):
                quelle = quelle[0] if quelle else ""
            if titel and not _ist_ungueltiger_titel(titel):
                return {
                    "author": auth_str if not _ist_ungueltiger_autor(auth_str) else "",
                    "year": jahr,
                    "title": titel,
                    "source": str(quelle),
                    "url": saubere_url,
                }
    except Exception:
        pass

    # 2. Crossref REST
    try:
        anfrage = urllib.request.Request(
            f"https://api.crossref.org/works/{doi_sauber}",
            headers={"User-Agent": benutzer_kennung},
        )
        with urllib.request.urlopen(anfrage, timeout=4.0) as antwort:
            daten = json.loads(antwort.read().decode("utf-8")).get("message", {})
            titel_liste = daten.get("title", [])
            titel = str(titel_liste[0]) if titel_liste else ""
            if daten.get("subtitle"):
                titel = f"{titel}: {daten['subtitle'][0]}"
            auth_str = _strukturierte_autoren_formatieren(daten.get("author", []), "family", "given")
            jahr = ""
            datum_info = daten.get("published-print") or daten.get("issued") or daten.get("created")
            if datum_info and datum_info.get("date-parts"):
                jahr = str(datum_info["date-parts"][0][0])
            container = daten.get("container-title", [])
            quelle = container[0] if container else daten.get("publisher", "")
            if titel and not _ist_ungueltiger_titel(titel):
                return {
                    "author": auth_str if not _ist_ungueltiger_autor(auth_str) else "",
                    "year": jahr,
                    "title": titel,
                    "source": str(quelle),
                    "url": saubere_url,
                }
    except Exception:
        pass

    # 3. DataCite REST
    try:
        anfrage = urllib.request.Request(
            f"https://api.datacite.org/dois/{doi_sauber}",
            headers={"User-Agent": benutzer_kennung},
        )
        with urllib.request.urlopen(anfrage, timeout=4.0) as antwort:
            daten = json.loads(antwort.read().decode("utf-8")).get("data", {}).get("attributes", {})
            titel_liste = daten.get("titles", [])
            titel = str(titel_liste[0].get("title", "")) if titel_liste else ""
            auth_str = _strukturierte_autoren_formatieren(daten.get("creators", []), "familyName", "givenName")
            jahr = str(daten.get("publicationYear") or "")
            quelle = str(daten.get("publisher") or "")
            if titel and not _ist_ungueltiger_titel(titel):
                return {
                    "author": auth_str if not _ist_ungueltiger_autor(auth_str) else "",
                    "year": jahr,
                    "title": titel,
                    "source": quelle,
                    "url": saubere_url,
                }
    except Exception:
        pass

    return None


def isbn_metadaten_abrufen(isbn_str: str) -> Optional[Dict[str, Any]]:
    """Ruft Buchmetadaten zu einer ISBN über Open Library und Lobid (DNB) ab."""
    c_isbn = isbn_bereinigen(isbn_str)
    if not c_isbn:
        return None

    cache_schluessel = f"isbn:{c_isbn}"
    cache = zitate_cache_laden()
    if cache_schluessel in cache:
        eintrag = cache[cache_schluessel]
        if eintrag.get("title") and not _ist_ungueltiger_titel(eintrag.get("title")):
            return eintrag

    titel = ""
    autoren: List[str] = []
    jahr = ""
    verlag = ""

    # 1. Open Library Books
    try:
        anfrage = urllib.request.Request(
            f"https://openlibrary.org/isbn/{c_isbn}.json",
            headers={"User-Agent": "txt2pdf/2.0"},
        )
        with urllib.request.urlopen(anfrage, timeout=3.5) as antwort:
            daten = json.loads(antwort.read().decode("utf-8"))
            titel = str(daten.get("title", ""))
            if daten.get("subtitle"):
                titel = f"{titel}: {daten['subtitle']}"
            verlage = daten.get("publishers", [])
            verlag = str(verlage[0]) if verlage else ""
            pub_datum = str(daten.get("publish_date", ""))
            m_jahr = re.search(r"\b(1[89]\d{2}|20\d{2})\b", pub_datum)
            if m_jahr:
                jahr = m_jahr.group(1)

            for a_ent in daten.get("authors", []):
                a_key = a_ent.get("key") if isinstance(a_ent, dict) else None
                if a_key:
                    try:
                        with urllib.request.urlopen(
                            urllib.request.Request(f"https://openlibrary.org{a_key}.json", headers={"User-Agent": "txt2pdf/2.0"}),
                            timeout=2.5,
                        ) as a_ant:
                            a_daten = json.loads(a_ant.read().decode("utf-8"))
                            if a_daten.get("name"):
                                autoren.append(str(a_daten["name"]))
                    except Exception:
                        pass

            if not autoren and daten.get("works"):
                w_key = daten["works"][0].get("key")
                if w_key:
                    try:
                        with urllib.request.urlopen(
                            urllib.request.Request(f"https://openlibrary.org{w_key}.json", headers={"User-Agent": "txt2pdf/2.0"}),
                            timeout=2.5,
                        ) as w_ant:
                            w_daten = json.loads(w_ant.read().decode("utf-8"))
                            for wa in w_daten.get("authors", []):
                                wa_autor = wa.get("author", {}) if isinstance(wa, dict) else {}
                                wa_key = wa_autor.get("key")
                                if wa_key:
                                    try:
                                        with urllib.request.urlopen(
                                            urllib.request.Request(f"https://openlibrary.org{wa_key}.json", headers={"User-Agent": "txt2pdf/2.0"}),
                                            timeout=2.5,
                                        ) as a_ant:
                                            a_daten = json.loads(a_ant.read().decode("utf-8"))
                                            if a_daten.get("name"):
                                                autoren.append(str(a_daten["name"]))
                                    except Exception:
                                        pass
                    except Exception:
                        pass
    except Exception:
        pass

    # 2. Open Library Search
    if not autoren or not verlag or not jahr or not titel:
        try:
            anfrage = urllib.request.Request(
                f"https://openlibrary.org/search.json?isbn={c_isbn}&limit=1",
                headers={"User-Agent": "txt2pdf/2.0"},
            )
            with urllib.request.urlopen(anfrage, timeout=3.5) as antwort:
                docs = json.loads(antwort.read().decode("utf-8")).get("docs", [])
                if docs:
                    d = docs[0]
                    titel = titel or str(d.get("title", ""))
                    if not autoren:
                        autoren = [str(a) for a in d.get("author_name", [])]
                    jahr = jahr or str(d.get("first_publish_year") or "")
                    if not verlag:
                        pubs = d.get("publisher", [])
                        verlag = str(pubs[0]) if pubs else ""
        except Exception:
            pass

    # 3. Lobid DNB
    if not titel or not autoren:
        try:
            anfrage = urllib.request.Request(
                f"https://lobid.org/resources/{c_isbn}.json",
                headers={"User-Agent": "txt2pdf/2.0"},
            )
            with urllib.request.urlopen(anfrage, timeout=3.5) as antwort:
                daten = json.loads(antwort.read().decode("utf-8"))
                if not titel:
                    titel = str(daten.get("title", "")).replace("¬", "").strip()
                if not jahr:
                    pub_ev = daten.get("publication", [])
                    if pub_ev and isinstance(pub_ev, list):
                        ev0 = pub_ev[0]
                        yr_val = str(ev0.get("startDate") or ev0.get("dateStatement") or "")
                        m_yr = re.search(r"\b(1[89]\d{2}|20\d{2})\b", yr_val)
                        if m_yr:
                            jahr = m_yr.group(1)
                        if not verlag:
                            pubs = ev0.get("publishedBy", [])
                            locs = ev0.get("location", [])
                            verlag = str(pubs[0]) if pubs else (str(locs[0]) if locs else "")
                if not autoren:
                    beitraege = daten.get("contribution", [])
                    for c in beitraege:
                        rolle = c.get("role", {})
                        r_id = str(rolle.get("id", ""))
                        r_lbl = str(rolle.get("label", "")).lower()
                        if "/aut" in r_id or "autor" in r_lbl or "author" in r_lbl:
                            ag = c.get("agent", {})
                            if ag.get("label"):
                                autoren.append(str(ag["label"]))
                    if not autoren:
                        for c in beitraege:
                            r_id = str(c.get("role", {}).get("id", ""))
                            if not any(st in r_id for st in ("trl", "dtc", "pbl", "prt")):
                                ag = c.get("agent", {})
                                if ag.get("label") and ag.get("type") == ["Person"]:
                                    autoren.append(str(ag["label"]))
        except Exception:
            pass

    if titel and not _ist_ungueltiger_titel(titel):
        auth_str = autorenliste_nach_apa(autoren) if autoren else ""
        ergebnis = {
            "type": "book",
            "author": auth_str if not _ist_ungueltiger_autor(auth_str) else "",
            "year": jahr,
            "title": titel,
            "publisher": verlag,
            "source": verlag,
            "isbn": c_isbn,
            "url": "",
        }
        cache[cache_schluessel] = ergebnis
        zitate_cache_speichern(cache)
        return ergebnis

    return None


def link_untersuchen(url: str) -> Optional[Dict[str, str]]:
    """Extrahiert Metadaten für einen Weblink oder eine DOI."""
    saubere_url = url_bereinigen(url)
    if not saubere_url:
        return None

    cache = zitate_cache_laden()
    if saubere_url in cache:
        eintrag = cache[saubere_url]
        if eintrag.get("title") and not _ist_ungueltiger_titel(eintrag.get("title")) and not _ist_ungueltiger_autor(eintrag.get("author")):
            return eintrag

    doi_treffer = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", saubere_url)
    ist_doi = "doi.org" in saubere_url or bool(doi_treffer)
    if ist_doi:
        doi_str = doi_treffer.group(0) if doi_treffer else saubere_url.split("doi.org/")[-1].strip("/")
        doi_meta = doi_metadaten_abrufen(doi_str, saubere_url)
        if doi_meta:
            cache[saubere_url] = doi_meta
            zitate_cache_speichern(cache)
            return doi_meta
        return None

    geparst = urllib.parse.urlparse(saubere_url)
    domain = re.sub(r"^www\.", "", geparst.netloc.lower())
    inst_karte = {
        "destatis.de": "Statistisches Bundesamt",
        "rki.de": "Robert Koch-Institut",
        "who.int": "World Health Organization",
        "spiegel.de": "Der Spiegel",
        "zeit.de": "Die Zeit",
        "faz.net": "Frankfurter Allgemeine Zeitung",
        "sueddeutsche.de": "Süddeutsche Zeitung",
        "tagesschau.de": "Tagesschau",
        "taz.de": "Die Tageszeitung",
        "bundesregierung.de": "Die Bundesregierung",
        "bmg.bund.de": "Bundesministerium für Gesundheit",
        "reuters.com": "Reuters",
        "bloomberg.com": "Bloomberg",
        "wikipedia.org": "Wikipedia",
        "nature.com": "Nature",
        "thelancet.com": "The Lancet",
        "arxiv.org": "arXiv",
        "bertelsmann-stiftung.de": "Bertelsmann Stiftung",
        "mckinsey.de": "McKinsey & Company",
        "mckinsey.com": "McKinsey & Company",
    }

    seitenname = inst_karte.get(domain, domain.capitalize())
    if domain in ("doi.org", "dx.doi.org", "crossref.org"):
        seitenname = ""

    titel = ""
    autor = ""
    jahr = ""

    try:
        anfrage = urllib.request.Request(
            saubere_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; txt2pdf/2.0)"},
        )
        with urllib.request.urlopen(anfrage, timeout=3.5) as antwort:
            inhaltstyp = antwort.headers.get("Content-Type", "")
            if "html" in inhaltstyp or "text" in inhaltstyp:
                html = antwort.read(250000).decode("utf-8", errors="replace")

                og_t = re.search(r'<meta[^>]+property=[\'"]og:title[\'"][^>]+content=[\'"](.*?)[\'"]', html, re.I)
                if og_t:
                    titel = og_t.group(1).strip()
                else:
                    tm = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
                    if tm:
                        titel = tm.group(1).strip()

                og_s = re.search(r'<meta[^>]+property=[\'"]og:site_name[\'"][^>]+content=[\'"](.*?)[\'"]', html, re.I)
                if og_s:
                    seitenname = unescape(og_s.group(1).strip())

                html_autoren = _autoren_aus_html(html)
                if html_autoren:
                    autor = autorenliste_nach_apa(html_autoren)

                m_json_datum = re.search(r'["\'](?:datePublished|dateCreated|dateModified|uploadDate)["\']\s*:\s*["\'](\d{4})', html, re.I)
                if m_json_datum:
                    jahr = m_json_datum.group(1)

                if not jahr:
                    datums_meta_muster = [
                        r'<meta[^>]+(?:name|property|itemprop)=[\'"](?:article:published_time|og:published_time|date|pubdate|publishdate|dc\.date|dc\.date\.issued|dc\.date\.created|sailthru\.date|parsely-pub-date|article:modified_time|og:updated_time)[\'"][^>]+content=[\'"](\d{4})',
                        r'<meta[^>]+content=[\'"](\d{4})[^>]*[\'"][^>]+(?:name|property|itemprop)=[\'"](?:article:published_time|og:published_time|date|pubdate|publishdate|dc\.date)[\'"]',
                    ]
                    for pat in datums_meta_muster:
                        m_m = re.search(pat, html, re.I)
                        if m_m:
                            jahr = m_m.group(1)
                            break

                if not jahr:
                    m_time = re.search(r'<time[^>]+datetime=[\'"](\d{4})', html, re.I)
                    if m_time:
                        jahr = m_time.group(1)
                    else:
                        m_tt = re.search(r"<time[^>]*>[^<]*?\b((?:19|20)\d{2})\b[^<]*?</time>", html, re.I)
                        if m_tt:
                            jahr = m_tt.group(1)

                if not jahr:
                    m_de = re.search(
                        r"\b\d{1,2}\.?\s*(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|Jan|Feb|Mär|Apr|Mai|Jun|Jul|Aug|Sep|Okt|Nov|Dez)\.?\s*((?:19|20)\d{2})\b",
                        html,
                        re.I,
                    )
                    if m_de:
                        jahr = m_de.group(1)
                    else:
                        m_en = re.search(
                            r"\b(?:(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*((?:19|20)\d{2})|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+((?:19|20)\d{2}))\b",
                            html,
                            re.I,
                        )
                        if m_en:
                            jahr = m_en.group(1) or m_en.group(2)

                if not jahr:
                    m_iso = re.search(
                        r"\b(?:Stand:?\s*|Datum:?\s*|Veröffentlicht:?\s*)?(?:((?:19|20)\d{2})[-/.](?:0[1-9]|1[0-2])[-/.](?:0[1-9]|[12]\d|3[01])|(?:0[1-9]|[12]\d|3[01])\.(?:0[1-9]|1[0-2])\.((?:19|20)\d{2}))\b",
                        html,
                        re.I,
                    )
                    if m_iso:
                        jahr = m_iso.group(1) or m_iso.group(2)
    except Exception:
        pass

    titel = unescape(titel)
    if not titel:
        pfad = geparst.path.strip("/")
        letztes_seg = pfad.split("/")[-1] if pfad else domain
        m_slug = re.match(r"^(\d{4})[-_](\d{2})[-_](\d{2})[-_]+(.*)$", letztes_seg)
        if m_slug:
            jahr = jahr or m_slug.group(1)
            letztes_seg = m_slug.group(4)
        titel = letztes_seg.replace("-", " ").replace("_", " ").capitalize()

    if seitenname:
        titel = re.sub(r"\s*[\-|–—|]\s*" + re.escape(seitenname) + r".*$", "", titel, flags=re.I).strip()
    if not autor and seitenname and not _ist_ungueltiger_autor(seitenname):
        autor = seitenname

    if not jahr:
        url_jahr = re.search(r"/((?:19|20)\d{2})(?:[-_/]|$)", saubere_url)
        if url_jahr:
            jahr = url_jahr.group(1)

    if _ist_ungueltiger_autor(autor):
        autor = ""
    if _ist_ungueltiger_titel(titel):
        titel = ""

    ergebnis = {
        "author": autor,
        "year": jahr,
        "title": titel,
        "source": seitenname if (autor and seitenname and autor.lower() != seitenname.lower()) else "",
        "url": saubere_url,
    }
    if ergebnis["title"]:
        cache[saubere_url] = ergebnis
        zitate_cache_speichern(cache)
    return ergebnis


def _datum_im_kontext_finden(
    rohzitat: str,
    saubere_url: str,
    link_meta: Optional[dict],
    kontext_text: str,
) -> Optional[str]:
    if not kontext_text or not kontext_text.strip():
        return None

    suchbegriffe: List[str] = []
    if saubere_url:
        geparst = urllib.parse.urlparse(saubere_url)
        for teil in geparst.netloc.lower().replace("www.", "").split("."):
            if len(teil) >= 4 and teil not in ("com", "org", "net", "de", "edu", "info", "html"):
                suchbegriffe.append(teil)
        for slug in re.findall(r"[A-Za-z0-9äöüÄÖÜß]{4,}", geparst.path):
            if slug.lower() not in ("detail", "news", "html", "index", "article", "tarif", "faq"):
                suchbegriffe.append(slug.lower())

    if link_meta:
        for feld in ("author", "source", "title"):
            wert = str(link_meta.get(feld, ""))
            if wert and wert not in ("O. A.", "Ohne Autor"):
                for w in re.findall(r"[A-Za-z0-9äöüÄÖÜß]{4,}", wert):
                    if w.lower() not in ("software", "gmbh", "redaktion", "verband"):
                        suchbegriffe.append(w.lower())

    for w in re.findall(r"[A-Za-z0-9äöüÄÖÜß]{4,}", rohzitat):
        wk = w.lower()
        if not wk.startswith("http") and wk not in ("https", "quellen", "quelle", "literatur", "references", "works", "cited"):
            suchbegriffe.append(wk)

    suchbegriffe = list(dict.fromkeys(suchbegriffe))
    if not suchbegriffe:
        return None

    absaetze = [p.strip() for p in kontext_text.split("\n\n") if p.strip()]
    treffer = []
    for idx, p in enumerate(absaetze):
        p_klein = p.lower()
        punkte = sum(1 for begr in suchbegriffe if begr in p_klein)
        if punkte > 0:
            treffer.append((punkte, idx, p))
    treffer.sort(key=lambda x: x[0], reverse=True)

    datums_muster = [
        re.compile(r"\b(?:aus\s+dem|vom|im\s+Jahr(?:e)?|im|Stand:?)\s*(?:(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|Jan|Feb|Mär|Apr|Mai|Jun|Jul|Aug|Sep|Okt|Nov|Dez)\.?\s+)?((?:19|20)\d{2})\b", re.I),
        re.compile(r"\b(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+((?:19|20)\d{2})\b", re.I),
        re.compile(r"\b(19\d{2}|20(?:[0-2]\d|3[0-5]))\b"),
    ]

    for _, idx, p in treffer:
        for reg in datums_muster:
            m = reg.search(p)
            if m:
                return m.group(1)
        if idx > 0:
            for reg in datums_muster:
                m = reg.search(absaetze[idx - 1])
                if m:
                    return m.group(1)
    return None


def _autor_im_kontext_finden(
    saubere_url: str,
    link_meta: Optional[dict],
    kontext_text: str,
) -> Optional[str]:
    if not kontext_text or not kontext_text.strip():
        return None

    suchbegriffe: List[str] = []
    if saubere_url:
        geparst = urllib.parse.urlparse(saubere_url)
        for teil in geparst.netloc.lower().replace("www.", "").split("."):
            if len(teil) >= 4 and teil not in ("com", "org", "net", "de", "edu", "info", "html"):
                suchbegriffe.append(teil)
        for slug in re.findall(r"[A-Za-z0-9äöüÄÖÜß]{4,}", geparst.path):
            if slug.lower() not in ("detail", "news", "html", "index", "article", "tarif", "faq"):
                suchbegriffe.append(slug.lower())

    if link_meta:
        for feld in ("title", "source"):
            wert = str(link_meta.get(feld, ""))
            if wert:
                for w in re.findall(r"[A-Za-z0-9äöüÄÖÜß]{4,}", wert):
                    if w.lower() not in ("mortalität", "deutschland", "studie", "bericht", "bundesamt", "institut"):
                        suchbegriffe.append(w.lower())

    suchbegriffe = list(dict.fromkeys(suchbegriffe))
    if not suchbegriffe:
        return None

    for p in (p.strip() for p in kontext_text.split("\n\n") if p.strip()):
        if any(t in p.lower() for t in suchbegriffe):
            m_auth = re.search(
                r"\b(?:von|by)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)*(?:\s+(?:und|and|&)\s+[A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)*)?)\b",
                p,
            )
            if m_auth:
                teile = re.split(r"\s+(?:und|and|&)\s+", m_auth.group(1).strip())
                gueltig = [t.strip() for t in teile if len(t.strip().split()) >= 2]
                if gueltig:
                    apa = autorenliste_nach_apa(gueltig)
                    if apa:
                        return apa
    return None


def zitat_nach_apa7(rohzitat: str, kontext_text: str = "") -> Dict[str, str]:
    """Formatiert eine Literaturangabe, eine ISBN, eine DOI oder eine URL nach APA 7."""
    sauber = rohzitat.strip()
    if not sauber:
        return {}

    bib_kopf_re = re.compile(rf"^(?:{BIBLIOGRAFIE_WOERTER_MUSTER})\b:?\s*$", re.IGNORECASE)
    if bib_kopf_re.match(sauber):
        return {}

    ist_en = False
    if kontext_text:
        en_woerter = {"the", "and", "in", "of", "to", "with", "is", "for", "references"}
        stichprobe = set(re.findall(r"\b[a-z]+\b", kontext_text.lower()))
        if len(stichprobe & en_woerter) >= 4:
            ist_en = True

    # 1. ISBN
    isbns = isbns_extrahieren(sauber)
    if isbns:
        erste_isbn = isbns[0]
        isbn_meta = isbn_metadaten_abrufen(erste_isbn)
        if isbn_meta:
            autor_w = isbn_meta.get("author") or ("N. A." if ist_en else "O. A.")
            jahr_w = isbn_meta.get("year") or ("n.d." if ist_en else "o. D.")
            titel_w = isbn_meta.get("title") or ("Untitled" if ist_en else "Ohne Titel")
            verlag_w = isbn_meta.get("publisher", "")

            m_extra = re.search(
                r"(?:(?:Kap\.|Kapitel|Chapter|Chap\.)\s*([0-9IVXLCDM]+|[A-Z])\b|(?:S\.|pp?\.)\s*(\d+(?:[-–—]\d+)?))",
                sauber,
                re.I,
            )
            extra = f" ({m_extra.group(0).strip()})" if m_extra else ""
            autor_teil = typst_maskieren(str(autor_w))
            if not autor_teil.endswith("."):
                autor_teil += "."
            clean_t = re.sub(r"^_*([^_]+)_*$", r"\1", str(titel_w)).strip().rstrip(".")
            titel_teil = f"_{typst_maskieren(clean_t)}_{typst_maskieren(extra)}."
            verlag_teil = f" {typst_maskieren(str(verlag_w))}." if verlag_w else ""
            formatiert = f"{autor_teil} ({jahr_w}). {titel_teil}{verlag_teil}".strip()
            return {
                "sort_key": str(autor_w).lower(),
                "formatted": formatiert,
                "clean_url": f"isbn:{erste_isbn}",
                "title_key": re.sub(r"[^a-z0-9]", "", str(titel_w).lower()),
            }

    # 2. Buchkapitel im Sammelband mit Herausgeber
    m_kap_hrsg = re.match(
        r"^(?P<author>.+?)\s*[\(\[](?P<year>[12]\d{3}[^\)\]]*)[\)\]][\.:]?\s*(?P<chapter>.+?)\.\s+[iI]n\s+(?P<editor>.+?)\s*[\(\[](?P<ed_label>Hrsg\.|Ed\.|Eds\.|Hg\.)[\)\]],?\s*(?P<book>.+?)(?:\s*[\(\[](?:(?:S\.|pp?\.)\s*)?(?P<pages>\d+(?:[-–—]\d+)?)[\]\)])?\.\s*(?P<publisher>.+)$",
        sauber,
    )
    if m_kap_hrsg:
        d = m_kap_hrsg.groupdict()
        auth_apa = autorenname_nach_apa(d["author"]) or d["author"].strip()
        auth_teil = typst_maskieren(auth_apa)
        if not auth_teil.endswith("."):
            auth_teil += "."
        kap_teil = typst_maskieren(d["chapter"].strip().rstrip(".")) + "."
        ed_lbl = d.get("ed_label") or ("Ed." if ist_en else "Hrsg.")
        in_teil = f"In {typst_maskieren(d['editor'].strip())} ({typst_maskieren(ed_lbl)}),"
        buch_sauber = re.sub(r"^_*([^_]+)_*$", r"\1", d["book"]).strip().rstrip(".")
        seiten = d.get("pages")
        seiten_zusatz = f" ({'pp. ' if ist_en else 'S. '}{seiten})" if seiten else ""
        buch_teil = f"_{typst_maskieren(buch_sauber)}_{typst_maskieren(seiten_zusatz)}."
        verlag_teil = f" {typst_maskieren(d['publisher'].strip().rstrip('.'))}."
        return {
            "sort_key": auth_apa.lower(),
            "formatted": f"{auth_teil} ({d['year'].strip()}). {kap_teil} {in_teil} {buch_teil}{verlag_teil}".strip(),
            "clean_url": "",
            "title_key": re.sub(r"[^a-z0-9]", "", d["chapter"].lower()),
        }

    # 3. Buchkapitel ohne expliziten Herausgeber (Hinweis: korrigiertes \s* statt \\s*)
    m_kap_ohne = re.match(
        r"^(?P<author>.+?)\s*[\(\[](?P<year>[12]\d{3}[^\)\]]*)[\)\]][\.:]?\s*(?P<chapter>.+?)\.\s+[iI]n\s+(?P<book>.+?)(?:\s*[\(\[](?:(?:S\.|pp?\.)\s*)?(?P<pages>\d+(?:[-–—]\d+)?)[\]\)])\.\s*(?P<publisher>.+)$",
        sauber,
    )
    if m_kap_ohne:
        d = m_kap_ohne.groupdict()
        auth_apa = autorenname_nach_apa(d["author"]) or d["author"].strip()
        auth_teil = typst_maskieren(auth_apa)
        if not auth_teil.endswith("."):
            auth_teil += "."
        kap_teil = typst_maskieren(d["chapter"].strip().rstrip(".")) + "."
        buch_sauber = re.sub(r"^_*([^_]+)_*$", r"\1", d["book"]).strip().rstrip(".")
        seiten = d.get("pages")
        seiten_zusatz = f" ({'pp. ' if ist_en else 'S. '}{seiten})" if seiten else ""
        buch_teil = f"In _{typst_maskieren(buch_sauber)}_{typst_maskieren(seiten_zusatz)}."
        verlag_teil = f" {typst_maskieren(d['publisher'].strip().rstrip('.'))}."
        return {
            "sort_key": auth_apa.lower(),
            "formatted": f"{auth_teil} ({d['year'].strip()}). {kap_teil} {buch_teil}{verlag_teil}".strip(),
            "clean_url": "",
            "title_key": re.sub(r"[^a-z0-9]", "", d["chapter"].lower()),
        }

    # 4. Monografie mit Auflage / Band
    m_buch_aufl = re.match(
        r"^(?P<author>.+?)\s*[\(\[](?P<year>[12]\d{3}[^\)\]]*)[\)\]][\.:]?\s*(?P<book>.+?)\s*[\(\[](?:(?P<edition>(?:\d+\.?\s*(?:Aufl\.|ed\.|Ausg\.)|Bd\.\s*\d+|Vol\.\s*\d+)[^()\]]*)|(?:S\.|pp?\.)\s*(?P<pages>\d+(?:[-–—]\d+)?))[\]\)][\.:]?\s*(?P<publisher>.+)$",
        sauber,
    )
    if m_buch_aufl and not m_buch_aufl.group("book").lower().startswith("http"):
        d = m_buch_aufl.groupdict()
        auth_apa = autorenname_nach_apa(d["author"]) or d["author"].strip()
        auth_teil = typst_maskieren(auth_apa)
        if not auth_teil.endswith("."):
            auth_teil += "."
        buch_sauber = re.sub(r"^_*([^_]+)_*$", r"\1", d["book"]).strip().rstrip(".")
        ed_w = d.get("edition") or (f"S. {d['pages']}" if d.get("pages") else "")
        ed_zusatz = f" ({ed_w.strip()})" if ed_w else ""
        buch_teil = f"_{typst_maskieren(buch_sauber)}_{typst_maskieren(ed_zusatz)}."
        verlag_teil = f" {typst_maskieren(d['publisher'].strip().rstrip('.'))}."
        return {
            "sort_key": auth_apa.lower(),
            "formatted": f"{auth_teil} ({d['year'].strip()}). {buch_teil}{verlag_teil}".strip(),
            "clean_url": "",
            "title_key": re.sub(r"[^a-z0-9]", "", d["book"].lower()),
        }

    # 5. Standard-Monografie: Autor (Jahr). Titel. Verlag.
    m_buch = re.match(r"^(?P<author>.+?)\s*[\(\[](?P<year>[12]\d{3}[^\)\]]*)[\)\]][\.:]?\s*(?P<rest>.+)$", sauber)
    if m_buch and "http" not in sauber:
        rest = m_buch.group("rest").strip().rstrip(".")
        teile = re.split(r"(?<!\b[A-ZÄÖÜ])\.\s+(?=[A-ZÄÖÜ])", rest)
        if len(teile) == 2:
            auth_apa = autorenname_nach_apa(m_buch.group("author")) or m_buch.group("author").strip()
            auth_teil = typst_maskieren(auth_apa)
            if not auth_teil.endswith("."):
                auth_teil += "."
            buch_sauber = re.sub(r"^_*([^_]+)_*$", r"\1", teile[0]).strip().rstrip(".")
            buch_teil = f"_{typst_maskieren(buch_sauber)}._"
            verlag_teil = f" {typst_maskieren(teile[1].strip().rstrip('.'))}."
            return {
                "sort_key": auth_apa.lower(),
                "formatted": f"{auth_teil} ({m_buch.group('year').strip()}). {buch_teil}{verlag_teil}".strip(),
                "clean_url": "",
                "title_key": re.sub(r"[^a-z0-9]", "", teile[0].lower()),
            }

    # 6. URL / DOI
    m_url = re.search(r'https?://[^\s<>"\'\[\]]+', sauber)
    saubere_url = url_bereinigen(m_url.group(0)) if m_url else ""
    link_meta = link_untersuchen(saubere_url) if saubere_url else None

    text_ohne_url = re.sub(r'https?://[^\s<>"\'\[\]]+', "", sauber).strip().rstrip(".,;:")
    if bib_kopf_re.match(text_ohne_url):
        return {}

    autor = ""
    datum = ""
    titel = ""
    quelle = ""

    m_zitat = re.match(r"^(.*?)\s*[\(\[]([12]\d{3}[^\)\]]*)[\)\]][\.:]?\s*(.*)$", text_ohne_url)
    if not saubere_url and not m_zitat:
        if len(text_ohne_url) < 15 or len(text_ohne_url.split()) < 3:
            return {}

    if m_zitat:
        autor = m_zitat.group(1).strip().rstrip(".,;:")
        datum = m_zitat.group(2).strip()
        rest = m_zitat.group(3).strip().rstrip(".,;:")
        teile = re.split(r"\.\s+(?=[A-ZÄÖÜ])", rest)
        if len(teile) > 1 and len(teile[-1]) <= 70:
            titel = ". ".join(teile[:-1]).strip().rstrip(".,;:")
            quelle = teile[-1].strip().rstrip(".,;:")
        else:
            titel = rest.strip().rstrip(".,;:")

    if link_meta:
        if link_meta.get("author") and (not autor or autor.lower() in link_meta.get("source", "").lower() or autor.lower() in ("o. a.", "ohne autor")):
            if autor and autor != link_meta["author"] and not quelle:
                quelle = autor
            autor = link_meta["author"]
        if link_meta.get("source") and not quelle and autor.lower() != link_meta["source"].lower():
            quelle = link_meta["source"]
        if not titel and link_meta.get("title"):
            titel = link_meta["title"]
        if not datum and link_meta.get("year"):
            datum = link_meta["year"]

    if not datum or datum in ("o. D.", "n.d."):
        datum_kontext = _datum_im_kontext_finden(sauber, saubere_url, link_meta, kontext_text)
        if datum_kontext:
            datum = datum_kontext

    if _ist_ungueltiger_autor(autor):
        autor = ""
    if _ist_ungueltiger_titel(titel):
        titel = ""

    if not autor:
        autor_kontext = _autor_im_kontext_finden(saubere_url, link_meta, kontext_text)
        if autor_kontext and not _ist_ungueltiger_autor(autor_kontext):
            autor = autor_kontext

    autor = autor or ("N. A." if ist_en else "O. A.")
    datum = datum or ("n.d." if ist_en else "o. D.")
    titel = titel or ("Untitled" if ist_en else "Ohne Titel")

    autor_teil = typst_maskieren(autor)
    if not autor_teil.endswith("."):
        autor_teil += "."
    clean_titel = re.sub(r"^_*([^_]+)_*$", r"\1", titel).strip().rstrip(".")
    titel_teil = f"_{typst_maskieren(clean_titel)}._"
    quelle_teil = f" {typst_maskieren(quelle)}." if quelle and quelle.lower() != autor.lower() else ""
    link_teil = ""
    if saubere_url:
        url_esc = typst_zeichenkette_maskieren(saubere_url)
        link_teil = f' #link("{url_esc}")[{typst_maskieren(saubere_url)}]'

    formatiert = f"{autor_teil} ({datum}). {titel_teil}{quelle_teil}{link_teil}".strip()
    return {
        "sort_key": autor.lower(),
        "formatted": formatiert,
        "clean_url": saubere_url,
        "title_key": re.sub(r"[^a-z0-9]", "", titel.lower()),
    }


def literaturverzeichnis_typst(
    urls: Optional[List[str]] = None,
    explizite_eintraege: Optional[List[str]] = None,
    bib_titel: str = "Literaturverzeichnis",
    schrift_angabe: str = '("PT Serif", "EB Garamond", "Tinos")',
    schriftgroesse: str = "8pt",
    titelgroesse: str = "14pt",
    kontext_text: str = "",
    haengender_einzug: str = "12.7mm",
    zeilenabstand: str = "0.55em",
    koerper_einzug_nutzen: bool = False,
    einzug_str: str = "3.8mm",
    trennlinie_anzeigen: bool = True,
    titel_schrift: Optional[str] = None,
    fmt: str = "atk2",
) -> str:
    """Erstellt das alphabetisch sortierte APA-7-Literaturverzeichnis in Typst (parallel aufgelöst)."""
    kandidaten: List[str] = []
    if explizite_eintraege:
        for e in explizite_eintraege:
            s_e = e.strip()
            if s_e and s_e not in kandidaten:
                kandidaten.append(s_e)
    if urls:
        for u in urls:
            s_u = u.strip()
            if s_u and s_u not in kandidaten:
                kandidaten.append(s_u)

    if not kandidaten:
        return ""

    # Paralleles Nachschlagen der Kandidaten beschleunigt Dokumente mit vielen Quellen enorm
    ergebnisse_nach_index: Dict[int, Dict[str, str]] = {}
    if len(kandidaten) == 1:
        ergebnisse_nach_index[0] = zitat_nach_apa7(kandidaten[0], kontext_text=kontext_text)
    else:
        with ThreadPoolExecutor(max_workers=min(6, len(kandidaten))) as pool:
            zukuenfte = {
                pool.submit(zitat_nach_apa7, eintrag, kontext_text): idx
                for idx, eintrag in enumerate(kandidaten)
            }
            for fut in as_completed(zukuenfte):
                idx = zukuenfte[fut]
                try:
                    ergebnisse_nach_index[idx] = fut.result()
                except Exception:
                    ergebnisse_nach_index[idx] = {}

    zitate: List[Dict[str, str]] = []
    gesehen_text = set()
    gesehen_urls = set()
    gesehen_titel = set()

    for idx in range(len(kandidaten)):
        cit = ergebnisse_nach_index.get(idx)
        if not cit or not cit.get("formatted"):
            continue
        norm_f = cit["formatted"].strip().lower()
        c_url = cit.get("clean_url", "").strip().lower()
        t_key = cit.get("title_key", "").strip().lower()

        if norm_f in gesehen_text:
            continue
        if c_url and c_url in gesehen_urls:
            continue
        if t_key and len(t_key) >= 15 and t_key in gesehen_titel:
            continue

        gesehen_text.add(norm_f)
        if c_url:
            gesehen_urls.add(c_url)
        if t_key and len(t_key) >= 15:
            gesehen_titel.add(t_key)
        zitate.append(cit)

    if not zitate:
        return ""

    zitate.sort(key=lambda c: c["sort_key"])

    eintraege_typst: List[str] = []
    if koerper_einzug_nutzen:
        for idx, c in enumerate(zitate):
            vorsatz = "" if idx == 0 else f"#h({einzug_str})"
            eintraege_typst.append(f"#block(inset: (bottom: 0pt))[\n  {vorsatz}{c['formatted']}\n]")
        par_haengend = "0pt"
    else:
        for c in zitate:
            eintraege_typst.append(f"#block(inset: (bottom: 3.5mm))[\n  {c['formatted']}\n]")
        par_haengend = haengender_einzug

    koerper = "\n".join(eintraege_typst)
    bib_schrift_arg = titel_schrift if titel_schrift else "none"
    h_esc = typst_maskieren(bib_titel)

    if fmt in ("atk1", "atk2", "atk3"):
        trenner = '#v(1.0em)\n#line(length: 100%, stroke: 0.3pt + rgb("#000000"))\n' if trennlinie_anzeigen else ""
        kopf = (
            f"{trenner}#render_section_heading([{h_esc}], align_center: true, "
            f"font_attr: {bib_schrift_arg}, font_size: {titelgroesse}, above_gap: 2.8em, below_gap: 2.8em)"
        )
    elif fmt in ("br1", "br2"):
        kopf = (
            f"#v(1.0em)\n#render_section_heading([{h_esc}], align_center: false, "
            f"font_attr: {bib_schrift_arg}, font_size: {titelgroesse}, above_gap: 2.0em, below_gap: 1.0em)"
        )
    else:
        trenner = '#v(1.0em)\n#line(length: 100%, stroke: 0.3pt + rgb("#000000"))\n#v(0.6em)\n' if trennlinie_anzeigen else "#v(1.0em)\n"
        kopf = (
            f"{trenner}#render_section_heading([{h_esc}], align_center: true, "
            f"font_attr: {bib_schrift_arg}, font_size: {titelgroesse}, above_gap: 1.2em, below_gap: 1.2em)"
        )

    return f"""
{kopf}

#show link: set text(fill: rgb("#0b57d0"))
#set text(font: {schrift_angabe}, size: {schriftgroesse}, hyphenate: true)
#set par(
  hanging-indent: {par_haengend},
  first-line-indent: 0pt,
  leading: {zeilenabstand},
  spacing: {zeilenabstand},
  justify: true,
  linebreaks: "optimized"
)

{koerper}
"""
