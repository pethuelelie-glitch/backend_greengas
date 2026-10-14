from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.comptes.models import Utilisateur, Role
from apps.referentiel.models import Site, Secteur, Bac, StatutSite, StatutBac


class ReferentielEndpointsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.admin = Utilisateur.objects.create_user(
            telephone="+2250100000001",
            nom="Admin",
            password="password123",
            role=Role.ADMINISTRATEUR
        )
        self.citoyen = Utilisateur.objects.create_user(
            telephone="+2250100000002",
            nom="Citoyen",
            password="password123",
            role=Role.CITOYEN
        )

        self.site = Site.objects.create(
            code="DIG-01",
            nom="Site Digesteur",
            statut=StatutSite.NOMINAL,
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
            capacite_kg=Decimal('100.00'),
            statut=StatutBac.ACTIF
        )

    def test_sites_lister_et_modifier(self):
        self.client.force_authenticate(user=self.admin)
        # Lister
        res_list = self.client.get("/api/v1/sites/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_list.data), 1)
        self.assertEqual(res_list.data[0]['code'], "DIG-01")

        # Modifier (passer en maintenance)
        res_patch = self.client.patch(
            f"/api/v1/sites/{self.site.id}/",
            {"statut": "maintenance"},
            format='json'
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.data['statut'], "maintenance")

    def test_secteurs_lister_et_modifier(self):
        self.client.force_authenticate(user=self.admin)
        res_list = self.client.get("/api/v1/secteurs/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_list.data), 1)
        self.assertEqual(res_list.data[0]['code'], "NORD")

    def test_bacs_crud(self):
        self.client.force_authenticate(user=self.admin)
        # 1. Lister
        res_list = self.client.get("/api/v1/bacs/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(res_list.data['count'], 1)

        # 2. Créer un nouveau bac
        payload = {
            "code": "BAC-015",
            "residence": "Résidence Les Palmiers",
            "secteur_id": str(self.secteur.id),
            "nb_foyers_declares": 35,
            "latitude": 5.346000,
            "longitude": -4.013000,
            "tare_kg": 12.5,
            "capacite_kg": 120.0
        }
        res_post = self.client.post("/api/v1/bacs/", payload, format='json')
        self.assertEqual(res_post.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_post.data['code'], "BAC-015")

        # 3. Modifier le bac
        bac_id = res_post.data['id']
        res_patch = self.client.patch(f"/api/v1/bacs/{bac_id}/", {"nb_foyers_declares": 40}, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.data['nb_foyers_declares'], 40)
