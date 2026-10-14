from decimal import Decimal
from datetime import date
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.comptes.models import Utilisateur, Role
from apps.referentiel.models import Site, Secteur, Bac
from apps.collecte.models import (
    Tournee, StatutTournee, NiveauContamination,
    Collecte, StatutCollecte, StatutControle,
    Scan, StatutScan
)
from apps.tri.models import LotTrie, Categorie, Destination
from apps.greenpoints.models import GreenPointsTransaction, StatutTransaction
from apps.energie.models import ProductionEnergie
from apps.supervision.models import JournalAudit, Parametre


class TriEndpointsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Utilisateurs
        self.admin = Utilisateur.objects.create_user(
            telephone="+2250100000001",
            nom="Admin",
            password="password123",
            role=Role.ADMINISTRATEUR
        )
        self.operateur = Utilisateur.objects.create_user(
            telephone="+2250100000002",
            nom="Operateur Tri",
            password="password123",
            role=Role.OPERATEUR_TRI
        )
        self.collecteur = Utilisateur.objects.create_user(
            telephone="+2250100000003",
            nom="Collecteur",
            password="password123",
            role=Role.COLLECTEUR
        )
        self.citoyen1 = Utilisateur.objects.create_user(
            telephone="+2250100000004",
            nom="Citoyen 1",
            password="password123",
            role=Role.CITOYEN
        )
        self.citoyen2 = Utilisateur.objects.create_user(
            telephone="+2250100000005",
            nom="Citoyen 2",
            password="password123",
            role=Role.CITOYEN
        )

        # Référentiel
        self.site = Site.objects.create(
            code="DIG-01",
            nom="Site Digesteur",
            statut="nominal",
            capacite_kg_jour=1000,
            latitude=5.345,
            longitude=-4.012
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
            latitude=Decimal('5.345678'),
            longitude=Decimal('-4.012345'),
            tare_kg=Decimal('10.00'),
            capacite_kg=Decimal('100.00')
        )


        # Scans citoyens sur le bac
        # Citoyen 1: 3 scans, Citoyen 2: 1 scan -> total = 4 scans
        for _ in range(3):
            Scan.objects.create(
                citoyen=self.citoyen1,
                bac=self.bac,
                statut=StatutScan.VALIDE,
                compte=True
            )
        Scan.objects.create(
            citoyen=self.citoyen2,
            bac=self.bac,
            statut=StatutScan.VALIDE,
            compte=True
        )

        # Tournée et Collecte
        self.tournee = Tournee.objects.create(
            code="TRN-1013-01",
            date=date.today(),
            secteur=self.secteur,
            site=self.site,
            collecteur=self.collecteur,
            statut=StatutTournee.COLLECTEE
        )
        self.tournee.bacs.add(self.bac)

        self.collecte = Collecte.objects.create(
            tournee=self.tournee,
            bac=self.bac,
            collecteur=self.collecteur,
            statut=StatutCollecte.VALIDEE,
            tare_kg=Decimal('10.00'),
            poids_brut_kg=Decimal('110.00'),
            poids_net_kg=Decimal('100.00'),
            statut_controle=StatutControle.NORMAL
        )

    def test_tournee_tri_non_authentifie(self):
        response = self.client.post(f"/api/v1/tournees/{self.tournee.id}/tri/", {})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_tournee_tri_citoyen_acces_refuse(self):
        self.client.force_authenticate(user=self.citoyen1)
        response = self.client.post(f"/api/v1/tournees/{self.tournee.id}/tri/", {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_tournee_statut_invalide(self):
        self.client.force_authenticate(user=self.operateur)
        self.tournee.statut = StatutTournee.EN_COURS
        self.tournee.save()

        payload = {
            "niveau_contamination": "faible",
            "lots": [
                {"categorie": "organique", "poids_kg": 100}
            ]
        }
        response = self.client.post(f"/api/v1/tournees/{self.tournee.id}/tri/", payload, format='json')
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.data['code'], "TOURNEE_STATUT_INVALIDE")

    def test_tolerance_tri_depassee_sans_motif(self):
        self.client.force_authenticate(user=self.operateur)
        # Collecte = 100 kg, Tri = 110 kg -> 10% d'écart > 2% de tolérance
        payload = {
            "niveau_contamination": "faible",
            "lots": [
                {"categorie": "organique", "poids_kg": 110}
            ]
        }
        response = self.client.post(f"/api/v1/tournees/{self.tournee.id}/tri/", payload, format='json')
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.data['code'], "ECART_TOLERANCE")
        self.assertIn("ecart_pct", response.data['details'])
        self.assertEqual(response.data['details']['ecart_pct'], 10.0)

    def test_tolerance_tri_depassee_avec_motif_acceptee(self):
        self.client.force_authenticate(user=self.operateur)
        payload = {
            "niveau_contamination": "faible",
            "motif_ecart": "Humidité importante suite à de fortes pluies",
            "lots": [
                {"categorie": "organique", "poids_kg": 110}
            ]
        }
        response = self.client.post(f"/api/v1/tournees/{self.tournee.id}/tri/", payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['motif_ecart'], "Humidité importante suite à de fortes pluies")

    def test_validation_tri_pipeline_complet(self):
        self.client.force_authenticate(user=self.operateur)
        # 100 kg total : 60 kg organique (coef 10), 30 kg plastique (coef 8), 10 kg metal (coef 15)
        # valeur_kg = (0.6 * 10) + (0.3 * 8) + (0.1 * 15) = 6.0 + 2.4 + 1.5 = 9.9
        # coef_qualite = 1.0 (faible)
        # points_bac = 100 * 9.9 * 1.0 = 990
        # Citoyen 1 (3/4 scans) : floor(990 * 3 / 4) = 742 points
        # Citoyen 2 (1/4 scans) : floor(990 * 1 / 4) = 247 points
        payload = {
            "niveau_contamination": "faible",
            "lots": [
                {"categorie": "organique", "poids_kg": 60},
                {"categorie": "plastique", "poids_kg": 30},
                {"categorie": "metal", "poids_kg": 10}
            ]
        }
        response = self.client.post(f"/api/v1/tournees/{self.tournee.id}/tri/", payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data

        # Vérifications résultat
        self.assertEqual(data['code_tournee'], "TRN-1013-01")
        self.assertEqual(data['niveau_contamination'], "faible")
        self.assertEqual(float(data['coef_qualite']), 1.0)
        self.assertEqual(float(data['poids_collecte_kg']), 100.0)
        self.assertEqual(float(data['poids_trie_kg']), 100.0)
        self.assertEqual(float(data['ecart_pct']), 0.0)
        self.assertEqual(float(data['valeur_kg']), 9.9)
        self.assertEqual(len(data['lots']), 3)
        self.assertEqual(data['nb_transactions'], 2)
        self.assertEqual(data['points_credites'], 742 + 247)
        self.assertEqual(data['points_en_attente'], 0)

        # Vérification lots en DB
        lots_db = LotTrie.objects.filter(tournee=self.tournee)
        self.assertEqual(lots_db.count(), 3)
        lot_org = lots_db.get(categorie="organique")
        self.assertEqual(lot_org.destination, Destination.DIGESTEUR)
        self.assertEqual(lot_org.site, self.site)
        self.assertTrue(lot_org.code_lot.startswith("ORG-"))
        self.assertEqual(float(lot_org.part_pct), 60.0)

        lot_pla = lots_db.get(categorie="plastique")
        self.assertEqual(lot_pla.destination, Destination.RECYCLEUR)
        self.assertIsNone(lot_pla.site)
        self.assertTrue(lot_pla.code_lot.startswith("PLA-"))

        # Vérification transactions GreenPoints
        tx1 = GreenPointsTransaction.objects.get(citoyen=self.citoyen1, tournee=self.tournee)
        self.assertEqual(tx1.scans_citoyen, 3)
        self.assertEqual(tx1.scans_bac, 4)
        self.assertEqual(tx1.points, 742)
        self.assertEqual(tx1.statut, StatutTransaction.CREDITEE)

        tx2 = GreenPointsTransaction.objects.get(citoyen=self.citoyen2, tournee=self.tournee)
        self.assertEqual(tx2.scans_citoyen, 1)
        self.assertEqual(tx2.scans_bac, 4)
        self.assertEqual(tx2.points, 247)
        self.assertEqual(tx2.statut, StatutTransaction.CREDITEE)

        # Vérification statut tournée
        self.tournee.refresh_from_db()
        self.assertEqual(self.tournee.statut, StatutTournee.TRIEE)
        self.assertEqual(self.tournee.niveau_contamination, "faible")

        # Vérification bilan ProductionEnergie (60 kg organique -> 6.0 m³ attendu avec coef 0.1)
        prod = ProductionEnergie.objects.get(site=self.site, date=self.tournee.date)
        self.assertEqual(float(prod.poids_organique_recu_kg), 60.0)
        self.assertEqual(float(prod.biogaz_attendu_m3), 6.0)

        # Vérification de l'idempotence / conflit de re-tri
        conflit_response = self.client.post(f"/api/v1/tournees/{self.tournee.id}/tri/", payload, format='json')
        self.assertEqual(conflit_response.status_code, status.HTTP_409_CONFLICT)

        # Vérification GET résultat de tri
        get_response = self.client.get(f"/api/v1/tournees/{self.tournee.id}/tri/")
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data['code_tournee'], "TRN-1013-01")
        self.assertEqual(get_response.data['nb_transactions'], 2)

    def test_lister_lots_avec_filtres(self):
        self.client.force_authenticate(user=self.admin)
        # Créer des lots
        LotTrie.objects.create(
            code_lot="ORG-0001",
            tournee=self.tournee,
            categorie=Categorie.ORGANIQUE,
            poids_kg=Decimal('50.00'),
            part_pct=Decimal('50.00'),
            destination=Destination.DIGESTEUR,
            site=self.site
        )
        LotTrie.objects.create(
            code_lot="PLA-0001",
            tournee=self.tournee,
            categorie=Categorie.PLASTIQUE,
            poids_kg=Decimal('50.00'),
            part_pct=Decimal('50.00'),
            destination=Destination.RECYCLEUR
        )

        response = self.client.get("/api/v1/lots/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)

        # Filtrer par catégorie
        response_filtre = self.client.get("/api/v1/lots/?categorie=organique")
        self.assertEqual(response_filtre.status_code, status.HTTP_200_OK)
        self.assertEqual(response_filtre.data['count'], 1)
        self.assertEqual(response_filtre.data['results'][0]['code_lot'], "ORG-0001")

        self.client.force_authenticate(user=self.citoyen1)
        res_citoyen_lots = self.client.get('/api/v1/lots/')
        self.assertEqual(res_citoyen_lots.status_code, status.HTTP_403_FORBIDDEN)

        res_citoyen_tri = self.client.get(f"/api/v1/tournees/{self.tournee.id}/tri/")
        self.assertEqual(res_citoyen_tri.status_code, status.HTTP_403_FORBIDDEN)
