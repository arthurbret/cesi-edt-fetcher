#!/usr/bin/env python3
"""
Affiche uniquement les cours d'aujourd'hui, en clair (pas du JSON brut).

Réutilise le login et l'appel API de cesi_edt_sync.py (même dossier requis).

Usage :
  python cesi_cours_du_jour.py

Exemple de cron (tous les matins à 7h, mail/log du jour) :
  0 7 * * * /chemin/venv/bin/python /chemin/cesi_cours_du_jour.py
"""

import datetime as dt

import requests

from cesi_edt_sync import HEADERS, fetch_schedule, login


def format_heure(iso_dt: str) -> str:
    # ex: "2026-07-09T08:30:00+02" -> "08:30"
    return iso_dt[11:16]


def main():
    today = dt.date.today().isoformat()

    session = requests.Session()
    session.headers.update(HEADERS)

    login(session)
    cours = fetch_schedule(session, today, today)

    cours = sorted(cours, key=lambda c: c["start"])

    date_str = dt.date.today().strftime("%A %d %B %Y")
    print(f"Cours du {date_str} :\n")

    if not cours:
        print("Aucun cours aujourd'hui.")
        return

    for c in cours:
        debut = format_heure(c["start"])
        fin = format_heure(c["end"])
        salles = ", ".join(s.get("nomSalle", "") for s in c.get("salles", []))
        intervenants = ", ".join(
            f"{i.get('prenom', '')} {i.get('nom', '')}".strip()
            for i in c.get("intervenants", [])
        )
        ligne = f"{debut} - {fin}  {c['title']}"
        if salles:
            ligne += f"  [{salles}]"
        if intervenants:
            ligne += f"  ({intervenants})"
        print(ligne)


if __name__ == "__main__":
    main()
