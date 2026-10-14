from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.comptes.models import Utilisateur, Role
from apps.referentiel.models import Site
from apps.energie.models import (
    ProductionEnergie,
    Alerte,
    StatutJournee,
    DestinationDigestat,
    TypeAlerte,
    StatutAlerte,
)
from apps.supervision.models import JournalAudit, TypeObjet


class EnergieEndpointsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Utilisateurs de test
        self.admin_user = Utilisateur.objects.create_user(
            telephone="+2250100000001",
            nom="Admin Test",
            password="password123",
            role=Role.ADMINISTRATEUR
        )
        self.resp_metha = Utilisateur.objects.create_user(
            telephone="+2250100000002",
            nom="Resp Méthanisation",
            password="password123",
            role=Role.RESPONSABLE_METHANISATION
        )
        self.capteur_user = Utilisateur.objects.create_user(
            telephone="+2250100000003",
            nom="Capteur IoT",
            password="password123",
            role=Role.CAPTEUR
        )
        self.citoyen_user = Utilisateur.objects.create_user(
            telephone="+2250100000004",
            nom="Citoyen Test",
            password="password123",
            role=Role.CITOYEN
        )

        # Site de test
        self.site = Site.objects.create(
            code="DIG-01",
            nom="Digesteur Central",
            statut="nominal",
            capacite_kg_jour=1000,
            latitude=5.345,
            longitude=-4.012
        )

        self.site2 = Site.objects.create(
            code="DIG-02",
            nom="Digesteur Est",
            statut="nominal",
            capacite_kg_jour=800,
            latitude=5.350,
            longitude=-4.000
        )

        # Production de test
        self.prod = ProductionEnergie.objects.create(
            site=self.site,
            date=date(2026, 9, 12),
            statut_journee=StatutJournee.OUVERTE,
            poids_organique_recu_kg=Decimal('320.00'),
            biogaz_attendu_m3=Decimal('32.00')
        )

    def test_productions_list(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get('/api/v1/productions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['code_site'], 'DIG-01')

    def test_productions_refusees_aux_citoyens(self):
        self.client.force_authenticate(user=self.citoyen_user)
        response = self.client.get('/api/v1/productions/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response_globale = self.client.get('/api/v1/productions/globale/?date=2026-09-12')
        self.assertEqual(response_globale.status_code, status.HTTP_403_FORBIDDEN)

    def test_productions_list_filters(self):
        self.client.force_authenticate(user=self.admin_user)
        # Filtrer par site_id
        res = self.client.get(f'/api/v1/productions/?site_id={self.site.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data['results']), 1)

        res_autre = self.client.get(f'/api/v1/productions/?site_id={self.site2.id}')
        self.assertEqual(len(res_autre.data['results']), 0)

        # Filtrer par date
        res_date = self.client.get('/api/v1/productions/?date_debut=2026-09-01&date_fin=2026-09-30')
        self.assertEqual(len(res_date.data['results']), 1)

    def test_productions_globale(self):
        self.client.force_authenticate(user=self.admin_user)
        # Créer une 2ème production sur site2 même date
        ProductionEnergie.objects.create(
            site=self.site2,
            date=date(2026, 9, 12),
            poids_organique_recu_kg=Decimal('200.00'),
            biogaz_attendu_m3=Decimal('20.00'),
            biogaz_mesure_m3=Decimal('18.00'),
            electricite_kwh=Decimal('30.60'),
            chaleur_kwh=Decimal('61.20'),
            digestat_kg=Decimal('100.00'),
            foyers_equivalents=Decimal('6.25')
        )

        response = self.client.get('/api/v1/productions/globale/?date=2026-09-12')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['date'], '2026-09-12')
        self.assertEqual(response.data['nb_sites'], 2)
        self.assertEqual(Decimal(str(response.data['poids_organique_recu_kg'])), Decimal('520.00'))
        self.assertEqual(Decimal(str(response.data['biogaz_attendu_m3'])), Decimal('52.00'))
        self.assertEqual(len(response.data['par_site']), 2)

    def test_productions_detail(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(f'/api/v1/productions/{self.prod.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], str(self.prod.id))
        self.assertEqual(response.data['code_site'], 'DIG-01')

    def test_productions_cloturer(self):
        self.client.force_authenticate(user=self.resp_metha)
        response = self.client.post(
            f'/api/v1/productions/{self.prod.id}/cloturer/',
            {'destination_digestat': 'vente_agricole'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.prod.refresh_from_db()
        self.assertEqual(self.prod.statut_journee, StatutJournee.CLOTUREE)
        self.assertEqual(self.prod.destination_digestat, 'vente_agricole')

        # Clôturer une journée déjà clôturée renvoie 422 JOURNEE_CLOTUREE
        res_closed = self.client.post(
            f'/api/v1/productions/{self.prod.id}/cloturer/',
            {'destination_digestat': 'stockage'},
            format='json'
        )
        self.assertEqual(res_closed.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(res_closed.data['code'], 'JOURNEE_CLOTUREE')

    def test_site_mesures_nominal(self):
        self.client.force_authenticate(user=self.capteur_user)
        # biogaz attendu = 32.0. Si mesure = 30.0 -> ecart = (30-32)/32 = -6.25% (|ecart| < 20%)
        # ch4 = 60% (> 50%)
        payload = {
            'date': '2026-09-12',
            'biogaz_mesure_m3': 30.0,
            'ch4_pct': 60.0,
            'temperature_c': 37.0,
            'ph': 7.2,
            'source': 'capteur'
        }
        response = self.client.post(
            f'/api/v1/sites/{self.site.id}/mesures/',
            payload,
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.prod.refresh_from_db()
        self.assertEqual(self.prod.biogaz_mesure_m3, Decimal('30.00'))
        self.assertEqual(self.prod.ch4_pct, Decimal('60.00'))
        # electricite = 30 * 1.7 = 51.0
        self.assertEqual(self.prod.electricite_kwh, Decimal('51.00'))
        # chaleur = 30 * 3.4 = 102.0
        self.assertEqual(self.prod.chaleur_kwh, Decimal('102.00'))
        # digestat = 320 * 0.5 = 160.0
        self.assertEqual(self.prod.digestat_kg, Decimal('160.00'))
        # foyers = 51 * 365 / 1785 = 10.43
        self.assertEqual(self.prod.foyers_equivalents, Decimal('10.43'))
        # Pas d'alerte
        self.assertEqual(Alerte.objects.filter(site=self.site).count(), 0)
        # Journal d'audit créé
        self.assertTrue(JournalAudit.objects.filter(action="site.mesures").exists())

    def test_site_mesures_declenche_alerte(self):
        self.client.force_authenticate(user=self.capteur_user)
        # biogaz attendu = 32.0. Si mesure = 22.4 -> ecart = (22.4 - 32)/32 = -30.0% (|ecart| >= 20%)
        # ch4 = 45.0% (< 50%) -> Déclenche les 2 alertes !
        payload = {
            'date': '2026-09-12',
            'biogaz_mesure_m3': 22.4,
            'ch4_pct': 45.0,
            'temperature_c': 36.2,
            'ph': 7.1,
            'source': 'simule'
        }
        response = self.client.post(
            f'/api/v1/sites/{self.site.id}/mesures/',
            payload,
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(response.data['ecart_pct'])), Decimal('-30.0'))
        self.assertEqual(Decimal(str(response.data['electricite_kwh'])), Decimal('38.08'))
        self.assertEqual(Decimal(str(response.data['chaleur_kwh'])), Decimal('76.16'))
        self.assertEqual(Decimal(str(response.data['digestat_kg'])), Decimal('160.00'))

        # Deux alertes créées
        self.assertEqual(Alerte.objects.filter(site=self.site, statut=StatutAlerte.OUVERTE).count(), 2)
        self.site.refresh_from_db()
        self.assertEqual(self.site.statut, 'alerte')

    def test_alertes_list_and_resoudre(self):
        alerte = Alerte.objects.create(
            site=self.site,
            type=TypeAlerte.PRODUCTION,
            statut=StatutAlerte.OUVERTE,
            valeur_attendue=Decimal('32.00'),
            valeur_mesuree=Decimal('22.40'),
            ecart_pct=Decimal('-30.0'),
            description="Production de biogaz inférieure de 30 % à l'attendu",
            nb_occurrences=1
        )
        self.site.statut = 'alerte'
        self.site.save()

        self.client.force_authenticate(user=self.resp_metha)
        # Lister
        res_list = self.client.get('/api/v1/alertes/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_list.data['results']), 1)
        self.assertEqual(res_list.data['results'][0]['code_site'], 'DIG-01')

        # Résoudre
        res_resoudre = self.client.post(
            f'/api/v1/alertes/{alerte.id}/resoudre/',
            {'commentaire': 'Correction apportée au niveau du réacteur'},
            format='json'
        )
        self.assertEqual(res_resoudre.status_code, status.HTTP_200_OK)
        alerte.refresh_from_db()
        self.assertEqual(alerte.statut, StatutAlerte.RESOLUE)
        self.assertEqual(alerte.commentaire_resolution, 'Correction apportée au niveau du réacteur')
        self.site.refresh_from_db()
        self.assertEqual(self.site.statut, 'nominal')

        # Déjà résolue -> 422 ALERTE_DEJA_RESOLUE
        res_again = self.client.post(
            f'/api/v1/alertes/{alerte.id}/resoudre/',
            {'commentaire': 'Encore une fois'},
            format='json'
        )
        self.assertEqual(res_again.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

        self.client.force_authenticate(user=self.citoyen_user)
        res_citoyen = self.client.get('/api/v1/alertes/')
        self.assertEqual(res_citoyen.status_code, status.HTTP_403_FORBIDDEN)
