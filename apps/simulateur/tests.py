from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.comptes.models import Utilisateur, Role
from apps.referentiel.models import Site
from apps.simulateur.models import ScenarioSimulation


class SimulateurEndpointsTestCase(TestCase):
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
            statut="nominal",
            capacite_kg_jour=1000,
            latitude=Decimal('5.345000'),
            longitude=Decimal('-4.012000')
        )

    def test_scenarios_simulation_crud(self):
        # 1. Citoyen interdit
        self.client.force_authenticate(user=self.citoyen)
        res_citoyen = self.client.get("/api/v1/simulation/scenarios/")
        self.assertEqual(res_citoyen.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Admin liste (vide au départ)
        self.client.force_authenticate(user=self.admin)
        res_list = self.client.get("/api/v1/simulation/scenarios/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_list.data), 0)

        # 3. Admin crée / force un scénario (facteur 0.70)
        payload = {
            "site_id": str(self.site.id),
            "facteur_mesure": 0.70
        }
        res_post = self.client.post("/api/v1/simulation/scenarios/", payload, format='json')
        self.assertEqual(res_post.status_code, status.HTTP_201_CREATED)
        self.assertEqual(float(res_post.data['facteur_mesure']), 0.70)

        # 4. Admin liste (1 scénario)
        res_list2 = self.client.get("/api/v1/simulation/scenarios/")
        self.assertEqual(len(res_list2.data), 1)

        # 5. Admin supprime le scénario
        res_del = self.client.delete(f"/api/v1/simulation/scenarios/{self.site.id}/")
        self.assertEqual(res_del.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(ScenarioSimulation.objects.count(), 0)
