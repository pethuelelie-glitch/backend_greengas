from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.comptes.models import Utilisateur, Role, StatutValidation
from apps.referentiel.models import Site, Secteur, Bac, StatutSite
from apps.collecte.models import (
    Scan, StatutScan,
    Tournee, StatutTournee, MotifAffectation,
    Collecte, StatutCollecte, StatutControle, SourceMesure
)


class CollecteEndpointsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Utilisateurs
        self.admin = Utilisateur.objects.create_user(
            telephone="+2250100000001",
            nom="Admin",
            password="password123",
            role=Role.ADMINISTRATEUR
        )
        self.collecteur = Utilisateur.objects.create_user(
            telephone="+2250100000002",
            nom="Collecteur",
            password="password123",
            role=Role.COLLECTEUR
        )
        self.citoyen_valide = Utilisateur.objects.create_user(
            telephone="+2250100000003",
            nom="Citoyen Valide",
            password="password123",
            role=Role.CITOYEN,
            statut_validation=StatutValidation.VALIDE
        )
        self.citoyen_en_attente = Utilisateur.objects.create_user(
            telephone="+2250100000004",
            nom="Citoyen En Attente",
            password="password123",
            role=Role.CITOYEN,
            statut_validation=StatutValidation.EN_ATTENTE
        )

        # Référentiel
        self.site_nominal = Site.objects.create(
            code="DIG-01",
            nom="Site Digesteur Nominal",
            statut=StatutSite.NOMINAL,
            capacite_kg_jour=1000,
            latitude=Decimal('5.345000'),
            longitude=Decimal('-4.012000')
        )
        self.site_repli = Site.objects.create(
            code="DIG-02",
            nom="Site Repli",
            statut=StatutSite.NOMINAL,
            capacite_kg_jour=800,
            latitude=Decimal('5.350000'),
            longitude=Decimal('-4.000000')
        )
        self.secteur = Secteur.objects.create(
            code="NORD",
            nom="Secteur Nord",
            site=self.site_nominal,
            site_repli=self.site_repli
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
        self.citoyen_valide.bac = self.bac
        self.citoyen_valide.save()

    def test_scan_compte_non_valide(self):
        self.client.force_authenticate(user=self.citoyen_en_attente)
        payload = {
            "code_bac": "BAC-014",
            "latitude": 5.345000,
            "longitude": -4.012000
        }
        res = self.client.post("/api/v1/scans/", payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(res.data['code'], "COMPTE_NON_VALIDE")

    def test_scan_valide_et_debounce(self):
        self.client.force_authenticate(user=self.citoyen_valide)
        payload = {
            "code_bac": "BAC-014",
            "latitude": 5.345000,
            "longitude": -4.012000
        }
        # 1er scan valide
        res1 = self.client.post("/api/v1/scans/", payload, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res1.data['statut'], "valide")
        self.assertTrue(res1.data['compte'])

        # 2ème scan immédiat (< 10s) -> anti-rebond (debounce)
        res2 = self.client.post("/api/v1/scans/", payload, format='json')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data['id'], res1.data['id'])

    def test_scan_hors_zone(self):
        self.client.force_authenticate(user=self.citoyen_valide)
        # Position très éloignée (latitude différente de 0.1 deg ~ 11 km)
        payload = {
            "code_bac": "BAC-014",
            "latitude": 5.445000,
            "longitude": -4.012000
        }
        res = self.client.post("/api/v1/scans/", payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['statut'], "hors_zone")
        self.assertFalse(res.data['compte'])

    def test_scan_plafond_journalier(self):
        self.client.force_authenticate(user=self.citoyen_valide)
        # Créer manuellement 2 scans comptabilisés aujourd'hui
        h_past = timezone.now() - timedelta(minutes=30)
        s1 = Scan.objects.create(citoyen=self.citoyen_valide, bac=self.bac, statut=StatutScan.VALIDE, compte=True)
        s2 = Scan.objects.create(citoyen=self.citoyen_valide, bac=self.bac, statut=StatutScan.VALIDE, compte=True)
        Scan.objects.filter(id__in=[s1.id, s2.id]).update(horodatage=h_past)


        payload = {
            "code_bac": "BAC-014",
            "latitude": 5.345000,
            "longitude": -4.012000
        }
        res = self.client.post("/api/v1/scans/", payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['statut'], "refuse_plafond")
        self.assertFalse(res.data['compte'])

    def test_historique_scans_est_limite_au_proprietaire(self):
        Scan.objects.create(citoyen=self.citoyen_valide, bac=self.bac, statut=StatutScan.VALIDE, compte=True)
        autre_citoyen = Utilisateur.objects.create_user(
            telephone="+2250100000099", nom="Autre citoyen", password="password123", role=Role.CITOYEN
        )
        Scan.objects.create(citoyen=autre_citoyen, bac=self.bac, statut=StatutScan.VALIDE, compte=True)

        self.client.force_authenticate(user=self.citoyen_valide)
        response = self.client.get(f"/api/v1/scans/?citoyen_id={autre_citoyen.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(str(response.data['results'][0]['citoyen']), str(self.citoyen_valide.id))

        self.client.force_authenticate(user=self.collecteur)
        response_collecteur = self.client.get('/api/v1/scans/')
        self.assertEqual(response_collecteur.data['count'], 0)

    def test_tournee_workflow_complet(self):
        # 1. Admin crée la tournée
        self.client.force_authenticate(user=self.admin)
        payload = {
            "secteur_id": str(self.secteur.id),
            "date": str(date.today()),
            "collecteur_id": str(self.collecteur.id),
            "bac_ids": [str(self.bac.id)]
        }
        res_create = self.client.post("/api/v1/tournees/", payload, format='json')
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        tournee_id = res_create.data['id']
        self.assertTrue(res_create.data['code'].startswith("TRN-"))
        self.assertEqual(res_create.data['motif_affectation'], MotifAffectation.SECTEUR)

        # 2. Collecteur démarre la tournée
        self.client.force_authenticate(user=self.collecteur)
        res_start = self.client.post(f"/api/v1/tournees/{tournee_id}/demarrer/")
        self.assertEqual(res_start.status_code, status.HTTP_200_OK)
        self.assertEqual(res_start.data['statut'], "en_cours")

        # 3. Récupérer la collecte créée
        collecte = Collecte.objects.get(tournee_id=tournee_id, bac=self.bac)
        self.assertEqual(collecte.statut, StatutCollecte.EN_ATTENTE_PESEE)

        # 4. Capteur pèse la collecte (tare = 10kg, brut = 60kg -> net = 50kg)
        self.client.force_authenticate(user=self.admin)
        res_pesee = self.client.post(
            f"/api/v1/collectes/{collecte.id}/pesee/",
            {"poids_brut_kg": 60.0, "source": "capteur"},
            format='json'
        )
        self.assertEqual(res_pesee.status_code, status.HTTP_200_OK)
        self.assertEqual(float(res_pesee.data['poids_net_kg']), 50.0)
        self.assertEqual(res_pesee.data['statut'], "pesee")

        # 5. Créer 2 scans citoyens pour le calcul du kg/scan
        Scan.objects.create(citoyen=self.citoyen_valide, bac=self.bac, statut=StatutScan.VALIDE, compte=True)
        Scan.objects.create(citoyen=self.citoyen_valide, bac=self.bac, statut=StatutScan.VALIDE, compte=True)

        # 6. Collecteur valide la collecte
        self.client.force_authenticate(user=self.collecteur)
        res_valider = self.client.post(f"/api/v1/collectes/{collecte.id}/valider/")
        self.assertEqual(res_valider.status_code, status.HTTP_200_OK)
        self.assertEqual(res_valider.data['statut'], "validee")
        self.assertEqual(res_valider.data['scans_valides'], 2)
        # 50 kg / 2 scans = 25 kg/scan > 0.3 -> normal
        self.assertEqual(res_valider.data['statut_controle'], "normal")

        # 7. Collecteur clôture la tournée
        res_close = self.client.post(f"/api/v1/tournees/{tournee_id}/cloturer/")
        self.assertEqual(res_close.status_code, status.HTTP_200_OK)
        self.assertEqual(res_close.data['statut'], "collectee")
