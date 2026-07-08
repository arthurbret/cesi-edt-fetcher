# Récupération automatique de l'emploi du temps ENT CESI

Script Python qui se connecte tout seul au SSO CESI (ADFS) et récupère ton
emploi du temps via l'API JSON interne de l'ENT.

## Installation sur ton VPS

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env          # renseigne CESI_USERNAME et CESI_PASSWORD
chmod 600 .env      # limite la lecture au propriétaire
```

## Test manuel

```bash
python cesi_edt_sync.py                        # semaine en cours (lundi-dimanche)
python cesi_edt_sync.py 2026-07-13 2026-07-19  # semaine choisie
```

Si tout se passe bien, tu obtiens un JSON avec tes cours (titre, horaires,
salle, intervenant). Si ça plante, le script explique où ça a coincé
(WAYF, ADFS, ou vérification finale).

## Automatiser (cron)

Exemple : récupérer la semaine en cours chaque matin à 6h et l'écrire dans un
fichier :

```cron
0 6 * * * /chemin/vers/venv/bin/python /chemin/vers/cesi_edt_sync.py >> /chemin/vers/edt.json 2>&1
```

## Limites connues (à ne pas découvrir en prod)

- **Pas de gestion MFA.** Le script fait un login "UserName + Password"
  classique. Si ton compte a une double authentification ou une politique
  d'accès conditionnel ADFS, ça bloquera à l'étape 2 et il faudra une autre
  approche (ex: garder un cookie de session obtenu manuellement plutôt que de
  se reconnecter à chaque fois).
- **Fragile par nature.** Les noms de champs (`login`, `UserName`, `Password`,
  `AuthMethod`) ont été relevés en inspectant le vrai formulaire le 08/07/2026.
  Si CESI change son ENT ou bascule d'IdP, le script cassera et il faudra
  ré-inspecter les formulaires (F12 > Réseau dans un navigateur).
- **Mot de passe en clair dans `.env`.** Correct pour un usage perso sur un
  VPS que tu contrôles, mais protège bien l'accès à la machine (chmod 600,
  pas de backup non chiffré, etc.).
- **Vérifie la charte informatique CESI** avant de mettre ça en cron
  permanent — un accès automatisé répété peut ne pas être couvert par les
  conditions d'usage de l'ENT.

## codePersonne

Le paramètre `codePersonne` (dans `.env`) est un identifiant interne stable
lié à ton compte (`2426023` pour Arthur BRET). Pas besoin d'y retoucher.
