#!/usr/bin/env python3
"""
Récupère automatiquement l'emploi du temps ENT CESI via l'API JSON interne,
en s'authentifiant tout seul via le SSO ADFS (sts.viacesi.fr).

Flux d'authentification observé (juillet 2026) :
  1. GET  https://ent.cesi.fr/identification/wayf
     -> formulaire avec un seul champ "login" (POST vers /identification/wayf/)
  2. POST "login" -> redirige vers sts.viacesi.fr/adfs/ls/?login_hint=...
     -> formulaire ADFS classique : champs "UserName", "Password", "AuthMethod"
        (POST vers /adfs/ls/)
  3. ADFS répond par une page contenant un formulaire caché
     (SAMLResponse/wresult) qui se soumet automatiquement vers ent.cesi.fr.
        On rejoue ce POST nous-mêmes.
  4. Le cookie de session est posé sur ent.cesi.fr -> on peut appeler
     GET /api/seance/all?start=...&end=...&codePersonne=...

ATTENTION - à lire avant de s'en servir :
  - C'est un SSO Microsoft ADFS. S'il y a la moindre MFA / Conditional Access
    activée sur le compte, ce script s'arrêtera au niveau du login (il ne gère
    PAS les défis MFA). Il ne fonctionne que pour un login "UserName + Password"
    simple.
  - Les noms de champs ("login", "UserName", "Password", "AuthMethod") ont été
    relevés en inspectant le vrai formulaire HTML le 08/07/2026. Si CESI change
    son ENT ou son ADFS, ce script cassera silencieusement -> d'où les
    vérifications (raise) après chaque étape.
  - Ne commite jamais le fichier .env dans un dépôt git.
  - Vérifie que ton usage automatisé de l'ENT ne contrevient pas à la charte
    informatique CESI.

Usage :
  pip install -r requirements.txt
  cp .env.example .env   # puis remplis identifiant / mot de passe
  python cesi_edt_sync.py                     # semaine en cours
  python cesi_edt_sync.py 2026-07-13 2026-07-19  # semaine spécifique
"""

import os
import sys
import json
import datetime as dt
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

BASE = "https://ent.cesi.fr"
USERNAME = os.environ.get("CESI_USERNAME")
PASSWORD = os.environ.get("CESI_PASSWORD")
CODE_PERSONNE = os.environ.get("CESI_CODE_PERSONNE")

DEBUG = os.environ.get("CESI_DEBUG", "0") == "1"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}


def debug_step(label: str, r: requests.Response, session: requests.Session) -> None:
    if not DEBUG:
        return
    print(f"--- {label} ---", file=sys.stderr)
    print(f"status: {r.status_code}", file=sys.stderr)
    print(f"final url: {r.url}", file=sys.stderr)
    print(f"redirect chain: {[h.url for h in r.history]}", file=sys.stderr)
    print(
        f"session cookie names so far: {sorted(c.name for c in session.cookies)}",
        file=sys.stderr,
    )
    # Cherche un message d'erreur explicite dans le HTML rendu (pas de secret
    # à craindre ici, c'est du HTML public renvoyé par le serveur).
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    print(f"texte visible de la page (premiers 400 car.): {text[:400]}", file=sys.stderr)


def parse_form(html: str, base_url: str):
    """Extrait le premier <form> d'une page : (action absolue, dict des champs)."""
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form")
    if not form:
        return None, {}
    action = urljoin(base_url, form.get("action") or base_url)
    data = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if name:
            data[name] = inp.get("value", "")
    return action, data


def follow_auto_post_forms(
    session: requests.Session, r: requests.Response, max_hops: int = 6
) -> requests.Response:
    """Rejoue les formulaires caché auto-soumis (relais SAML/WS-Fed du type
    'votre navigateur ne supporte pas JS, cliquez sur Continuer') jusqu'à
    tomber sur un vrai formulaire de login (WAYF ou ADFS) ou sur une page
    sans formulaire (landing page)."""
    for _ in range(max_hops):
        soup = BeautifulSoup(r.text, "html.parser")
        form = soup.find("form")
        if not form:
            return r
        input_names = {
            inp.get("name") for inp in form.find_all("input") if inp.get("name")
        }
        if {"UserName", "Password"} & input_names:
            return r  # formulaire de login ADFS : on s'arrête, login() prend le relais
        if input_names == {"login"}:
            return r  # formulaire WAYF : on s'arrête, login() prend le relais
        # sinon : relais caché (SAMLResponse/wresult/RelayState...), on le rejoue
        action, data = parse_form(r.text, r.url)
        if action is None:
            return r
        r = session.post(action, data=data, headers={"Referer": r.url})
        if DEBUG:
            debug_step("relais auto-submit", r, session)
    return r


def login(session: requests.Session) -> None:
    if not USERNAME or not USERNAME.strip():
        raise SystemExit(
            "CESI_USERNAME est vide ou absent. Vérifie que le fichier .env "
            "est bien dans le même dossier que ce script, et que "
            "CESI_USERNAME=... n'a pas de guillemets ni d'espace en trop."
        )
    if not PASSWORD or not PASSWORD.strip():
        raise SystemExit(
            "CESI_PASSWORD est vide ou absent. Vérifie ton .env (même dossier "
            "que ce script)."
        )
    if DEBUG:
        masked = USERNAME[:3] + "***" if len(USERNAME) > 3 else "***"
        print(f"USERNAME chargé : {masked} (longueur {len(USERNAME)})", file=sys.stderr)
        print(f"PASSWORD chargé : longueur {len(PASSWORD)}", file=sys.stderr)

    # Étape 0 : page d'accueil, pour récupérer les cookies initiaux comme le
    # ferait un vrai navigateur (au cas où le WAYF les exige).
    r = session.get(f"{BASE}/", headers={"Referer": BASE + "/"})
    debug_step("accueil", r, session)

    # Étape 1 : WAYF
    r = session.get(f"{BASE}/identification/wayf", headers={"Referer": BASE + "/"})
    debug_step("GET wayf", r, session)
    action, data = parse_form(r.text, r.url)
    if action is None:
        raise RuntimeError("Formulaire WAYF introuvable - page probablement changée.")
    data["login"] = USERNAME
    r = session.post(action, data=data, headers={"Referer": r.url})
    debug_step("POST wayf", r, session)

    # Relais intermédiaires éventuels (pages "Continuer" auto-submit SAML/WS-Fed)
    r = follow_auto_post_forms(session, r)
    debug_step("après relais post-wayf", r, session)

    # Étape 2 : formulaire ADFS (username + password)
    if "adfs" not in r.url:
        raise RuntimeError(
            f"Redirection inattendue après le WAYF (arrivé sur {r.url}). "
            "Le flux d'auth a peut-être changé, ou un cookie/en-tête manque "
            "(relance avec CESI_DEBUG=1 pour voir la chaîne de redirection)."
        )
    action, data = parse_form(r.text, r.url)
    if action is None:
        raise RuntimeError("Formulaire ADFS introuvable - la page de login a changé.")
    data["UserName"] = USERNAME
    data["Password"] = PASSWORD
    data.setdefault("AuthMethod", "FormsAuthentication")
    r = session.post(action, data=data, headers={"Referer": r.url})
    debug_step("POST adfs", r, session)

    # Étape 3 : relais auto-submit (SAMLResponse/wresult) de retour vers ent.cesi.fr,
    # potentiellement plusieurs sauts.
    r = follow_auto_post_forms(session, r)
    debug_step("après relais retour SAML", r, session)

    # Vérification finale
    if "mon-emploi-du-temps" not in r.text and "accueil-apprenant" not in r.url:
        raise RuntimeError(
            "Login probablement en échec (identifiants invalides, MFA "
            "requise, ou structure de page changée). Réponse tronquée :\n"
            + r.text[:500]
        )


def fetch_schedule(session: requests.Session, start: str, end: str) -> list:
    if not CODE_PERSONNE:
        raise SystemExit("CESI_CODE_PERSONNE manquant (voir README pour le trouver).")
    r = session.get(
        f"{BASE}/api/seance/all",
        params={"start": start, "end": end, "codePersonne": CODE_PERSONNE},
    )
    r.raise_for_status()
    return r.json()


def default_week() -> tuple[str, str]:
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    sunday = monday + dt.timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


def main():
    if len(sys.argv) >= 3:
        start, end = sys.argv[1], sys.argv[2]
    else:
        start, end = default_week()

    session = requests.Session()
    session.headers.update(HEADERS)

    login(session)
    courses = fetch_schedule(session, start, end)

    print(json.dumps(courses, indent=2, ensure_ascii=False))
    return courses


if __name__ == "__main__":
    main()
