#!/usr/bin/env python3
"""
Petit wrapper HTTP autour de cesi_edt_sync.py / cesi_cours_du_jour.py, pour
pouvoir déclencher la récupération de l'emploi du temps "à la demande" via
une simple requête HTTP (navigateur, curl, raccourci iOS/Android, bot
Telegram...), une fois déployé sur ton VPS (Coolify ou autre).

Endpoints :
  GET /aujourdhui   -> JSON des cours du jour (+ champ "texte" lisible)
  GET /semaine       -> JSON brut de la semaine en cours (ou ?start=&end=)
  GET /healthz       -> ping simple, sans auth (pour Coolify health check)

Sécurité :
  Toutes les routes (sauf /healthz) exigent un header :
    Authorization: Bearer <API_TOKEN>
  où API_TOKEN est une variable d'environnement que tu choisis (chaîne
  aléatoire, ex: générée avec `openssl rand -hex 32`). Sans quoi n'importe
  qui connaissant l'URL publique pourrait déclencher le script.

Variables d'environnement nécessaires : CESI_USERNAME, CESI_PASSWORD,
CESI_CODE_PERSONNE (déjà utilisées par les scripts), + API_TOKEN.
"""

import os
import functools
import datetime as dt

from flask import Flask, request, jsonify

from cesi_edt_sync import HEADERS, default_week, fetch_schedule, login
import requests

API_TOKEN = os.environ.get("API_TOKEN")

app = Flask(__name__)


def require_token(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not API_TOKEN:
            return jsonify({"error": "API_TOKEN non configuré côté serveur"}), 500
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {API_TOKEN}":
            return jsonify({"error": "Non autorisé"}), 401
        return view(*args, **kwargs)

    return wrapped


def get_authenticated_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    login(session)
    return session


def format_heure(iso_dt: str) -> str:
    return iso_dt[11:16]


# Noms français en dur : l'image Docker (debian slim) n'a pas la locale
# fr_FR, donc strftime("%A %B") sortirait "Friday July".
JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def format_date_fr(d: dt.date) -> str:
    return f"{JOURS_FR[d.weekday()]} {d.day} {MOIS_FR[d.month - 1]} {d.year}"


@app.route("/healthz")
def healthz():
    return "ok", 200


@app.route("/semaine")
@require_token
def semaine():
    start = request.args.get("start")
    end = request.args.get("end")
    if not start or not end:
        start, end = default_week()
    try:
        session = get_authenticated_session()
        cours = fetch_schedule(session, start, end)
    except Exception as e:  # noqa: BLE001 - on veut renvoyer l'erreur au client
        return jsonify({"error": str(e)}), 502
    return jsonify(cours)


@app.route("/aujourdhui")
@require_token
def aujourdhui():
    today = dt.date.today().isoformat()
    try:
        session = get_authenticated_session()
        cours = fetch_schedule(session, today, today)
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 502

    cours = sorted(cours, key=lambda c: c["start"])
    date_str = format_date_fr(dt.date.today())

    lignes = [f"Cours du {date_str} :", ""]
    cours_json = []
    if not cours:
        lignes.append("Aucun cours aujourd'hui.")
    else:
        for c in cours:
            debut = format_heure(c["start"])
            fin = format_heure(c["end"])
            salles = [
                s["nomSalle"] for s in c.get("salles", []) if s.get("nomSalle")
            ]
            ligne = f"{debut} - {fin}  {c['title']}"
            if salles:
                ligne += f"  [{', '.join(salles)}]"
            lignes.append(ligne)
            cours_json.append(
                {
                    "debut": debut,
                    "fin": fin,
                    "titre": c["title"],
                    "salles": salles,
                    "start": c["start"],
                    "end": c["end"],
                }
            )

    return jsonify(
        {
            "date": today,
            "jour": date_str,
            "cours": cours_json,
            # version texte lisible (l'ancien format de cet endpoint)
            "texte": "\n".join(lignes),
        }
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
