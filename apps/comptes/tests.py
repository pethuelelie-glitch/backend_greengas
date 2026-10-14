from decimal import Decimal
from unittest.mock import patch
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

        from apps.supervision.models import Parametre
        Parametre.objects.update_or_create(
            cle="validation_comptes_personnel",
            defaults={"valeur": Decimal('1'), "unite": "", "statut": "aligne"}
        )

    def test_exception_serveur_ne_revele_pas_les_details_internes(self):
        from types import SimpleNamespace
        from apps.comptes.exceptions import custom_exception_handler

        secret_interne = "mot-de-passe-db-interne"
        response = custom_exception_handler(
            RuntimeError(secret_interne),
            {'request': SimpleNamespace(path='/api/v1/test/')},
        )

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data['code'], 'ERREUR_SERVEUR')
        self.assertEqual(response.data['details'], {})
        self.assertNotIn(secret_interne, str(response.data))

    def test_validation_personnel_annule_si_le_journal_audit_echoue(self):
        utilisateur = Utilisateur.objects.create_user(
            telephone="+2250700000088",
            email="audit.fail@greengas.ci",
            nom="Personnel en attente",
            password="Password123!",
            role=Role.OPERATEUR_TRI,
            statut_validation=StatutValidation.EN_ATTENTE,
        )
        self.client.force_authenticate(user=self.admin)

        with patch(
            'apps.supervision.models.JournalAudit.objects.create',
            side_effect=RuntimeError("échec du journal"),
        ):
            response = self.client.post(
                f"/api/v1/utilisateurs/{utilisateur.id}/validation/",
                {"decision": "valider"},
                format='json',
            )

        utilisateur.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(utilisateur.statut_validation, StatutValidation.EN_ATTENTE)

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

    def test_otp_est_aleatoire_et_limite_les_tentatives(self):
        telephone = "+2250700000099"
        user = Utilisateur.objects.create_user(
            telephone=telephone,
            nom="Utilisateur OTP",
            password="Password123!",
            role=Role.CITOYEN,
            telephone_verifie=False,
        )
        otp = CodeOTP.generer_code(telephone)
        self.assertRegex(otp.code, r"^[0-9]{6}$")
        self.assertNotIn(otp.code, str(otp))

        for _ in range(CodeOTP.MAX_TENTATIVES):
            response = self.client.post(
                "/api/v1/auth/otp/verifier/",
                {"telephone": telephone, "code": "000000" if otp.code != "000000" else "999999"},
                format='json',
            )
            self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

        otp.refresh_from_db()
        self.assertEqual(otp.tentatives, CodeOTP.MAX_TENTATIVES)
        response = self.client.post(
            "/api/v1/auth/otp/verifier/",
            {"telephone": telephone, "code": otp.code},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        user.refresh_from_db()
        self.assertFalse(user.telephone_verifie)

        otp_nouveau = CodeOTP.generer_code(telephone)
        response = self.client.post(
            "/api/v1/auth/otp/verifier/",
            {"telephone": telephone, "code": otp_nouveau.code},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.telephone_verifie)

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
        from apps.supervision.models import JournalAudit
        self.assertTrue(JournalAudit.objects.filter(
            action="utilisateur.demande_inscription",
            objet_id=res_inscr.data['id'],
        ).exists())
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
        # Vérification OpenAPI 1.5.0
        res_schema = self.client.get("/api/schema/")
        self.assertEqual(res_schema.status_code, status.HTTP_200_OK)
        self.assertEqual(res_schema.json()['info']['version'], "1.6.1")

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

    def test_rotation_revoque_ancien_refresh_et_deconnexion_revoque_le_nouveau(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        user = Utilisateur.objects.create_user(
            telephone="+2250766778800",
            nom="Utilisateur Jeton",
            password="greengas2026",
            role=Role.CITOYEN,
            statut_validation=StatutValidation.VALIDE,
        )
        refresh_initial = str(RefreshToken.for_user(user))

        res_rotation = self.client.post(
            "/api/v1/auth/token/rafraichir/",
            {"refresh": refresh_initial},
            format='json',
        )
        self.assertEqual(res_rotation.status_code, status.HTTP_200_OK)
        self.assertIn('access', res_rotation.data)
        self.assertIn('refresh', res_rotation.data)

        res_rejeu = self.client.post(
            "/api/v1/auth/token/rafraichir/",
            {"refresh": refresh_initial},
            format='json',
        )
        self.assertEqual(res_rejeu.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {res_rotation.data['access']}")
        res_deconnexion = self.client.post(
            "/api/v1/auth/deconnexion/",
            {"refresh": res_rotation.data['refresh']},
            format='json',
        )
        self.assertEqual(res_deconnexion.status_code, status.HTTP_204_NO_CONTENT)

        res_refresh_revoque = self.client.post(
            "/api/v1/auth/token/rafraichir/",
            {"refresh": res_rotation.data['refresh']},
            format='json',
        )
        self.assertEqual(res_refresh_revoque.status_code, status.HTTP_401_UNAUTHORIZED)

        token_orphelin = str(RefreshToken.for_user(user))
        user.delete()
        res_compte_supprime = self.client.post(
            "/api/v1/auth/token/rafraichir/",
            {"refresh": token_orphelin},
            format='json',
        )
        self.assertEqual(res_compte_supprime.status_code, status.HTTP_401_UNAUTHORIZED)


class Contrat150TestCase(TestCase):
    """
    Tests exhaustifs du Contrat 1.5.0 : Validation du personnel activable.
    """
    def setUp(self):
        self.client = APIClient()

        # Admin
        self.admin = Utilisateur.objects.create_user(
            telephone="+2250100000001",
            email="admin@greengas.ci",
            nom="Admin Principal",
            password="password123",
            role=Role.ADMINISTRATEUR,
            statut_validation=StatutValidation.VALIDE
        )

        # Paramètre validation_comptes_personnel (valeur départ 0)
        from apps.supervision.models import Parametre
        self.param, _ = Parametre.objects.update_or_create(
            cle="validation_comptes_personnel",
            defaults={
                "valeur": Decimal('0'),
                "unite": "",
                "statut": "aligne",
                "description": "Validation des comptes du personnel par un administrateur"
            }
        )

    def test_patch_validation_comptes_personnel_valeurs(self):
        """
        Modification de validation_comptes_personnel :
        - 0 ou 1 autorisés (200 OK)
        - toute autre valeur -> 422 PARAMETRE_INVALIDE
        """
        self.client.force_authenticate(user=self.admin)

        # 1. Passer à 1 -> OK
        res1 = self.client.patch(
            "/api/v1/parametres/validation_comptes_personnel/",
            {"valeur": 1, "motif": "Activation de la validation manuelle"},
            format='json'
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertEqual(float(res1.data['valeur']), 1.0)

        # 2. Passer à 0 -> OK
        res0 = self.client.patch(
            "/api/v1/parametres/validation_comptes_personnel/",
            {"valeur": 0, "motif": "Désactivation"},
            format='json'
        )
        self.assertEqual(res0.status_code, status.HTTP_200_OK)
        self.assertEqual(float(res0.data['valeur']), 0.0)

        # 3. Passer à 2 -> 422 PARAMETRE_INVALIDE
        res2 = self.client.patch(
            "/api/v1/parametres/validation_comptes_personnel/",
            {"valeur": 2},
            format='json'
        )
        self.assertEqual(res2.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(res2.data['code'], "PARAMETRE_INVALIDE")

        # 4. Passer à -1 -> 422 PARAMETRE_INVALIDE
        res_neg = self.client.patch(
            "/api/v1/parametres/validation_comptes_personnel/",
            {"valeur": -1},
            format='json'
        )
        self.assertEqual(res_neg.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(res_neg.data['code'], "PARAMETRE_INVALIDE")

    def test_inscription_personnel_selon_parametre(self):
        """
        POST /auth/inscription/personnel/ (toujours sans jetons) :
        - paramètre à 0 -> inscription publique refusée, inscription admin autorisée
        - paramètre à 1 -> statut_validation = en_attente, notification compte_a_valider aux admins
        """
        from apps.supervision.models import Notification, TypeNotification

        # 1. Paramètre à 0 : validation désactivée
        self.param.valeur = Decimal('0')
        self.param.save()

        payload1 = {
            "telephone": "+2250788000001",
            "email": "agent1@greengas.ci",
            "nom": "Agent Valide Direct",
            "mot_de_passe": "password123",
            "role": "operateur_tri"
        }
        res_public = self.client.post("/api/v1/auth/inscription/personnel/", payload1, format='json')
        self.assertEqual(res_public.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(Utilisateur.objects.filter(telephone=payload1['telephone']).exists())

        self.client.force_authenticate(user=self.admin)
        res1 = self.client.post("/api/v1/auth/inscription/personnel/", payload1, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res1.data['statut_validation'], "valide")
        self.assertNotIn("access", res1.data)
        # Pas de notification créée
        self.assertFalse(Notification.objects.filter(type=TypeNotification.COMPTE_A_VALIDER, objet_id=res1.data['id']).exists())

        # 2. Paramètre à 1 : validation activée
        self.param.valeur = Decimal('1')
        self.param.save()
        self.client.force_authenticate(user=None)

        payload2 = {
            "telephone": "+2250788000002",
            "email": "agent2@greengas.ci",
            "nom": "Agent En Attente",
            "mot_de_passe": "password123",
            "role": "responsable_methanisation"
        }
        res2 = self.client.post("/api/v1/auth/inscription/personnel/", payload2, format='json')
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res2.data['statut_validation'], "en_attente")
        self.assertNotIn("access", res2.data)
        # Notification compte_a_valider émise pour les admins
        self.assertTrue(Notification.objects.filter(type=TypeNotification.COMPTE_A_VALIDER, objet_id=res2.data['id']).exists())

    def test_inscription_personnel_est_annulee_si_audit_echoue(self):
        from apps.comptes.serializers import InscriptionPersonnelSerializer
        from apps.supervision.models import JournalAudit

        self.param.valeur = Decimal('1')
        self.param.save()
        payload = {
            "telephone": "+2250788000099",
            "email": "sans.audit@greengas.ci",
            "nom": "Personnel sans audit",
            "mot_de_passe": "password123",
            "role": Role.OPERATEUR_TRI,
        }
        serializer = InscriptionPersonnelSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        with patch.object(JournalAudit.objects, 'create', side_effect=RuntimeError("audit indisponible")):
            with self.assertRaises(RuntimeError):
                serializer.save()

        self.assertFalse(Utilisateur.objects.filter(telephone=payload['telephone']).exists())

    def test_connexion_et_deconnexion_dynamique_requetes_authentifiees(self):
        """
        - paramètre à 1 -> un compte en_attente reçoit 403 COMPTE_NON_VALIDE à la connexion
        - paramètre à 0 -> un compte en_attente peut se connecter
        - requêtes authentifiées : si on réactive la validation (1), un compte encore en attente
          est déconnecté (403 COMPTE_NON_VALIDE) à sa requête suivante
        - token refresh : refusé si paramètre à 1
        """
        from rest_framework_simplejwt.tokens import RefreshToken

        # Créer utilisateur en attente
        user_attente = Utilisateur.objects.create_user(
            telephone="+2250799000001",
            email="attente@greengas.ci",
            nom="Personnel Attente",
            password="greengas2026",
            role=Role.OPERATEUR_TRI,
            statut_validation=StatutValidation.EN_ATTENTE
        )

        # 1. Paramètre à 1 -> connexion refusée 403
        self.param.valeur = Decimal('1')
        self.param.save()

        res_login_bloque = self.client.post(
            "/api/v1/auth/token/",
            {"telephone": user_attente.telephone, "mot_de_passe": "greengas2026"},
            format='json'
        )
        self.assertEqual(res_login_bloque.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_login_bloque.data['code'], "COMPTE_NON_VALIDE")

        # 2. Paramètre à 0 -> connexion acceptée 200 avec jetons
        self.param.valeur = Decimal('0')
        self.param.save()

        res_login_ok = self.client.post(
            "/api/v1/auth/token/",
            {"telephone": user_attente.telephone, "mot_de_passe": "greengas2026"},
            format='json'
        )
        self.assertEqual(res_login_ok.status_code, status.HTTP_200_OK)
        access_token = res_login_ok.data['access']
        refresh_token = res_login_ok.data['refresh']

        # 3. Requête authentifiée autorisée tant que paramètre à 0
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        res_moi = self.client.get("/api/v1/auth/moi/")
        self.assertEqual(res_moi.status_code, status.HTTP_200_OK)

        # 4. On réactive la validation (paramètre = 1) -> requête suivante rejetée 403
        self.param.valeur = Decimal('1')
        self.param.save()

        res_moi_bloque = self.client.get("/api/v1/auth/moi/")
        self.assertEqual(res_moi_bloque.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_moi_bloque.data['code'], "COMPTE_NON_VALIDE")

        # 5. Rafraîchissement de token également rejeté 403
        self.client.credentials()  # reset auth header
        res_refresh = self.client.post(
            "/api/v1/auth/token/rafraichir/",
            {"refresh": refresh_token},
            format='json'
        )
        self.assertEqual(res_refresh.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_refresh.data['code'], "COMPTE_NON_VALIDE")
