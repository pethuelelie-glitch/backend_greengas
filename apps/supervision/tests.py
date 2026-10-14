from decimal import Decimal
from datetime import date
from django.utils import timezone
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.comptes.models import Utilisateur, Role, StatutValidation
from apps.referentiel.models import Site, Secteur, Bac
from apps.collecte.models import Tournee, StatutTournee, Collecte, StatutCollecte, StatutControle, Scan, StatutScan
from apps.supervision.models import (
    Parametre, JournalAudit, TypeObjet,
    Notification, TypeNotification, NiveauNotification
)
from apps.supervision.services import creer_notification, notifier_utilisateurs
from apps.energie.models import ProductionEnergie, StatutJournee, Alerte, TypeAlerte, StatutAlerte


class SupervisionEndpointsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Utilisateurs
        self.admin = Utilisateur.objects.create_user(
            telephone="+2250100000001",
            nom="Admin",
            password="password123",
            role=Role.ADMINISTRATEUR
        )
        self.personnel_attente = Utilisateur.objects.create_user(
            telephone="+2250100000002",
            email="operateur@greengas.ci",
            nom="Opérateur En Attente",
            password="password123",
            role=Role.OPERATEUR_TRI,
            statut_validation=StatutValidation.EN_ATTENTE
        )
        self.collecteur = Utilisateur.objects.create_user(
            telephone="+2250100000003",
            nom="Collecteur",
            password="password123",
            role=Role.COLLECTEUR
        )

        # Référentiel
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
        self.tournee = Tournee.objects.create(
            code="TRN-1013-01",
            date=date.today(),
            secteur=self.secteur,
            site=self.site,
            collecteur=self.collecteur,
            statut=StatutTournee.TRIEE
        )
        self.collecte = Collecte.objects.create(
            tournee=self.tournee,
            bac=self.bac,
            collecteur=self.collecteur,
            statut=StatutCollecte.VALIDEE,
            tare_kg=Decimal('10.00'),
            poids_brut_kg=Decimal('110.00'),
            poids_net_kg=Decimal('100.00'),
            statut_controle=StatutControle.A_VERIFIER
        )

        # Paramètre de test
        self.param = Parametre.objects.create(
            cle="coefficient_filiere_organique",
            valeur=Decimal('10.0000'),
            unite="pts/kg",
            statut="nominal",
            description="Coefficient de valorisation filière organique",
            source="contrat"
        )

    def test_verifications_queue(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/v1/verifications/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Doit contenir au moins la collecte_a_verifier et le compte_en_attente
        types = [item['type'] for item in res.data]
        self.assertIn('collecte_a_verifier', types)
        self.assertIn('compte_en_attente', types)

    def test_parametres_liste_et_update(self):
        self.client.force_authenticate(user=self.admin)
        # 1. Lister
        res_list = self.client.get("/api/v1/parametres/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertTrue(len(res_list.data) >= 1)

        # 2. Modifier
        payload = {
            "valeur": 12.5,
            "motif": "Revalorisation temporaire de la filière organique"
        }
        res_patch = self.client.patch(
            f"/api/v1/parametres/{self.param.cle}/",
            payload,
            format='json'
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(float(res_patch.data['valeur']), 12.5)

        # Vérifier que le journal d'audit a consigné la modification
        entree = JournalAudit.objects.filter(
            action="parametre.modifier",
            objet_id=self.param.cle
        ).first()
        self.assertIsNotNone(entree)
        self.assertEqual(entree.motif, "Revalorisation temporaire de la filière organique")

        self.client.force_authenticate(user=self.collecteur)
        res_collecteur = self.client.get("/api/v1/parametres/")
        self.assertEqual(res_collecteur.status_code, status.HTTP_403_FORBIDDEN)

    def test_journal_audit_lister(self):
        self.client.force_authenticate(user=self.admin)
        # Créer une entrée d'audit manuelle
        JournalAudit.objects.create(
            auteur=self.admin,
            action="compte.valider",
            objet_type=TypeObjet.UTILISATEUR,
            objet_id=str(self.personnel_attente.id),
            motif="Vérification physique effectuée"
        )
        res = self.client.get("/api/v1/journal/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 1)
        self.assertEqual(res.data['results'][0]['action'], "compte.valider")

    def test_bac_tracabilite(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(f"/api/v1/bacs/{self.bac.id}/tracabilite/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['bac']['code'], "BAC-014")
        self.assertIn('citoyens', res.data)
        self.assertIn('historique', res.data)
        self.assertEqual(len(res.data['historique']), 1)
        self.assertEqual(res.data['historique'][0]['collecte']['code_bac'], "BAC-014")

        referent = Utilisateur.objects.create_user(
            telephone="+2250100000098", nom="Référent", password="password123",
            role=Role.REFERENT, bac=self.bac,
        )
        self.client.force_authenticate(user=referent)
        res_referent = self.client.get(f"/api/v1/bacs/{self.bac.id}/tracabilite/")
        self.assertEqual(res_referent.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.collecteur)
        res_collecteur = self.client.get(f"/api/v1/bacs/{self.bac.id}/tracabilite/")
        self.assertEqual(res_collecteur.status_code, status.HTTP_403_FORBIDDEN)


class NotificationEndpointsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Utilisateurs
        self.aya = Utilisateur.objects.create_user(
            telephone="+2250100000010",
            nom="Aya Opératrice",
            password="greengas2026",
            role=Role.OPERATEUR_TRI,
            statut_validation=StatutValidation.VALIDE
        )
        self.admin = Utilisateur.objects.create_user(
            telephone="+2250100000011",
            nom="Admin Principal",
            password="greengas2026",
            role=Role.ADMINISTRATEUR,
            statut_validation=StatutValidation.VALIDE
        )
        self.serge = Utilisateur.objects.create_user(
            telephone="+2250100000012",
            nom="Serge Méthanisation",
            password="greengas2026",
            role=Role.RESPONSABLE_METHANISATION,
            statut_validation=StatutValidation.VALIDE
        )
        self.awa = Utilisateur.objects.create_user(
            telephone="+2250100000013",
            nom="Awa Citoyenne",
            password="greengas2026",
            role=Role.CITOYEN,
            statut_validation=StatutValidation.VALIDE
        )
        self.capteur = Utilisateur.objects.create_user(
            telephone="+2250100000014",
            nom="Capteur DIG-01",
            password="greengas2026",
            role=Role.CAPTEUR,
            statut_validation=StatutValidation.VALIDE
        )

        # Référentiel
        self.site = Site.objects.create(
            code="DIG-01",
            nom="Site Digesteur Test",
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
            residence="Résidence Test",
            secteur=self.secteur,
            nb_foyers_declares=20,
            latitude=Decimal('5.345000'),
            longitude=Decimal('-4.012000'),
            tare_kg=Decimal('10.00'),
            capacite_kg=Decimal('100.00')
        )

        # Tournées en attente de tri (Scénario 1)
        self.trn1 = Tournee.objects.create(
            code="TRN-0912-01",
            date=date.today(),
            secteur=self.secteur,
            site=self.site,
            collecteur=self.aya,
            statut=StatutTournee.COLLECTEE
        )
        self.trn2 = Tournee.objects.create(
            code="TRN-0912-02",
            date=date.today(),
            secteur=self.secteur,
            site=self.site,
            collecteur=self.aya,
            statut=StatutTournee.COLLECTEE
        )

        # Création des 2 notifications pour Aya (Scénario 1)
        self.notif_aya1 = Notification.objects.create(
            destinataire=self.aya,
            type=TypeNotification.TOURNEE_A_TRIER,
            niveau=NiveauNotification.INFO,
            titre="Tournée à trier",
            message="TRN-0912-01 (NORD, 500 kg) attend son tri.",
            objet_type="tournee",
            objet_id=self.trn1.id,
            lue=False
        )
        self.notif_aya2 = Notification.objects.create(
            destinataire=self.aya,
            type=TypeNotification.TOURNEE_A_TRIER,
            niveau=NiveauNotification.INFO,
            titre="Tournée à trier",
            message="TRN-0912-02 (NORD, 400 kg) attend son tri.",
            objet_type="tournee",
            objet_id=self.trn2.id,
            lue=False
        )

        # Notification pour Admin
        self.notif_admin = Notification.objects.create(
            destinataire=self.admin,
            type=TypeNotification.BAC_SURINSCRIT,
            niveau=NiveauNotification.INFO,
            titre="Bac surinscrit",
            message="BAC-014 : surinscrit.",
            objet_type="bac",
            objet_id=self.bac.id,
            lue=False
        )

    def test_scenario_1_compteur_non_lues_aya(self):
        """Scénario 1 : Aya a 2 notifications non lues pour les tournées à trier."""
        self.client.force_authenticate(user=self.aya)
        res = self.client.get("/api/v1/notifications/compteur/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['non_lues'], 2)

    def test_scenario_4_tout_lire(self):
        """Scénario 4 : Marquer toutes les notifications comme lues remet le compteur à 0."""
        self.client.force_authenticate(user=self.aya)
        res = self.client.post("/api/v1/notifications/tout-lire/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['marquees'], 2)

        # Vérifier que le compteur passe bien à 0
        res_compteur = self.client.get("/api/v1/notifications/compteur/")
        self.assertEqual(res_compteur.status_code, status.HTTP_200_OK)
        self.assertEqual(res_compteur.data['non_lues'], 0)

        # Vérifier que les notifications sont bien marquées lues avec date_lecture
        for notif in Notification.objects.filter(destinataire=self.aya):
            self.assertTrue(notif.lue)
            self.assertIsNotNone(notif.date_lecture)

    def test_scenario_5_lecture_notification_autre_utilisateur_renvoie_404(self):
        """Scénario 5 : Tenter de lire la notification d'un autre utilisateur renvoie 404."""
        self.client.force_authenticate(user=self.aya)
        res = self.client.post(f"/api/v1/notifications/{self.notif_admin.id}/lue/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_marquer_une_notification_lue(self):
        """Marquer une seule notification comme lue."""
        self.client.force_authenticate(user=self.aya)
        res = self.client.post(f"/api/v1/notifications/{self.notif_aya1.id}/lue/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['lue'])
        self.assertIsNotNone(res.data['date_lecture'])

        # Compteur décrémenté à 1
        res_compteur = self.client.get("/api/v1/notifications/compteur/")
        self.assertEqual(res_compteur.data['non_lues'], 1)

    def test_liste_notifications_et_filtres(self):
        """Lister les notifications avec filtres lue et type."""
        self.client.force_authenticate(user=self.aya)

        # Lister toutes
        res = self.client.get("/api/v1/notifications/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 2)

        # Filtre lue=false
        res_non_lues = self.client.get("/api/v1/notifications/?lue=false")
        self.assertEqual(res_non_lues.data['count'], 2)

        # Filtre lue=true
        res_lues = self.client.get("/api/v1/notifications/?lue=true")
        self.assertEqual(res_lues.data['count'], 0)

        # Filtre par type
        res_type = self.client.get("/api/v1/notifications/?type=tournee_a_trier")
        self.assertEqual(res_type.data['count'], 2)

        res_autre = self.client.get("/api/v1/notifications/?type=alerte_ouverte")
        self.assertEqual(res_autre.data['count'], 0)

    def test_capteur_exclusion(self):
        """Le compte technique capteur ne reçoit aucune notification et renvoie 0."""
        self.client.force_authenticate(user=self.capteur)
        res_list = self.client.get("/api/v1/notifications/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(res_list.data['count'], 0)

        res_count = self.client.get("/api/v1/notifications/compteur/")
        self.assertEqual(res_count.status_code, status.HTTP_200_OK)
        self.assertEqual(res_count.data['non_lues'], 0)

        # Création directe empêchée
        notif = creer_notification(
            destinataire=self.capteur,
            type=TypeNotification.SITE_MAINTENANCE,
            niveau=NiveauNotification.INFO,
            titre="Test",
            message="Test message"
        )
        self.assertIsNone(notif)

    def test_anti_doublon_bac_surinscrit_et_collecte(self):
        """Pas de notification doublon non-lue pour bac_surinscrit et collecte_a_verifier."""
        # Un non-lu existe déjà pour self.admin et self.bac.id
        doublon = creer_notification(
            destinataire=self.admin,
            type=TypeNotification.BAC_SURINSCRIT,
            niveau=NiveauNotification.INFO,
            titre="Bac surinscrit",
            message="Nouveau message",
            objet_type="bac",
            objet_id=self.bac.id
        )
        self.assertIsNone(doublon)

        # Une fois marqué lu, une nouvelle notification peut être émise
        self.notif_admin.lue = True
        self.notif_admin.save()

        nouvelle = creer_notification(
            destinataire=self.admin,
            type=TypeNotification.BAC_SURINSCRIT,
            niveau=NiveauNotification.INFO,
            titre="Bac surinscrit",
            message="Deuxième notification après lecture",
            objet_type="bac",
            objet_id=self.bac.id
        )
        self.assertIsNotNone(nouvelle)

    def test_exclusion_auteur_action(self):
        """L'auteur d'une action ne reçoit pas de notification pour sa propre action."""
        notif = creer_notification(
            destinataire=self.admin,
            type=TypeNotification.SITE_MAINTENANCE,
            niveau=NiveauNotification.ATTENTION,
            titre="Maintenance",
            message="Site en maintenance",
            auteur=self.admin
        )
        self.assertIsNone(notif)

    def test_scenario_2_tri_points_credites_notification(self):
        """Scénario 2 : Le tri d'une tournée crédite des points et notifie le citoyen."""
        # Créer une collecte validée sur la tournée
        collecte = Collecte.objects.create(
            tournee=self.trn1,
            bac=self.bac,
            collecteur=self.aya,
            statut=StatutCollecte.VALIDEE,
            tare_kg=Decimal('10.00'),
            poids_brut_kg=Decimal('110.00'),
            poids_net_kg=Decimal('100.00'),
            statut_controle=StatutControle.NORMAL
        )
        # Créer un scan comptabilisé pour Awa sur ce bac
        Scan.objects.create(
            citoyen=self.awa,
            bac=self.bac,
            statut=StatutScan.VALIDE,
            compte=True,
            distance_m=Decimal('12.50'),
            horodatage=timezone.now()
        )

        # Aya valide le tri de la tournée
        self.client.force_authenticate(user=self.aya)
        payload = {
            "lots": [
                {"categorie": "organique", "poids_kg": 70.0},
                {"categorie": "plastique", "poids_kg": 30.0}
            ],
            "niveau_contamination": "faible"
        }
        res = self.client.post(f"/api/v1/tournees/{self.trn1.id}/tri/", payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Vérifier qu'Awa a reçu une notification points_credites
        notif_awa = Notification.objects.filter(
            destinataire=self.awa,
            type=TypeNotification.POINTS_CREDITES
        ).first()
        self.assertIsNotNone(notif_awa)
        self.assertEqual(notif_awa.titre, "Points crédités")
        self.assertIn("points pour la collecte du", notif_awa.message)
        self.assertIn("BAC-014", notif_awa.message)

    def test_scenario_3_mesure_alerte_critique_notification(self):
        """Scénario 3 : Une mesure avec écart >= 20% déclenche une alerte critique pour les responsables et admins."""
        # Préparer la production du jour avec biogaz attendu = 32.0 m³
        prod = ProductionEnergie.objects.create(
            site=self.site,
            date=date.today(),
            statut_journee=StatutJournee.OUVERTE,
            poids_organique_recu_kg=Decimal('320.00'),
            biogaz_attendu_m3=Decimal('32.00')
        )

        # Envoi de mesure avec facteur 0.7 (22.4 m³ -> -30% d'écart) par le compte capteur
        self.client.force_authenticate(user=self.capteur)
        payload = {
            "date": str(date.today()),
            "biogaz_mesure_m3": 22.4,
            "ch4_pct": 55.0,
            "source": "capteur"
        }
        res = self.client.post(f"/api/v1/sites/{self.site.id}/mesures/", payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Vérifier qu'une alerte critique a été créée
        alerte = Alerte.objects.filter(site=self.site, statut=StatutAlerte.OUVERTE).first()
        self.assertIsNotNone(alerte)

        # Serge (responsable méthanisation) et Admin doivent avoir reçu la notification critique
        notif_serge = Notification.objects.filter(
            destinataire=self.serge,
            type=TypeNotification.ALERTE_OUVERTE,
            niveau=NiveauNotification.CRITIQUE
        ).first()
        self.assertIsNotNone(notif_serge)
        self.assertEqual(notif_serge.titre, "Alerte ouverte")
        self.assertIn("DIG-01", notif_serge.message)
        self.assertIn("-30 %", notif_serge.message)

        notif_admin = Notification.objects.filter(
            destinataire=self.admin,
            type=TypeNotification.ALERTE_OUVERTE,
            niveau=NiveauNotification.CRITIQUE
        ).first()
        self.assertIsNotNone(notif_admin)
