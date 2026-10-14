# 🌿 GREENGAS — Backend API

> **SIREXE Hackathon 2026 · Équipe DEDSEC · Abidjan, Côte d'Ivoire**  
> Plateforme intégrée d'économie circulaire et de valorisation des déchets organiques en biogaz, électricité et digestat agricole.

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.2-green.svg)](https://www.djangoproject.com/)
[![Django REST Framework](https://img.shields.io/badge/DRF-3.15-red.svg)](https://www.django-rest-framework.org/)
[![JWT](https://img.shields.io/badge/Auth-SimpleJWT-orange.svg)](https://django-rest-framework-simplejwt.readthedocs.io/)
[![API Spec](https://img.shields.io/badge/OpenAPI-3.0.3-brightgreen.svg)](../openapi.yaml)

---

## 📌 Présentation du Projet

**GREENGAS** est une solution numérique conçue pour encourager le tri sélectif des déchets ménagers et assurer la traçabilité complète de la valorisation organique :

1. **Les citoyens** trient leurs déchets et scannent le bac de quartier pour accumuler des **GreenPoints**.
2. **Les collecteurs** réalisent leurs tournées et pèsent les bacs via une pesée embarquée.
3. **Le centre de tri** répartit les flux de matières (organique, plastique, verre, carton, métal, etc.) et déclenche la distribution des récompenses.
4. **Les unités de méthanisation (digesteurs)** transforment la matière organique en **biogaz**, **électricité**, **chaleur** et **digestat agricole**, avec un suivi en temps réel de la performance énergétique et des alertes d'écart.

### ⚡ Règle d'or de l'architecture
> **Seul le backend calcule.**  
> Ni l'application mobile Flutter ni le Control Center (React/Electron) ne calculent des points, des volumes de gaz, des équivalents kWh ou des écarts. Le backend est la source unique de vérité et applique toutes les règles métier.

---

## 🏗️ Architecture Globale

```
   ┌───────────────────────────┐         ┌─────────────────────────────┐
   │    Application Flutter    │         │       Control Center        │
   │  • Citoyen (scan, points) │         │   (React web + Electron)    │
   │  • Collecteur (tournée)   │         │  • Opérateur de tri         │
   └─────────────┬─────────────┘         │  • Resp. méthanisation      │
                 │                       │  • Administrateur           │
                 │   HTTP + JSON + JWT   └──────────────┬──────────────┘
                 │                                      │
                 └───────────────────┬──────────────────┘
                                     ▼
                    ┌─────────────────────────────────┐
                    │     Backend Django REST API     │
                    │        Préfixe : /api/v1/       │
                    │   • Règles métier & calculs     │
                    │   • Contrôle d'accès par rôle   │
                    │   • Simulateur IoT (pesée, gaz) │
                    │   • Journal d'audit & antifraude│
                    └────────────────┬────────────────┘
                                     ▼
                              ┌─────────────┐
                              │ Base MySQL  │
                              │  / SQLite   │
                              └─────────────┘
```

---

## 📦 Organisation des Applications Django

Le backend est structuré en **8 applications modulaires**, chacune organisée en **sous-dossiers** (`models/`, `views/`, `admin/`) :

```text
backend_greengas/
├── manage.py
├── backend_greengas/           # Configuration principale (settings, urls, wsgi)
└── apps/
    ├── comptes/                # Utilisateur (UUID, téléphone), Rôles, OTP
    │   ├── admin/
    │   ├── models/             # utilisateur.py, otp.py
    │   ├── views/
    │   ├── migrations/
    │   └── urls.py
    ├── referentiel/            # Secteurs, Sites digesteurs (DIG-01..03), Bacs
    ├── collecte/               # Scans géolocalisés, Tournées, Collectes, Pesées
    ├── tri/                    # Lots triés (ORG, PLA, MET...), Pipeline atomique
    ├── greenpoints/            # Transactions, Récompenses, Échanges de points
    ├── energie/                # Production quotidienne (biogaz, kWh, digestat), Alertes
    ├── supervision/            # Paramètres système éditables, Journal d'audit, File antifraude
    └── simulateur/             # Simulateur de capteurs IoT (pesée de camion, débitmètre gaz)
```

---

## 🚀 Installation et Démarrage Rapide

### Prérequis
- Python 3.10 ou supérieur
- Git
- MySQL (optionnel, SQLite activé par défaut pour le développement rapide)

### 1. Cloner et accéder au projet
```bash
cd backend_greengas
```

### 2. Activer l'environnement virtuel
Sur Windows (PowerShell) :
```powershell
..\.venv\Scripts\Activate.ps1
```

### 3. Installer les dépendances
```bash
pip install -r ..\requirements.txt
```

### 4. Appliquer les migrations
```bash
python manage.py migrate
```

### 5. Créer un administrateur (si non existant)
```bash
python manage.py createsuperuser
```

### Configuration de production

En production, définir une clé aléatoire longue (`SECRET_KEY`), `DEBUG=False`,
`ALLOWED_HOSTS` avec le nom d'hôte de l'API et `CORS_ALLOWED_ORIGINS` avec les origines
HTTPS du Control Center. Configurer `CSRF_TRUSTED_ORIGINS` pour les interfaces qui utilisent
les cookies de session. HTTPS (redirection) et les cookies sécurisés sont activés par défaut.
Choisir explicitement `DB_ENGINE=mysql` ou `DB_ENGINE=postgresql` et fournir `DB_NAME`,
`DB_USER`, `DB_PASSWORD` et `DB_HOST`. Le démarrage refuse les identifiants absents, un moteur
inconnu, SQLite en production et l'absence d'un cache partagé (`CACHE_URL`, Redis recommandé).
`psycopg`, `django-redis` et Gunicorn sont inclus dans `requirements.txt`.
WhiteNoise sert les fichiers statiques collectés. Avant le démarrage, exécuter
`python manage.py collectstatic --noinput`, appliquer les migrations, puis lancer
`gunicorn backend_greengas.wsgi:application --bind 0.0.0.0:8000 --workers 3` derrière le proxy TLS.
Les journaux sont écrits sur la sortie standard (`LOG_LEVEL=INFO` par défaut en production);
les erreurs serveur sont journalisées côté serveur et renvoient un message générique à l'API.

Le proxy ou l'hébergeur doit terminer TLS. Définir `TRUST_X_FORWARDED_PROTO=True` uniquement
si ce proxy supprime l'en-tête client et transmet lui-même `X-Forwarded-Proto: https`; sinon
la redirection HTTPS ne peut pas reconnaître la connexion TLS terminée en amont. HSTS est
configurable avec `SECURE_HSTS_SECONDS`; l'inclusion des sous-domaines et le préchargement
sont désactivés jusqu'à validation de tous les domaines concernés.

En production, les limites d'appels s'appliquent aux routes publiques et aux utilisateurs.
Régler `API_NUM_PROXIES` au nombre exact de proxies de confiance et s'assurer qu'ils remplacent
`X-Forwarded-For`; sans cela, les limites par adresse ne sont pas fiables.

Les jetons d'accès expirent après 15 minutes; les refresh expirent après 7 jours, sont renouvelés
à chaque usage et révoqués à la rotation ou via `POST /api/v1/auth/deconnexion/`. Appliquer les
migrations avant de démarrer (`python manage.py migrate`) et planifier quotidiennement
`python manage.py flushexpiredtokens` pour purger les refresh expirés.

Les routes d'OTP ont une limite de tentatives, mais aucun fournisseur SMS n'est intégré:
`POST /api/v1/auth/otp/renvoyer/` ne livre pas le code. Ne pas activer un parcours de vérification
par SMS en production avant d'avoir branché et configuré le fournisseur choisi.

Les demandes publiques de comptes personnel restent possibles lorsque la validation
administrateur est activée. Si elle est désactivée, seule une session administrateur peut créer
ces comptes. Les données de démonstration activent cette validation par défaut.

### 6. Lancer l'ensemble des tests automatisés (64 tests)
```bash
python manage.py test apps.comptes.tests apps.referentiel.tests apps.collecte.tests apps.tri.tests apps.greenpoints.tests apps.energie.tests apps.supervision.tests apps.simulateur.tests
```

GitHub Actions exécute aussi cette suite sur MySQL 8.4 avec Redis et vérifie les réglages
de déploiement ainsi que la collecte des fichiers statiques à chaque push ou pull request vers `main`.

### 7. Lancer le serveur de développement
```bash
python manage.py runserver
```
Le serveur API est accessible sur : `http://localhost:8000/api/v1/`  
Le dashboard d'administration Jazzmin est sur : `http://localhost:8000/greengas/`


---

##  Règles et Formules Métier

### 1. Scan Citoyen
- **Contrôle d'accès** : Compte validé obligatoire (`COMPTE_NON_VALIDE`).
- **Anti-rebond (Debounce)** : Scan sur le même bac par le même citoyen en moins de 10 secondes = doublon renvoyé.
- **Plafond** : 2 scans valides max par jour par citoyen (`refuse_plafond`).
- **Géolocalisation** : Distance $> 100\text{ m}$ du bac $\rightarrow$ statut `hors_zone` (ne rapporte pas de points).

### 2. Pesée & Contrôle Antifraude
- Poids net : $\text{poids\_net\_kg} = \text{poids\_brut\_kg} - \text{tare\_kg}$.
- Ratio par scan : $\text{kg\_par\_scan} = \frac{\text{poids\_net\_kg}}{\text{scans\_valides}}$.
- Si $\text{kg\_par\_scan} < 0,3\text{ kg} \rightarrow$ collecte marquée **`a_verifier`** (les points des citoyens sont mis en attente jusqu'à décision d'un administrateur).

### 3. Pipeline de Tri & GreenPoints (Transaction Atomique)
- Tolérance de balance : $|\text{poids\_trié} - \text{poids\_collecté}| \le 2\%$ (sinon motif obligatoire).
- Coefficients par filière : Organique (10), Métal (15), Plastique (8), Biomasse (6), Carton/Papier (5), Verre (3), Refus (0).
- Valeur au kilo de la tournée : $\text{valeur\_kg} = \sum (\text{part}_f \times \text{coef}_f)$.
- Points du bac : $\text{points\_bac} = \text{poids\_net\_bac} \times \text{valeur\_kg} \times \text{coef\_qualite}$.
- Répartition citoyen :
  $$\text{points\_citoyen} = \left\lfloor \text{points\_bac} \times \frac{\text{scans\_citoyen}}{\text{scans\_bac}} \right\rfloor$$

### 4. Énergie & Biométhanisation
- Biogaz attendu : $\text{biogaz\_attendu} = \text{poids\_organique\_recu\_kg} \times 0,1\text{ m}^3/\text{kg}$.
- Écart : $\text{ecart\_pct} = \frac{\text{biogaz\_mesuré} - \text{biogaz\_attendu}}{\text{biogaz\_attendu}} \times 100$.
- Énergie valorisée :
  - Électricité : $\text{biogaz\_mesuré} \times 1,7\text{ kWh}$.
  - Chaleur : $\text{biogaz\_mesuré} \times 3,4\text{ kWh}$.
  - Digestat : $\text{poids\_organique\_recu\_kg} \times 0,5\text{ kg}$.
  - Foyers équivalents : $\frac{\text{electricite\_kwh} \times 365}{1785}$.
- **Déclencheur d'alerte** : Si $|\text{écart}| \ge 20\%$ ou si $\% \text{CH}_4 < 50\%$.

---

##  Conventions de l'API REST

- **Préfixe global** : `/api/v1/`
- **Barre oblique finale** : Toujours obligatoire (ex: `/api/v1/bacs/`)
- **Identifiants** : `id` en UUID technique + `code` lisible (`BAC-014`, `TRN-0912-01`, `DIG-01`).
- **Nombres** : Toujours des nombres JSON (jamais de chaînes textuelles pour les décimaux).
- **Dates** : Format ISO 8601 UTC avec `Z` (`2026-09-12T08:30:00Z`).
- **Format d'erreur universel** :
  ```json
  {
    "code": "SOLDE_INSUFFISANT",
    "message": "Solde insuffisant pour cette récompense",
    "details": {
      "solde": 60,
      "cout_points": 100
    }
  }
  ```


---

## 📄 Licence & Équipe

Projet développé par l'équipe **DEDSEC** dans le cadre du **SIREXE Hackathon 2026**.  
Tous droits réservés.
