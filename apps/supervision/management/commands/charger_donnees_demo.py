import os
import json
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from django.utils.dateparse import parse_datetime, parse_date

from apps.referentiel.models import Site, Secteur, Bac
from apps.comptes.models import Utilisateur
from apps.supervision.models import Parametre
from apps.greenpoints.models import Recompense, GreenPointsTransaction, StatutTransaction
from apps.collecte.models import Tournee, Collecte, Scan
from apps.tri.models import LotTrie
from apps.energie.models import ProductionEnergie, StatutJournee


class Command(BaseCommand):
    help = "Charge le jeu de données de démonstration commun GREENGAS (SIREXE Hackathon 2026)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--fichier',
            type=str,
            default=None,
            help="Chemin vers le fichier JSON des données de démo (par défaut fixtures/donnees_demo.json)"
        )

    def handle(self, *args, **options):
        fixture_path = options['fichier']
        if not fixture_path:
            fixture_path = os.path.join(
                settings.BASE_DIR,
                'apps', 'supervision', 'fixtures', 'donnees_demo.json'
            )

        if not os.path.exists(fixture_path):
            self.stderr.write(self.style.ERROR(f"Fichier introuvable: {fixture_path}"))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(f"Chargement des données de démonstration depuis {fixture_path}..."))

        with open(fixture_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        with transaction.atomic():
            # 1. Sites
            sites_count = 0
            for s in data.get('sites', []):
                Site.objects.update_or_create(
                    id=s['id'],
                    defaults={
                        'code': s['code'],
                        'nom': s['nom'],
                        'statut': s['statut'],
                        'capacite_kg_jour': s['capacite_kg_jour'],
                        'latitude': s['latitude'],
                        'longitude': s['longitude'],
                    }
                )
                sites_count += 1
            self.stdout.write(self.style.SUCCESS(f"  [OK] Sites charges: {sites_count}"))

            # 2. Secteurs
            secteurs_count = 0
            for sec in data.get('secteurs', []):
                Secteur.objects.update_or_create(
                    id=sec['id'],
                    defaults={
                        'code': sec['code'],
                        'nom': sec['nom'],
                        'site_id': sec['site_id'],
                        'site_repli_id': sec.get('site_repli_id'),
                    }
                )
                secteurs_count += 1
            self.stdout.write(self.style.SUCCESS(f"  [OK] Secteurs charges: {secteurs_count}"))

            # 3. Bacs
            bacs_count = 0
            for b in data.get('bacs', []):
                date_derniere = parse_datetime(b['date_derniere_collecte']) if b.get('date_derniere_collecte') else None
                Bac.objects.update_or_create(
                    id=b['id'],
                    defaults={
                        'code': b['code'],
                        'residence': b['residence'],
                        'secteur_id': b['secteur_id'],
                        'nb_foyers_declares': b['nb_foyers_declares'],
                        'latitude': b['latitude'],
                        'longitude': b['longitude'],
                        'tare_kg': b['tare_kg'],
                        'capacite_kg': b['capacite_kg'],
                        'statut': b['statut'],
                        'date_derniere_collecte': date_derniere,
                    }
                )
                bacs_count += 1
            self.stdout.write(self.style.SUCCESS(f"  [OK] Bacs charges: {bacs_count}"))

            # 4. Utilisateurs
            users_count = 0
            for u in data.get('utilisateurs', []):
                bac_id = u.get('bac_id')
                profil = u.get('profil_citoyen') or {}
                if not bac_id and profil:
                    bac_id = profil.get('bac_id')

                statut_val = u.get('statut_validation') or profil.get('statut_validation', 'valide')
                tel_verif = u.get('telephone_verifie', True)
                if 'telephone_verifie' in profil:
                    tel_verif = profil['telephone_verifie']

                role = u.get('role', 'citoyen')
                is_staff = role in ['administrateur', 'collecteur', 'operateur_tri', 'responsable_methanisation']
                is_superuser = role == 'administrateur'

                if Utilisateur.objects.filter(telephone=u['telephone']).exists():
                    user = Utilisateur.objects.get(telephone=u['telephone'])
                    user.nom = u['nom']
                    user.email = u.get('email')
                    user.role = role
                    user.statut_validation = statut_val
                    user.telephone_verifie = tel_verif
                    user.bac_id = bac_id
                    user.is_staff = is_staff
                    if is_superuser:
                        user.is_superuser = True
                    pwd = u.get('mot_de_passe', 'greengas2026')
                    user.set_password(pwd)
                    user.save()
                else:
                    user = Utilisateur.objects.create(
                        id=u['id'],
                        nom=u['nom'],
                        telephone=u['telephone'],
                        email=u.get('email'),
                        role=role,
                        actif=u.get('actif', True),
                        statut_validation=statut_val,
                        telephone_verifie=tel_verif,
                        bac_id=bac_id,
                        is_staff=is_staff,
                        is_superuser=is_superuser,
                    )
                    pwd = u.get('mot_de_passe', 'greengas2026')
                    user.set_password(pwd)
                    user.save()
                users_count += 1
            self.stdout.write(self.style.SUCCESS(f"  [OK] Utilisateurs charges: {users_count}"))

            # 5. Parametres
            params_count = 0
            for p in data.get('parametres', []):
                Parametre.objects.update_or_create(
                    cle=p['cle'],
                    defaults={
                        'valeur': p['valeur'],
                        'unite': p['unite'],
                        'statut': p['statut'],
                        'description': p.get('description', ''),
                        'source': p.get('source'),
                        'date_modification': parse_datetime(p['date_modification']) if p.get('date_modification') else None,
                    }
                )
                params_count += 1
            self.stdout.write(self.style.SUCCESS(f"  [OK] Parametres systeme charges: {params_count}"))

            # 6. Recompenses
            recomp_count = 0
            for r in data.get('recompenses', []):
                Recompense.objects.update_or_create(
                    id=r['id'],
                    defaults={
                        'nom': r['nom'],
                        'description': r['description'],
                        'cout_points': r['cout_points'],
                        'partenaire': r['partenaire'],
                        'actif': r.get('actif', True),
                    }
                )
                recomp_count += 1
            self.stdout.write(self.style.SUCCESS(f"  [OK] Recompenses GreenPoints chargees: {recomp_count}"))

            # 7. Tournees
            tournees_count = 0
            for t in data.get('tournees', []):
                obj, created = Tournee.objects.update_or_create(
                    id=t['id'],
                    defaults={
                        'code': t['code'],
                        'date': parse_date(t['date']),
                        'secteur_id': t['secteur_id'],
                        'site_id': t['site_id'],
                        'motif_affectation': t.get('motif_affectation', 'secteur'),
                        'collecteur_id': t['collecteur_id'],
                        'statut': t['statut'],
                        'niveau_contamination': t.get('niveau_contamination'),
                    }
                )
                if t.get('bac_ids'):
                    obj.bacs.set(t['bac_ids'])
                tournees_count += 1
            self.stdout.write(self.style.SUCCESS(f"  [OK] Tournees de collecte chargees: {tournees_count}"))

            # 8. Collectes
            collectes_count = 0
            for c in data.get('collectes', []):
                Collecte.objects.update_or_create(
                    id=c['id'],
                    defaults={
                        'tournee_id': c['tournee_id'],
                        'bac_id': c['bac_id'],
                        'collecteur_id': c['collecteur_id'],
                        'statut': c['statut'],
                        'poids_brut_kg': c.get('poids_brut_kg'),
                        'tare_kg': c['tare_kg'],
                        'poids_net_kg': c.get('poids_net_kg'),
                        'source': c.get('source'),
                        'scans_valides': c.get('scans_valides'),
                        'kg_par_scan': c.get('kg_par_scan'),
                        'statut_controle': c.get('statut_controle'),
                        'date_pesee': parse_datetime(c['date_pesee']) if c.get('date_pesee') else None,
                        'date_validation': parse_datetime(c['date_validation']) if c.get('date_validation') else None,
                    }
                )
                if c.get('date_ouverture'):
                    Collecte.objects.filter(id=c['id']).update(date_ouverture=parse_datetime(c['date_ouverture']))
                collectes_count += 1
            self.stdout.write(self.style.SUCCESS(f"  [OK] Collectes chargees: {collectes_count}"))

            # 9. Lots
            lots_count = 0
            for l in data.get('lots', []):
                LotTrie.objects.update_or_create(
                    id=l['id'],
                    defaults={
                        'code_lot': l['code_lot'],
                        'tournee_id': l['tournee_id'],
                        'categorie': l['categorie'],
                        'poids_kg': l['poids_kg'],
                        'part_pct': l['part_pct'],
                        'destination': l['destination'],
                        'site_id': l.get('site_id'),
                    }
                )
                lots_count += 1
            self.stdout.write(self.style.SUCCESS(f"  [OK] Lots de matiere triee charges: {lots_count}"))

            # 10. Scans
            scans_count = 0
            for s in data.get('scans', []):
                Scan.objects.update_or_create(
                    id=s['id'],
                    defaults={
                        'citoyen_id': s['citoyen_id'],
                        'bac_id': s['bac_id'],
                        'latitude': s.get('latitude'),
                        'longitude': s.get('longitude'),
                        'distance_m': s.get('distance_m'),
                        'statut': s['statut'],
                        'compte': s.get('compte', True),
                    }
                )
                if s.get('horodatage'):
                    Scan.objects.filter(id=s['id']).update(horodatage=parse_datetime(s['horodatage']))
                scans_count += 1
            self.stdout.write(self.style.SUCCESS(f"  [OK] Scans citoyens charges: {scans_count}"))

            # 11. Productions Énergie initiales pour la journée de travail (12/09/2026)
            dig1 = Site.objects.filter(code='DIG-01').first()
            dig2 = Site.objects.filter(code='DIG-02').first()
            dig3 = Site.objects.filter(code='DIG-03').first()

            if dig1:
                ProductionEnergie.objects.update_or_create(
                    site=dig1,
                    date=parse_date('2026-09-12'),
                    defaults={
                        'statut_journee': StatutJournee.OUVERTE,
                        'poids_organique_recu_kg': Decimal('0'),
                        'biogaz_attendu_m3': Decimal('0'),
                    }
                )
            if dig2:
                ProductionEnergie.objects.update_or_create(
                    site=dig2,
                    date=parse_date('2026-09-12'),
                    defaults={
                        'statut_journee': StatutJournee.OUVERTE,
                        'poids_organique_recu_kg': Decimal('0'),
                        'biogaz_attendu_m3': Decimal('0'),
                    }
                )
            if dig3:
                ProductionEnergie.objects.update_or_create(
                    site=dig3,
                    date=parse_date('2026-09-12'),
                    defaults={
                        'statut_journee': StatutJournee.OUVERTE,
                        'poids_organique_recu_kg': Decimal('320.00'),
                        'biogaz_attendu_m3': Decimal('32.00'),
                        'biogaz_mesure_m3': Decimal('32.00'),
                        'ch4_pct': Decimal('62.5'),
                        'temperature_c': Decimal('37.5'),
                        'ph': Decimal('7.2'),
                        'ecart_pct': Decimal('0.0'),
                        'electricite_kwh': Decimal('54.40'),
                        'chaleur_kwh': Decimal('108.80'),
                        'digestat_kg': Decimal('160.00'),
                        'foyers_equivalents': Decimal('11.10'),
                        'foyers_cuisson': Decimal('21.30'),
                        'statuts_donnees': {
                            'biogaz_mesure_m3': 'mesure',
                            'electricite_kwh': 'estime',
                            'chaleur_kwh': 'estime',
                        }
                    }
                )
            self.stdout.write(self.style.SUCCESS("  [OK] Productions d'energie initialisees (DIG-01, DIG-02, DIG-03)"))

            # 12. GreenPoints Transactions initiales pour démo des citoyens
            # Répartir des points aux citoyens qui ont scanné les tournées triées
            awa = Utilisateur.objects.filter(telephone='+2250701020304').first()
            koffi = Utilisateur.objects.filter(telephone='+2250701020305').first()
            bac14 = Bac.objects.filter(code='BAC-014').first()
            tournee_triee = Tournee.objects.filter(statut='triee').first()

            if awa and koffi and bac14 and tournee_triee:
                collecte_bac14 = tournee_triee.collectes.filter(bac=bac14).first()
                if not collecte_bac14:
                    collecte_bac14 = Collecte.objects.filter(bac=bac14).first()

                if collecte_bac14:
                    GreenPointsTransaction.objects.update_or_create(
                        citoyen=awa,
                        bac=bac14,
                        tournee=collecte_bac14.tournee,
                        collecte=collecte_bac14,
                        defaults={
                            'scans_citoyen': 12,
                            'scans_bac': 24,
                            'poids_attribue_kg': Decimal('17.00'),
                            'valeur_kg': Decimal('8.5400'),
                            'coef_qualite': Decimal('1.00'),
                            'points': 145,
                            'statut': StatutTransaction.CREDITEE,
                        }
                    )
                    GreenPointsTransaction.objects.update_or_create(
                        citoyen=koffi,
                        bac=bac14,
                        tournee=collecte_bac14.tournee,
                        collecte=collecte_bac14,
                        defaults={
                            'scans_citoyen': 10,
                            'scans_bac': 24,
                            'poids_attribue_kg': Decimal('14.16'),
                            'valeur_kg': Decimal('8.5400'),
                            'coef_qualite': Decimal('1.00'),
                            'points': 120,
                            'statut': StatutTransaction.CREDITEE,
                        }
                    )
                    self.stdout.write(self.style.SUCCESS("  [OK] Transactions GreenPoints initialisees pour les citoyens de test"))

            # 13. Notifications initiales de démonstration (Contrat 1.4.0)
            from apps.supervision.models import Notification, TypeNotification, NiveauNotification
            from apps.comptes.models import Role
            date_notif = parse_datetime('2026-09-12T09:00:00Z')

            operateurs_tri = Utilisateur.objects.filter(role=Role.OPERATEUR_TRI, actif=True, statut_validation='valide')
            trn1 = Tournee.objects.filter(code='TRN-0912-01').first()
            trn2 = Tournee.objects.filter(code='TRN-0912-02').first()
            admins = Utilisateur.objects.filter(role=Role.ADMINISTRATEUR, actif=True)
            ibrahim = Utilisateur.objects.filter(telephone='+2250700000008').first()
            bac22 = Bac.objects.filter(code='BAC-022').first()
            coll_bac22 = Collecte.objects.filter(bac__code='BAC-022').order_by('-date_ouverture').first()

            # Opérateurs de tri actifs (Aya) : tournee_a_trier pour TRN-0912-01 et TRN-0912-02
            for op in operateurs_tri:
                if trn1:
                    Notification.objects.update_or_create(
                        destinataire=op,
                        type=TypeNotification.TOURNEE_A_TRIER,
                        objet_id=trn1.id,
                        defaults={
                            'niveau': NiveauNotification.INFO,
                            'titre': "Tournée à trier",
                            'message': f"{trn1.code} ({trn1.secteur.code}, 500 kg) attend son tri.",
                            'objet_type': 'tournee',
                            'lue': False,
                            'date_creation': date_notif
                        }
                    )
                if trn2:
                    Notification.objects.update_or_create(
                        destinataire=op,
                        type=TypeNotification.TOURNEE_A_TRIER,
                        objet_id=trn2.id,
                        defaults={
                            'niveau': NiveauNotification.INFO,
                            'titre': "Tournée à trier",
                            'message': f"{trn2.code} ({trn2.secteur.code}, 400 kg) attend son tri.",
                            'objet_type': 'tournee',
                            'lue': False,
                            'date_creation': date_notif
                        }
                    )

            from apps.comptes.utils import is_validation_personnel_active
            val_active = is_validation_personnel_active()

            # Administrateurs : compte_a_valider, collecte_a_verifier, bac_surinscrit
            if not val_active and ibrahim:
                Notification.objects.filter(type=TypeNotification.COMPTE_A_VALIDER, objet_id=ibrahim.id).delete()

            for adm in admins:
                if ibrahim and val_active:
                    Notification.objects.update_or_create(
                        destinataire=adm,
                        type=TypeNotification.COMPTE_A_VALIDER,
                        objet_id=ibrahim.id,
                        defaults={
                            'niveau': NiveauNotification.ATTENTION,
                            'titre': "Compte à valider",
                            'message': f"{ibrahim.nom} demande un accès opérateur de tri.",
                            'objet_type': 'utilisateur',
                            'lue': False,
                            'date_creation': date_notif
                        }
                    )
                if coll_bac22:
                    Notification.objects.update_or_create(
                        destinataire=adm,
                        type=TypeNotification.COLLECTE_A_VERIFIER,
                        objet_id=coll_bac22.id,
                        defaults={
                            'niveau': NiveauNotification.ATTENTION,
                            'titre': "Collecte à vérifier",
                            'message': "BAC-022 : 2 kg pour 40 scans (0,05 kg/scan).",
                            'objet_type': 'collecte',
                            'lue': False,
                            'date_creation': date_notif
                        }
                    )
                if bac22:
                    Notification.objects.update_or_create(
                        destinataire=adm,
                        type=TypeNotification.BAC_SURINSCRIT,
                        objet_id=bac22.id,
                        defaults={
                            'niveau': NiveauNotification.INFO,
                            'titre': "Bac surinscrit",
                            'message': "BAC-022 : 5 comptes pour 4 foyers.",
                            'objet_type': 'bac',
                            'lue': False,
                            'date_creation': date_notif
                        }
                    )

            self.stdout.write(self.style.SUCCESS("  [OK] Notifications initiales de demonstration creees"))

        self.stdout.write(self.style.SUCCESS("\n[SUCCES] Toutes les donnees de demonstration ont ete chargees avec succes !"))
