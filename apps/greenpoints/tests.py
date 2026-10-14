from decimal import Decimal
from datetime import date
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.comptes.models import Utilisateur, Role
from apps.referentiel.models import Site, Secteur, Bac
from apps.collecte.models import Tournee, StatutTournee, Collecte, StatutCollecte
from apps.greenpoints.models import (
    GreenPointsTransaction, StatutTransaction,
    Recompense, Echange
)


class GreenPointsEndpointsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Utilisateurs
        self.admin = Utilisateur.objects.create_user(
            telephone="+2250100000001",
            nom="Admin",
            password="password123",
            role=Role.ADMINISTRATEUR
        )
        self.citoyen = Utilisateur.objects.create_user(
            telephone="+2250100000002",
            nom="Citoyen Solde",
            password="password123",
            role=Role.CITOYEN
        )
        self.autre_citoyen = Utilisateur.objects.create_user(
            telephone="+2250100000003",
            nom="Autre Citoyen",
            password="password123",
            role=Role.CITOYEN
        )
        self.collecteur = Utilisateur.objects.create_user(
            telephone="+2250100000004",
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
            poids_net_kg=Decimal('100.00')
        )

        # Transactions initiales pour self.citoyen :
        # 1 créditée de 300 pts, 1 en attente de 100 pts
        GreenPointsTransaction.objects.create(
            citoyen=self.citoyen,
            bac=self.bac,
            tournee=self.tournee,
            collecte=self.collecte,
            scans_citoyen=3,
            scans_bac=3,
            poids_attribue_kg=Decimal('100.00'),
            valeur_kg=Decimal('10.00'),
            coef_qualite=Decimal('1.00'),
            points=300,
            statut=StatutTransaction.CREDITEE
        )
        GreenPointsTransaction.objects.create(
            citoyen=self.citoyen,
            bac=self.bac,
            tournee=self.tournee,
            collecte=self.collecte,
            scans_citoyen=1,
            scans_bac=1,
            poids_attribue_kg=Decimal('10.00'),
            valeur_kg=Decimal('10.00'),
            coef_qualite=Decimal('1.00'),
            points=100,
            statut=StatutTransaction.EN_ATTENTE
        )

        # Récompense de test (coût: 200 pts)
        self.recompense = Recompense.objects.create(
            nom="Recharge Mobile 1000 FCFA",
            description="Recharge téléphonique tous opérateurs",
            cout_points=200,
            partenaire="Orange CI",
            actif=True
        )

    def test_solde_citoyen(self):
        self.client.force_authenticate(user=self.citoyen)
        res = self.client.get("/api/v1/greenpoints/solde/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # total_gagne = 300, total_echange = 0 -> solde = 300, en_attente = 100
        self.assertEqual(res.data['solde'], 300)
        self.assertEqual(res.data['total_gagne'], 300)
        self.assertEqual(res.data['total_echange'], 0)
        self.assertEqual(res.data['points_en_attente'], 100)

    def test_admin_solde_autre_citoyen(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(f"/api/v1/greenpoints/solde/?citoyen_id={self.citoyen.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['solde'], 300)

    def test_transactions_lister(self):
        self.client.force_authenticate(user=self.citoyen)
        res = self.client.get("/api/v1/greenpoints/transactions/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 2)

        # Filtrer par statut
        res_creditee = self.client.get("/api/v1/greenpoints/transactions/?statut=creditee")
        self.assertEqual(res_creditee.data['count'], 1)
        self.assertEqual(res_creditee.data['results'][0]['points'], 300)

        # Un autre rôle ne doit pas pouvoir parcourir l'historique des citoyens.
        self.client.force_authenticate(user=self.collecteur)
        res_collecteur = self.client.get("/api/v1/greenpoints/transactions/")
        self.assertEqual(res_collecteur.status_code, status.HTTP_200_OK)
        self.assertEqual(res_collecteur.data['count'], 0)

    def test_endpoints_solde_et_echange_refusent_les_roles_non_citoyens(self):
        self.client.force_authenticate(user=self.collecteur)
        res_solde = self.client.get("/api/v1/greenpoints/solde/")
        self.assertEqual(res_solde.status_code, status.HTTP_403_FORBIDDEN)

        res_echange = self.client.post(
            "/api/v1/echanges/",
            {"recompense_id": str(self.recompense.id)},
            format='json',
        )
        self.assertEqual(res_echange.status_code, status.HTTP_403_FORBIDDEN)

    def test_recompenses_gestion_admin(self):
        self.client.force_authenticate(user=self.admin)
        # Créer une récompense
        payload = {
            "nom": "Bouteille de Gaz B6",
            "description": "Recharge gaz domestique 6kg",
            "cout_points": 500,
            "partenaire": "Petroci",
            "actif": True
        }
        res_create = self.client.post("/api/v1/recompenses/", payload, format='json')
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        rec_id = res_create.data['id']

        # Modifier la récompense
        res_patch = self.client.patch(f"/api/v1/recompenses/{rec_id}/", {"cout_points": 450}, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.data['cout_points'], 450)

        # Lister pour citoyen (non-paginé)
        self.client.force_authenticate(user=self.citoyen)
        res_list = self.client.get("/api/v1/recompenses/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_list.data), 2)

    def test_echange_points_workflow(self):
        self.client.force_authenticate(user=self.citoyen)
        # 1. Échange réussi (solde 300 pts, coût 200 pts)
        payload = {"recompense_id": str(self.recompense.id)}
        res_echange = self.client.post("/api/v1/echanges/", payload, format='json')
        self.assertEqual(res_echange.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_echange.data['cout_points'], 200)

        # Nouveau solde = 300 - 200 = 100
        res_solde = self.client.get("/api/v1/greenpoints/solde/")
        self.assertEqual(res_solde.data['solde'], 100)
        self.assertEqual(res_solde.data['total_echange'], 200)

        # 2. Deuxième échange échoue -> solde insuffisant (100 < 200)
        res_fail = self.client.post("/api/v1/echanges/", payload, format='json')
        self.assertEqual(res_fail.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(res_fail.data['code'], "SOLDE_INSUFFISANT")
