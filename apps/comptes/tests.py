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
