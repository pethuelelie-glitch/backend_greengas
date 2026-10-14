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
            nom="Admin Principal",
            password="password123",
            role=Role.ADMINISTRATEUR
        )

    def test_inscription_citoyen_et_verification_otp(self):
        # 1. Inscription citoyen
        payload = {
            "telephone": "+2250700000001",
            "nom": "Kouassi Jean",
            "mot_de_passe": "Password123!",
            "code_bac": "BAC-014"
        }
        res_inscr = self.client.post("/api/v1/auth/inscription/", payload, format='json')
        self.assertEqual(res_inscr.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_inscr.data['profil_citoyen']['statut_validation'], "en_attente")
        self.assertEqual(res_inscr.data['role'], "citoyen")


        # Vérifier code OTP généré
        otp_obj = CodeOTP.objects.filter(telephone="+2250700000001").first()
        self.assertIsNotNone(otp_obj)

        # 2. Vérification OTP erroné -> 422
        res_otp_err = self.client.post(
            "/api/v1/auth/otp/verifier/",
            {"telephone": "+2250700000001", "code": "000000"},
            format='json'
        )
        self.assertEqual(res_otp_err.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)


        self.assertEqual(res_otp_err.data['code'], "OTP_INVALIDE")

        # 3. Vérification OTP valide -> 200
        res_otp_ok = self.client.post(
            "/api/v1/auth/otp/verifier/",
            {"telephone": "+2250700000001", "code": otp_obj.code},
            format='json'
        )
        self.assertEqual(res_otp_ok.status_code, status.HTTP_200_OK)

        # 4. Renvoyer OTP -> 204
        res_renv = self.client.post(
            "/api/v1/auth/otp/renvoyer/",
            {"telephone": "+2250700000001"},
            format='json'
        )
        self.assertEqual(res_renv.status_code, status.HTTP_204_NO_CONTENT)

    def test_inscription_personnel(self):
        # Opérateur tri autorisé
        payload = {
            "telephone": "+2250700000002",
            "nom": "Yao Tri",
            "mot_de_passe": "Password123!",
            "role": "operateur_tri"
        }
        res = self.client.post("/api/v1/auth/inscription/personnel/", payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', res.data)
        self.assertIn('refresh', res.data)

        # Rôle citoyen ou admin refusé -> 400
        payload_invalide = {
            "telephone": "+2250700000003",
            "nom": "Hacker",
            "mot_de_passe": "Password123!",
            "role": "administrateur"
        }
        res_err = self.client.post("/api/v1/auth/inscription/personnel/", payload_invalide, format='json')
        self.assertEqual(res_err.status_code, status.HTTP_400_BAD_REQUEST)

    def test_connexion_jwt_et_moi(self):
        # Connexion
        res_login = self.client.post(
            "/api/v1/auth/token/",
            {"telephone": "+2250100000001", "password": "password123"},
            format='json'
        )
        self.assertEqual(res_login.status_code, status.HTTP_200_OK)
        access = res_login.data['access']
        refresh = res_login.data['refresh']

        # GET /auth/moi/
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        res_moi = self.client.get("/api/v1/auth/moi/")
        self.assertEqual(res_moi.status_code, status.HTTP_200_OK)
        self.assertEqual(res_moi.data['telephone'], "+2250100000001")
        self.assertEqual(res_moi.data['role'], "administrateur")

        # Rafraîchir token
        self.client.credentials()  # reset
        res_ref = self.client.post(
            "/api/v1/auth/token/rafraichir/",
            {"refresh": refresh},
            format='json'
        )
        self.assertEqual(res_ref.status_code, status.HTTP_200_OK)
        self.assertIn('access', res_ref.data)

    def test_utilisateurs_lister_et_valider(self):
        # Créer un citoyen en attente
        citoyen = Utilisateur.objects.create_user(
            telephone="+2250700000099",
            nom="Awa En Attente",
            password="password123",
            role=Role.CITOYEN,
            statut_validation=StatutValidation.EN_ATTENTE,
            bac=self.bac
        )

        self.client.force_authenticate(user=self.admin)
        # Lister
        res_list = self.client.get("/api/v1/utilisateurs/?role=citoyen&statut_validation=en_attente")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(res_list.data['count'], 1)

        # Valider
        res_val = self.client.post(
            f"/api/v1/utilisateurs/{citoyen.id}/validation/",
            {"decision": "valider", "motif": "Vérification pièce d'identité OK"},
            format='json'
        )
        self.assertEqual(res_val.status_code, status.HTTP_200_OK)
        citoyen.refresh_from_db()
        self.assertEqual(citoyen.statut_validation, StatutValidation.VALIDE)

    def test_documentation_swagger_et_redoc(self):
        # Les endpoints de documentation sont publics et renvoient 200
        res_schema = self.client.get("/api/schema/")
        self.assertEqual(res_schema.status_code, status.HTTP_200_OK)
        self.assertEqual(res_schema['content-type'], "application/json")

        res_docs = self.client.get("/api/docs/")
        self.assertEqual(res_docs.status_code, status.HTTP_200_OK)
        self.assertIn("swagger-ui", str(res_docs.content))

        res_redoc = self.client.get("/api/redoc/")
        self.assertEqual(res_redoc.status_code, status.HTTP_200_OK)
        self.assertIn("redoc", str(res_redoc.content))


