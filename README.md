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

## Déploiement Docker / Coolify

Déploie avec le `docker-compose.yaml` fourni (dans Coolify : type de build
« Docker Compose »). Renseigne les variables `API_TOKEN`, `CESI_USERNAME`,
`CESI_PASSWORD`, `CESI_CODE_PERSONNE` dans l'onglet Environment.

### « Temporary failure in name resolution » sur `ent.cesi.fr`

Symptôme, en appelant `/aujourdhui` ou `/semaine` depuis le conteneur :

```json
{ "error": "... Failed to resolve 'ent.cesi.fr' ([Errno -3] Temporary failure in name resolution)" }
```

Ce n'est **ni un bug du code ni du Dockerfile** : `[Errno -3]` (EAI_AGAIN)
signifie « le serveur DNS configuré est injoignable » (à distinguer d'un
`NXDOMAIN`, qui serait un nom introuvable). Sur un VPS Ubuntu + systemd-resolved
(cas classique de Coolify), le conteneur hérite d'un `/etc/resolv.conf` pointant
vers `127.0.0.53`, un résolveur qui n'écoute que sur l'hôte et reste injoignable
depuis le conteneur.

Le correctif est déjà en place dans `docker-compose.yaml` : on force des
résolveurs publics joignables.

```yaml
    dns:
      - 1.1.1.1
      - 8.8.8.8
```

Alternative si tu restes sur un déploiement « Dockerfile » sans compose : règle
le DNS au niveau du démon Docker de ton VPS, `/etc/docker/daemon.json` :

```json
{ "dns": ["1.1.1.1", "8.8.8.8"] }
```

puis `sudo systemctl restart docker`.

> Attention : ce correctif suppose que le conteneur tourne sur un réseau où les
> DNS publics sont joignables (cas normal d'un VPS). Si tu exécutes le conteneur
> **depuis le réseau interne CESI**, les DNS publics y sont bloqués et seuls les
> résolveurs internes (`10.96.23.x`) résolvent `ent.cesi.fr` — dans ce cas, mets
> ces adresses-là dans `dns:` à la place.

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
