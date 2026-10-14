from decimal import Decimal
from datetime import date
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.comptes.models import Utilisateur, Role, StatutValidation
from apps.referentiel.models import Site, Secteur, Bac
from apps.collecte.models import Tournee, StatutTournee, Collecte, StatutCollecte, StatutControle
from apps.supervision.models import Parametre, JournalAudit, TypeObjet


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
