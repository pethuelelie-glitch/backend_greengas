from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.comptes.models import Utilisateur, Role, StatutValidation, CodeOTP
from apps.referentiel.models import Site, Secteur, Bac


class ComptesEndpointsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Référentiel pour bac
        self.site = Site.objects.create(
            code="DIG-01",
            nom="Site Digesteur",
            statut="nominal",
            capacite_kg_jour=1000,
            latitude=Decimal('5.345000'),
            longitude=Decimal('-4.012000')
        )
        self.secteur = Secteur.objects.create(
            code="NORD",
            nom="Secteur Nord",
            site=self.site,
            site_repli=self.site
        )
        self.bac = Bac.objects.create(
            code="BAC-014",
            residence="Résidence Soleil",
            secteur=self.secteur,
            nb_foyers_declares=20,
            latitude=Decimal('5.345000'),
            longitude=Decimal('-4.012000'),
            tare_kg=Decimal('10.00'),
            capacite_kg=Decimal('100.00')
        )

        # Admin
        self.admin = Utilisateur.objects.create_user(
            telephone="+2250100000001",
            email="admin@greengas.ci",
            nom="Admin Principal",
            password="password123",
            role=Role.ADMINISTRATEUR,
            statut_validation=StatutValidation.VALIDE
        )

    def test_inscription_citoyen_directe_et_jetons(self):
        """
        OpenAPI 1.3.0 : Pas de SMS OTP ni de validation référent.
        Compte actif aussitôt (valide, telephone_verifie=True) et connecté (renvoie 201 avec Jetons).
        """
        payload = {
            "telephone": "+2250700000001",
            "nom": "Kouassi Jean",
            "mot_de_passe": "Password123!",
            "code_bac": "BAC-014"
        }
        res = self.client.post("/api/v1/auth/inscription/", payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', res.data)
        self.assertIn('refresh', res.data)
        self.assertIn('utilisateur', res.data)
        self.assertEqual(res.data['utilisateur']['statut_validation'], "valide")
        self.assertEqual(res.data['utilisateur']['profil_citoyen']['telephone_verifie'], True)
        self.assertEqual(res.data['utilisateur']['role'], "citoyen")

    def test_inscription_personnel_validation_et_connexion(self):
        """
        OpenAPI 1.3.0 : Personnel créé en statut_validation='en_attente', AUCUN jeton émis (201 Utilisateur).
        Connexion bloquée avec 403 COMPTE_NON_VALIDE tant qu'un admin n'a pas validé.
        Puis validation admin -> connexion autorisée.
        """
        payload = {
            "telephone": "+2250700000002",
            "email": "Yao.Tri@GreenGas.ci",  # test casse majuscule
            "nom": "Yao Tri",
            "mot_de_passe": "Password123!",
            "role": "operateur_tri"
        }
        res_inscr = self.client.post("/api/v1/auth/inscription/personnel/", payload, format='json')
        self.assertEqual(res_inscr.status_code, status.HTTP_201_CREATED)
        self.assertNotIn('access', res_inscr.data)
        self.assertEqual(res_inscr.data['statut_validation'], "en_attente")
        self.assertEqual(res_inscr.data['email'], "yao.tri@greengas.ci")
        personnel_id = res_inscr.data['id']

        # Tentative de connexion avant validation -> 403 COMPTE_NON_VALIDE
        res_login_bloque = self.client.post(
            "/api/v1/auth/token/",
            {"telephone": "+2250700000002", "mot_de_passe": "Password123!"},
            format='json'
        )
        self.assertEqual(res_login_bloque.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_login_bloque.data['code'], "COMPTE_NON_VALIDE")

        # Validation par l'administrateur
        self.client.force_authenticate(user=self.admin)
        res_val = self.client.post(
            f"/api/v1/utilisateurs/{personnel_id}/validation/",
            {"decision": "valider", "commentaire": "Pièce OK"},
            format='json'
        )
        self.assertEqual(res_val.status_code, status.HTTP_200_OK)
        self.assertEqual(res_val.data['statut_validation'], "valide")

        # Tentative de re-validation -> 409 CONFLIT
        res_val_conflit = self.client.post(
            f"/api/v1/utilisateurs/{personnel_id}/validation/",
            {"decision": "valider"},
            format='json'
        )
        self.assertEqual(res_val_conflit.status_code, status.HTTP_409_CONFLICT)

        # Connexion après validation avec email (insensible à la casse) -> 200 OK
        self.client.credentials()  # reset auth
        res_login_email = self.client.post(
            "/api/v1/auth/token/",
            {"email": "YAO.TRI@GREENGAS.CI", "mot_de_passe": "Password123!"},
            format='json'
        )
        self.assertEqual(res_login_email.status_code, status.HTTP_200_OK)
        self.assertIn('access', res_login_email.data)

    def test_connexion_regles_identifiant(self):
        """
        OpenAPI 1.3.0 : Exactement un des deux identifiants (téléphone ou email).
        400 si les deux ou aucun.
        401 si mot de passe erroné.
        """
        # Aucun identifiant -> 400
        res_none = self.client.post(
            "/api/v1/auth/token/",
            {"mot_de_passe": "password123"},
            format='json'
        )
        self.assertEqual(res_none.status_code, status.HTTP_400_BAD_REQUEST)

        # Les deux fournis -> 400
        res_both = self.client.post(
            "/api/v1/auth/token/",
            {"telephone": "+2250100000001", "email": "admin@greengas.ci", "mot_de_passe": "password123"},
            format='json'
        )
        self.assertEqual(res_both.status_code, status.HTTP_400_BAD_REQUEST)

        # Mauvais mot de passe -> 401
        res_wrong = self.client.post(
            "/api/v1/auth/token/",
            {"telephone": "+2250100000001", "mot_de_passe": "wrongpass"},
            format='json'
        )
        self.assertEqual(res_wrong.status_code, status.HTTP_401_UNAUTHORIZED)

        # Connexion admin par téléphone -> 200
        res_ok = self.client.post(
            "/api/v1/auth/token/",
            {"telephone": "+2250100000001", "mot_de_passe": "password123"},
            format='json'
        )
        self.assertEqual(res_ok.status_code, status.HTTP_200_OK)
        self.assertIn('access', res_ok.data)

    def test_documentation_swagger_et_redoc(self):
        # Vérification OpenAPI 1.3.0
        res_schema = self.client.get("/api/schema/")
        self.assertEqual(res_schema.status_code, status.HTTP_200_OK)
        self.assertEqual(res_schema.json()['info']['version'], "1.3.0")

        res_docs = self.client.get("/api/docs/")
        self.assertEqual(res_docs.status_code, status.HTTP_200_OK)
        self.assertIn("swagger-ui", str(res_docs.content))

        res_redoc = self.client.get("/api/redoc/")
        self.assertEqual(res_redoc.status_code, status.HTTP_200_OK)
        self.assertIn("redoc", str(res_redoc.content))

    def test_verification_1_citoyen_inscription_et_scan(self):
        """
        1. Inscription d'un citoyen avec code_bac = BAC-014 -> jetons reçus, puis POST /scans/ accepté.
        """
        payload = {
            "telephone": "+2250711223344",
            "nom": "Citoyen Test",
            "mot_de_passe": "greengas2026",
            "code_bac": "BAC-014"
        }
        res_inscr = self.client.post("/api/v1/auth/inscription/", payload, format='json')
        self.assertEqual(res_inscr.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', res_inscr.data)
        access_token = res_inscr.data['access']

        # Scan immédiat sans attente de SMS ni de validation
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        res_scan = self.client.post(
            "/api/v1/scans/",
            {
                "code_bac": "BAC-014",
                "latitude": 5.345000,
                "longitude": -4.012000
            },
            format='json'
        )
        self.assertEqual(res_scan.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_scan.data['statut'], 'valide')
        self.assertTrue(res_scan.data['compte'])

    def test_verification_2_operateur_inscription_sans_jetons_et_connexion_bloquee(self):
        """
        2. Inscription d'un opérateur -> 201 sans jetons ; sa connexion -> 403 COMPTE_NON_VALIDE.
        """
        payload = {
            "telephone": "+2250788990011",
            "email": "operateur.test@greengas.ci",
            "nom": "Nouvel Opérateur",
            "mot_de_passe": "greengas2026",
            "role": "operateur_tri"
        }
        res_inscr = self.client.post("/api/v1/auth/inscription/personnel/", payload, format='json')
        self.assertEqual(res_inscr.status_code, status.HTTP_201_CREATED)
        self.assertNotIn('access', res_inscr.data)
        self.assertEqual(res_inscr.data['statut_validation'], 'en_attente')

        # Tentative de connexion -> 403 COMPTE_NON_VALIDE
        res_conn = self.client.post(
            "/api/v1/auth/token/",
            {"telephone": "+2250788990011", "mot_de_passe": "greengas2026"},
            format='json'
        )
        self.assertEqual(res_conn.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_conn.data['code'], "COMPTE_NON_VALIDE")
        self.assertEqual(res_conn.data['details'].get('statut_validation'), "en_attente")

    def test_verification_3_ibrahim_connexion_validation_reconnexion(self):
        """
        3. Connexion d'Ibrahim -> 403 ; validation par l'admin ; nouvelle connexion -> 200.
        """
        ibrahim = Utilisateur.objects.create_user(
            telephone="+2250700000008",
            email="ibrahim.kone@greengas.ci",
            nom="Ibrahim Koné",
            password="greengas2026",
            role=Role.OPERATEUR_TRI,
            statut_validation=StatutValidation.EN_ATTENTE
        )

        # 1. Connexion d'Ibrahim -> 403
        res_login_1 = self.client.post(
            "/api/v1/auth/token/",
            {"email": "ibrahim.kone@greengas.ci", "mot_de_passe": "greengas2026"},
            format='json'
        )
        self.assertEqual(res_login_1.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_login_1.data['code'], "COMPTE_NON_VALIDE")

        # 2. Validation par l'administrateur
        self.client.force_authenticate(user=self.admin)
        res_val = self.client.post(
            f"/api/v1/utilisateurs/{ibrahim.id}/validation/",
            {"decision": "valider", "commentaire": "Approuvé pour l'équipe de tri"},
            format='json'
        )
        self.assertEqual(res_val.status_code, status.HTTP_200_OK)
        self.assertEqual(res_val.data['statut_validation'], "valide")

        # 3. Nouvelle connexion -> 200 OK
        self.client.credentials()
        res_login_2 = self.client.post(
            "/api/v1/auth/token/",
            {"telephone": "+2250700000008", "mot_de_passe": "greengas2026"},
            format='json'
        )
        self.assertEqual(res_login_2.status_code, status.HTTP_200_OK)
        self.assertIn('access', res_login_2.data)

    def test_verification_4_validation_referent_refusee_et_validation_citoyen_conflit(self):
        """
        4. Validation demandée par le référent -> 403 ; validation d'un citoyen -> 409.
        """
        referent = Utilisateur.objects.create_user(
            telephone="+2250700000005",
            email="referent@greengas.ci",
            nom="Référent Soleil",
            password="greengas2026",
            role=Role.REFERENT,
            bac=self.bac,
            statut_validation=StatutValidation.VALIDE
        )
        citoyen = Utilisateur.objects.create_user(
            telephone="+2250701020304",
            nom="Awa Citoyenne",
            password="greengas2026",
            role=Role.CITOYEN,
            bac=self.bac,
            statut_validation=StatutValidation.VALIDE
        )
        operateur = Utilisateur.objects.create_user(
            telephone="+2250799999999",
            email="op@greengas.ci",
            nom="Opérateur En Attente",
            password="greengas2026",
            role=Role.OPERATEUR_TRI,
            statut_validation=StatutValidation.EN_ATTENTE
        )

        # A. Validation demandée par le référent -> 403 ACCES_REFUSE
        self.client.force_authenticate(user=referent)
        res_ref = self.client.post(
            f"/api/v1/utilisateurs/{operateur.id}/validation/",
            {"decision": "valider"},
            format='json'
        )
        self.assertEqual(res_ref.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_ref.data['code'], "ACCES_REFUSE")

        # B. Validation d'un citoyen par l'administrateur -> 409 CONFLIT
        self.client.force_authenticate(user=self.admin)
        res_cit = self.client.post(
            f"/api/v1/utilisateurs/{citoyen.id}/validation/",
            {"decision": "valider"},
            format='json'
        )
        self.assertEqual(res_cit.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res_cit.data['code'], "CONFLIT")
        self.assertEqual(res_cit.data['message'], "Ce compte n'attend pas de validation.")

    def test_verification_code_bac_inconnu_renvoie_404(self):
        """
        OpenAPI 1.3.0 : 404 INTROUVABLE si code de bac inconnu à l'inscription citoyen.
        """
        payload = {
            "telephone": "+2250755667788",
            "nom": "Citoyen Bac Inconnu",
            "mot_de_passe": "greengas2026",
            "code_bac": "BAC-INCONNU"
        }
        res = self.client.post("/api/v1/auth/inscription/", payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res.data['code'], "INTROUVABLE")

    def test_verification_rafraichir_bloque_compte_en_attente_ou_inactif(self):
        """
        OpenAPI 1.3.0 : Le rafraîchissement d'un jeton (/auth/token/rafraichir/)
        doit être refusé (403 COMPTE_NON_VALIDE) pour les comptes en attente, refusés ou désactivés.
        """
        from rest_framework_simplejwt.tokens import RefreshToken

        user_inactif = Utilisateur.objects.create_user(
            telephone="+2250766778899",
            nom="User Inactif",
            password="greengas2026",
            role=Role.CITOYEN,
            actif=False,
            statut_validation=StatutValidation.VALIDE
        )
        refresh = RefreshToken.for_user(user_inactif)

        res = self.client.post(
            "/api/v1/auth/token/rafraichir/",
            {"refresh": str(refresh)},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data['code'], "COMPTE_NON_VALIDE")
        self.assertEqual(res.data['details'].get('actif'), False)
