# GREENGAS — État d'avancement et Feuille de route technique

**SIREXE Hackathon 2026 · Équipe DEDSEC · Version du 13 octobre 2026**

Ce document récapitule l'ensemble du travail accompli sur le backend Django REST, ainsi que le plan de développement exhaustif des prochaines étapes nécessaires pour mener le projet à son intégration complète avec l'application mobile Flutter et le Control Center (React / Electron).

---

## 1. Rappel des principes fondateurs

> **Règle absolue d'architecture :** Seul le backend calcule.
> Ni l'application mobile Flutter (citoyen et collecteur) ni le Control Center (opérateur de tri, responsable méthanisation, administrateur) ne calculent des points, du biogaz, des kWh ou des écarts. Ils envoient des actions et affichent les résultats calculés par l'API.

---

## 2. Ce qui a été réalisé jusqu'à présent

### 2.1 Analyse du contrat technique et métier
- Analyse approfondie du document `GREENGAS_Guide_Commun.md`.
- Analyse de la spécification OpenAPI 3.0.3 `openapi.yaml` définissant les 38+ endpoints, les schémas de données, la sécurité Bearer JWT et le format d'erreur standardisé.

### 2.2 Préparation de l'environnement technique
- Création de l'environnement virtuel Python `.venv` isolé.
- Installation des dépendances clés : `Django` (5.2), `djangorestframework`, `djangorestframework-simplejwt`, `django-cors-headers`, `python-dotenv`, `PyMySQL`, `cryptography`.

### 2.3 Architecture modulaire du projet
- Initialisation du projet Django nommé `backend_greengas`.
- Création du répertoire modulaire `apps/` contenant les 8 applications du guide commun :
  1. `apps.comptes`
  2. `apps.referentiel`
  3. `apps.collecte`
  4. `apps.tri`
  5. `apps.greenpoints`
  6. `apps.energie`
  7. `apps.supervision`
  8. `apps.simulateur`
- **Application stricte de ton organisation personnalisée** :
  Remplacement de tous les fichiers simples par des dossiers modulaires équipés de leur `__init__.py` :
  - `models/` (avec `__init__.py`)
  - `views/` (avec `__init__.py`)
  - `admin/` (avec `__init__.py`)
  - `migrations/` (avec `__init__.py`)
  - `urls.py`
  - `apps.py` (configuré avec `name = 'apps.<nom>'` pour une isolation propre dans Django).

### 2.4 Configuration centrale de Django
Mise à jour de `backend_greengas/backend_greengas/settings.py` :
- **`INSTALLED_APPS`** : Intégration de `rest_framework`, `corsheaders` et des 8 applications `apps.*`.
- **`MIDDLEWARE`** : Positionnement de `corsheaders.middleware.CorsMiddleware` tout en haut pour débloquer les appels du Control Center.
- **`AUTH_USER_MODEL`** : Déclaré sur `'comptes.Utilisateur'` avant la moindre migration.
- **`REST_FRAMEWORK`** : Activation de `COERCE_DECIMAL_TO_STRING = False` (exigé pour renvoyer des nombres JSON `34.0` et non des chaînes `"34.00"`), authentification SimpleJWT par défaut, pagination à 50 éléments par page.
- **`SIMPLE_JWT`** : Tokens d'accès de 60 minutes, refresh tokens de 7 jours, identifiant en UUID (`user_id`).
- **`CORS`** : Origines autorisées pour `http://localhost:5173` (Vite) et `http://localhost:3000`.
- **Fuseau horaire** : `TIME_ZONE = 'UTC'`, `USE_TZ = True`, `LANGUAGE_CODE = 'fr-fr'`.

### 2.5 Modèles déjà créés et validés

| Modèle | Emplacement | Caractéristiques principales |
|---|---|---|
| **`Utilisateur`** | `apps/comptes/models/utilisateur.py` | Clé primaire en UUID, identifiant de connexion par `telephone` (`+225...`), gestion des 7 rôles (`citoyen`, `collecteur`, `operateur_tri`, `responsable_methanisation`, `referent`, `administrateur`, `capteur`), statut de validation (`en_attente`, `valide`, `refuse`), lien ForeignKey vers `Bac`, manager personnalisé `UtilisateurManager`. |
| **`Site`** | `apps/referentiel/models/site.py` | Digesteurs méthaniseurs (`DIG-01` à `DIG-03`), statuts (`nominal`, `alerte`, `maintenance`), capacité journalière en kg, coordonnées GPS (latitude/longitude). |
| **`Secteur`** | `apps/referentiel/models/secteur.py` | Secteurs géographiques (`NORD`, `EST`, `OUEST`), liens vers le site normal et le site de repli. |
| **`Bac`** | `apps/referentiel/models/bac.py` | Bacs de quartier (`BAC-014`...), résidence, secteur rattaché, nombre de foyers déclarés, tare à vide ($kg$), capacité ($kg$), statut actif/inactif, coordonnées GPS. |

> **Validation :** La commande `python manage.py check` s'est exécutée avec succès : **`System check identified no issues (0 silenced)`**.

---

## 3. Ce qu'il reste à faire (Feuille de route chronologique)

### Étape 1 : Finalisation du Socle & Authentification *(Semaine 1 : 13 → 19 octobre)*

**Objectif :** Permettre à l'application mobile et au Control Center de se connecter avec les comptes de démo.

- [ ] **Gestionnaire d'erreurs normalisé DRF** :
  - Créer un exception handler personnalisé dans `apps/comptes/exceptions.py` renvoyant le format exigé par le contrat :
    `{ "code": "CODE_ERREUR", "message": "Message explicatif", "details": {} }`
- [ ] **Modèles restants à coder** :
  - [ ] `apps/collecte/models/` : `Scan`, `Tournee`, `Collecte`.
  - [ ] `apps/tri/models/` : `LotTrie`.
  - [ ] `apps/greenpoints/models/` : `GreenPointsTransaction`, `Recompense`, `Echange`.
  - [ ] `apps/energie/models/` : `ProductionEnergie`, `Alerte`.
  - [ ] `apps/supervision/models/` : `Parametre`, `JournalAudit`.
- [ ] **Exécution des premières migrations** :
  - `python manage.py makemigrations`
  - `python manage.py migrate`
- [ ] **Commande de Seed (`python manage.py seed_data`)** :
  - Charger l'intégralité du jeu de test officiel (§12 du guide) :
    - Mot de passe universel : `greengas2026`.
    - Comptes : Admin, Collecteur, Opératrice, Resp. Méthanisation, Référent, Simulateur IoT, Citoyens (Awa, Koffi...).
    - Les 3 sites (`DIG-01`, `DIG-02`, `DIG-03`) et secteurs (`NORD`, `EST`, `OUEST`).
    - Les bacs officiels (`BAC-014` à `BAC-031`).
    - Les paramètres système initiaux (coefficients de filières, seuils, rendements).
    - Le catalogue initial de récompenses (Internet 1 Go, crédit d'appel, bon d'achat, kit de tri).
- [ ] **Endpoints d'authentification** :
  - [ ] `POST /api/v1/auth/token/` (login téléphone + mot de passe, renvoie tokens + profil avec rôle).
  - [ ] `POST /api/v1/auth/token/rafraichir/`.
  - [ ] `GET /api/v1/auth/moi/` (renvoie l'utilisateur connecté).
  - [ ] `POST /api/v1/auth/inscription/` (inscription citoyen avec code OTP simulé).
  - [ ] `POST /api/v1/auth/otp/verifier/` & `/auth/otp/renvoyer/`.

---

### Étape 2 : Référentiel, Scans Citoyens & Tournées de Collecte *(Semaine 2 : 20 → 26 octobre)*

**Objectif :** Valider l'intégralité du parcours terrain sur Flutter.

- [ ] **API Référentiel** :
  - `GET /api/v1/secteurs/`, `GET /api/v1/sites/`, `GET /api/v1/bacs/`, `GET /api/v1/bacs/{id}/`.
- [ ] **Moteur de Scans Citoyens (`POST /api/v1/scans/`)** :
  - Règle anti-triche : compte validé et téléphone vérifié obligatoires (`COMPTE_NON_VALIDE`).
  - Règle de debouncing : même bac + même citoyen $< 10\text{ s} \rightarrow$ doublon ignoré.
  - Plafond quotidien : maximum 2 scans valides par jour (`refuse_plafond`).
  - Géolocalisation : calcul de la distance au bac (si $> 100\text{ m} \rightarrow$ `hors_zone`).
- [ ] **Gestion des Tournées & Collectes** :
  - `GET /api/v1/tournees/?date=...` (tournées assignées au collecteur).
  - `POST /api/v1/tournees/{id}/demarrer/` (`planifiee` $\rightarrow$ `en_cours`).
  - `POST /api/v1/tournees/{id}/collectes/` (ouverture bac avec `code_bac`).
  - `POST /api/v1/collectes/{id}/pesee/` (réception de la pesée simulateur/capteur).
  - Calcul automatique : $\text{poids\_net} = \text{poids\_brut} - \text{tare}$.
  - Règle de contrôle : si $\text{kg}/\text{scan} < 0,3 \rightarrow$ `a_verifier`.
  - `POST /api/v1/collectes/{id}/valider/`.
  - `POST /api/v1/tournees/{id}/cloturer/` (`en_cours` $\rightarrow$ `collectee`).

---

### Étape 3 : Pipeline de Tri, GreenPoints & Bilan Énergétique *(Semaine 3 : 27 octobre → 2 novembre)*

**Objectif :** Implémenter le cœur algorithmique du système et connecter l'opérateur de tri et le responsable méthanisation.

- [ ] **Pipeline de Tri Atomique (`POST /api/v1/tournees/{id}/tri/`)** :
  - Exécution sous `transaction.atomic()` :
    1. Vérification de la tolérance de pesée ($|\text{écart}| \le 2\%$).
    2. Création des lots par filière (`ORG`, `BIO`, `PLA`, `MET`, `CAR`, `VER`, `REF`).
    3. Calcul de la valeur au kilo de la tournée : $\text{valeur\_kg} = \sum \text{part}(f) \times \text{coef}(f)$.
    4. Calcul des points par bac selon qualité : $\text{points\_bac} = \text{poids\_net} \times \text{valeur\_kg} \times \text{coef\_qualite}$.
    5. Répartition proportionnelle aux citoyens : $\text{points\_citoyen} = \lfloor \text{points\_bac} \times \frac{\text{scans\_citoyen}}{\text{scans\_bac}} \rfloor$.
    6. Transfert de la masse organique vers la production du jour du digesteur.
- [ ] **Espace GreenPoints Citoyen** :
  - `GET /api/v1/greenpoints/solde/`, `GET /api/v1/greenpoints/transactions/`, `GET /api/v1/recompenses/`, `POST /api/v1/echanges/`.
- [ ] **Bilan Énergétique Quotidien (`/api/v1/productions/`)** :
  - Calcul du biogaz théorique attendu ($0,1\text{ m}^3/\text{kg}$).
  - Réception des mesures réelles ou simulées (`biogaz_mesure`, $\% \text{CH}_4$, $T^\circ\text{C}$, $\text{pH}$).
  - Calculs énergétiques : électricité ($kWh$), chaleur ($kWh$), digestat ($kg$), foyers équivalents.
  - Déclencheur automatique d'alertes : si $|\text{écart}| \ge 20\%$ ou si $\% \text{CH}_4 < 50\%$.
  - Clôture journalière avec destination du digestat.

---

### Étape 4 : Supervision, Traçabilité & Démonstration Hackathon *(Semaine 4 : 3 → 9 novembre)*

**Objectif :** Fournir les écrans d'administration et préparer le pitch devant le jury du SIREXE.

- [ ] **File de vérification anti-fraude (`GET /api/v1/verifications/`)** :
  - Bacs surinscrits, collectes avec trop peu de kg/scan, scans hors zone.
  - Décision admin : valider ou annuler les points d'une collecte suspecte.
- [ ] **Traçabilité de bout en bout (`GET /api/v1/bacs/{id}/tracabilite/`)** :
  - Reconstitution complète : Scans $\rightarrow$ Collecte $\rightarrow$ Lots $\rightarrow$ Points $\rightarrow$ Biogaz $\rightarrow$ Électricité.
- [ ] **Paramètres Système dynamiques (`/api/v1/parametres/`)** :
  - Consultation et modification en direct des coefficients sans redémarrage.
- [ ] **Journal d'Audit immuable (`GET /api/v1/journal/`)** :
  - Traçabilité de chaque action sensible (qui, quand, avant, après, motif).
- [ ] **Scénario Démo IoT (`/api/v1/simulation/scenarios/`)** :
  - Forcer un facteur de production à $0,70$ pour déclencher une alerte à $-30\%$ en direct devant le jury.
