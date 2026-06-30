"""Tableau de bord IMPACT (réservé au Super Admin).

Bilan consolidé de l'impact de Map Action sur les incidents **résolus** et/ou
**pris en compte avec au moins une action** (une tâche effectuée). Alimenté par les
analyses IA (`Prediction`) :

  - bénéficiaires DIRECTS (personnes exposées) et INDIRECTS (population potentielle),
    avec ventilation hommes / femmes / enfants ;
  - structures & infrastructures sensibles PROTÉGÉES (écoles, marchés, sources d'eau,
    routes/ponts, bâtiments, maternités, centres de santé, crèches) — filtrables par type ;
  - temps moyen de résolution et taux de résolution ;
  - mobilisation des acteurs (organisations, agents, collaborations) ;
  - contribution citoyenne (signalements reçus / vérifiés / ayant conduit à une action) ;
  - superficie d'impact cumulée (somme des π·rayon² des zones d'impact, en hectares).

Filtres : `?status=resolved|taken_action|all` (défaut `all`) et période
`?filter_type=today|yesterday|last_7_days|last_30_days|this_month|last_month|custom_range`
(`custom_range` → `custom_start` & `custom_end`).
"""
import math
from datetime import timedelta

from django.db.models import Q, Sum
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from ..models import (
    Incident, Prediction, PredictionStatus, IncidentTask, Collaboration,
    IncidentAssignment, ORG_ROLE_FIELD,
    RESOLVED, RESOLVED_DEFINITIVE, DECLARED, TASK_DONE, COLLAB_STATUS_ACCEPTED,
)
from ..roles import is_super_admin, is_org_admin, is_bureau_agent

RESOLVED_ETATS = [RESOLVED, RESOLVED_DEFINITIVE]
# Types d'infrastructures sensibles (clés communes aux colonnes directes et au JSON indirect).
INFRA_TYPES = ['schools', 'health_centers', 'water_points', 'markets',
               'maternities', 'nurseries', 'main_roads_bridges', 'residential_buildings']
_COMPLETED = [PredictionStatus.COMPLETED, PredictionStatus.COMPLETED_WITH_WARNING]


def _apply_period(qs, field, filter_type, custom_start, custom_end):
    """Restreint un queryset sur une fenêtre de date appliquée à `field` (created_at)."""
    now = timezone.now()
    if filter_type == 'today':
        return qs.filter(**{f'{field}__date': now.date()})
    if filter_type == 'yesterday':
        return qs.filter(**{f'{field}__date': now.date() - timedelta(days=1)})
    if filter_type == 'last_7_days':
        return qs.filter(**{f'{field}__date__gte': now.date() - timedelta(days=7)})
    if filter_type == 'last_30_days':
        return qs.filter(**{f'{field}__date__gte': now.date() - timedelta(days=30)})
    if filter_type == 'this_month':
        return qs.filter(**{f'{field}__year': now.year, f'{field}__month': now.month})
    if filter_type == 'last_month':
        lm = now.month - 1 or 12
        ly = now.year if now.month > 1 else now.year - 1
        return qs.filter(**{f'{field}__year': ly, f'{field}__month': lm})
    if filter_type == 'custom_range' and custom_start and custom_end:
        return qs.filter(**{f'{field}__date__range': [custom_start, custom_end]})
    return qs


@extend_schema(
    tags=['Référentiel & Statistiques'],
    operation_id='impact_dashboard',
    summary="Tableau de bord IMPACT",
    description="Agrégats d'impact des incidents résolus / pris en compte avec action. "
                "**Super Admin** : toutes les organisations (vue plateforme, avec performance "
                "des interventions, mobilisation des acteurs et contribution citoyenne). "
                "**Admin / Agent de bureau d'organisation** : uniquement l'impact de SON "
                "organisation (bénéficiaires, infrastructures protégées, superficie cumulée) "
                "— les sections plateforme ne sont pas renvoyées.",
    parameters=[
        OpenApiParameter('status', OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
                         enum=['all', 'resolved', 'taken_action'],
                         description="Portée : résolus, pris en compte AVEC action (≥1 tâche "
                                     "effectuée), ou les deux (défaut all)."),
        OpenApiParameter('filter_type', OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
                         enum=['today', 'yesterday', 'last_7_days', 'last_30_days',
                               'this_month', 'last_month', 'custom_range'],
                         description="Fenêtre de date sur created_at."),
        OpenApiParameter('custom_start', OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False),
        OpenApiParameter('custom_end', OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False),
    ],
    responses={200: OpenApiResponse(description=(
        "{filters, beneficiaries{direct,indirect}, infrastructure_protected{total,by_type,"
        "indirect_by_type}, resolution{avg_resolution_days,resolution_rate}, mobilization, "
        "citizen_contribution, cumulative_impact_area_ha}."
    ))},
)
class ImpactView(APIView):
    """GET /MapApi/impact/ — bilan d'impact.

    Super Admin → vue plateforme (toutes orgs) + sections plateforme.
    Admin / Agent de bureau → impact de SON organisation uniquement (incidents pris
    en charge par son org), sans les sections plateforme.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        is_super = is_super_admin(user)
        org = None
        if not is_super:
            if not (is_org_admin(user) or is_bureau_agent(user)):
                return Response(
                    {"error": "Réservé au super admin et aux admins / agents de bureau d'organisation."},
                    status=status.HTTP_403_FORBIDDEN)
            org = getattr(user, 'organisation_member', None)
            if org is None:
                return Response({"error": "Aucune organisation associée à ce compte."},
                                status=status.HTTP_403_FORBIDDEN)

        p = request.query_params
        statut = (p.get('status') or 'all').lower()
        filter_type = p.get('filter_type') or p.get('period')
        cs, ce = p.get('custom_start'), p.get('custom_end')

        # Base : incidents non supprimés, filtrés par période sur created_at.
        base = _apply_period(
            Incident.objects.filter(is_deleted=False), 'created_at', filter_type, cs, ce)
        # Admin / agent de bureau : restreint à l'impact de SON organisation =
        # incidents pris en charge par son org (taken_by ∈ org).
        if org is not None:
            base = base.filter(taken_by__organisation_member=org)

        # « Avec action » = au moins une tâche effectuée (state=done).
        acted_ids = set(
            IncidentTask.objects.filter(state=TASK_DONE).values_list('incident_id', flat=True))

        resolved_q = Q(etat__in=RESOLVED_ETATS)
        taken_action_q = (~Q(etat__in=RESOLVED_ETATS)
                          & Q(taken_by__isnull=False) & Q(id__in=acted_ids))
        if statut in ('resolved', 'resolu', 'résolu', 'resolus'):
            scope = base.filter(resolved_q)
        elif statut in ('taken_action', 'taken_with_action', 'pris_en_compte', 'action'):
            scope = base.filter(taken_action_q)
        else:  # all / les deux
            scope = base.filter(resolved_q | taken_action_q)
        scope_ids = list(scope.values_list('id', flat=True))

        preds = Prediction.objects.filter(incident_id__in=scope_ids, status__in=_COMPLETED)

        # 1-2) Bénéficiaires DIRECTS (colonnes dédiées).
        d = preds.aggregate(total=Sum('total_population_exposed'), men=Sum('adult_men_exposed'),
                            women=Sum('adult_women_exposed'), children=Sum('children_exposed'))
        direct = {k: int(v or 0) for k, v in d.items()}

        # 1-2) Bénéficiaires INDIRECTS + infra (directe en colonnes, indirecte en JSON)
        #      + superficie d'impact (π·rayon²) — un seul passage sur les prédictions.
        ind = {'total': 0, 'men': 0, 'women': 0, 'children': 0}
        infra_direct = {t: 0 for t in INFRA_TYPES}
        infra_indirect = {t: 0 for t in INFRA_TYPES}
        area_m2 = 0.0
        for pr in preds:
            fr = pr.full_response or {}
            ihi = fr.get('indirect_human_impact') or {}
            ind['total'] += ihi.get('total_population_exposed') or 0
            ind['men'] += ihi.get('adult_men_exposed') or 0
            ind['women'] += ihi.get('adult_women_exposed') or 0
            ind['children'] += ihi.get('children_exposed') or 0
            isd = fr.get('indirect_social_data') or {}
            for t in INFRA_TYPES:
                infra_direct[t] += getattr(pr, t, 0) or 0
                infra_indirect[t] += isd.get(t) or 0
            r = pr.impact_radius_meters or 0
            if r:
                area_m2 += math.pi * (r ** 2)

        # --- Sections communes (super admin ET organisation) : « son impact ». ---
        payload = {
            'filters': {
                'scope': 'organisation' if org is not None else 'platform',
                'organisation': org.name if org is not None else None,
                'status': statut,
                'period': filter_type or 'all',
                'incidents_in_scope': len(scope_ids),
                'incidents_with_prediction': preds.count(),
            },
            'beneficiaries': {
                # DIRECTS = personnes exposées dans l'analyse ; INDIRECTS = population potentielle.
                'direct': direct,
                'indirect': {k: int(v) for k, v in ind.items()},
            },
            'infrastructure_protected': {
                'total': sum(infra_direct.values()),
                'by_type': infra_direct,            # filtrable par type côté front
                'indirect_by_type': infra_indirect,
            },
            # Superficie d'impact cumulée (ha) = Σ (π·rayon² / 10 000) sur le scope.
            'cumulative_impact_area_ha': round(area_m2 / 10000.0, 2),
        }

        # --- Sections PLATEFORME : réservées au Super Admin (non renvoyées à une org). ---
        if not is_super:
            return Response(payload, status=status.HTTP_200_OK)

        # 4) Temps moyen de résolution (jours) : created_at → resolution_end_date.
        durations = []
        for inc in scope.filter(etat__in=RESOLVED_ETATS, resolution_end_date__isnull=False):
            if inc.created_at and inc.resolution_end_date:
                days = (inc.resolution_end_date - inc.created_at.date()).days
                if days >= 0:
                    durations.append(days)
        avg_res_days = round(sum(durations) / len(durations), 1) if durations else None

        # 5) Taux de résolution = résolus / signalés (sur la période).
        reported_total = base.count()
        resolved_total = base.filter(etat__in=RESOLVED_ETATS).count()
        rate = round(resolved_total / reported_total, 4) if reported_total else 0

        # 6) Mobilisation des acteurs (sur le scope).
        orgs = set(
            o for o in scope.values_list('taken_by__organisation_member_id', flat=True) if o)
        collabs = Collaboration.objects.filter(incident_id__in=scope_ids)
        for o in collabs.filter(status=COLLAB_STATUS_ACCEPTED).values_list(
                'user__organisation_member_id', flat=True):
            if o:
                orgs.add(o)
        field_agents = set(
            IncidentAssignment.objects.filter(incident_id__in=scope_ids)
            .values_list('agent_id', flat=True))

        # 7) Contribution citoyenne (sur la période).
        active_citizens = (base.exclude(user_id__org_role=ORG_ROLE_FIELD)
                           .exclude(user_id__isnull=True).values('user_id').distinct().count())

        payload.update({
            'resolution': {
                'avg_resolution_days': avg_res_days,
                'resolution_rate': {
                    'resolved': resolved_total,
                    'reported': reported_total,
                    'rate': rate,
                    'percentage': round(rate * 100, 1),
                },
            },
            'mobilization': {
                'organisations_involved': len(orgs),
                'field_agents_mobilized': len(field_agents),
                'collaborations_created': collabs.count(),
                'incidents_collaborative': scope.filter(take_in_charge_mode__iexact='collaborative').count(),
                'incidents_individual': scope.filter(take_in_charge_mode__iexact='internal').count(),
            },
            'citizen_contribution': {
                # signalements vérifiés = pris en compte par une org (etat ≠ 'declared').
                'reports_received': reported_total,
                'reports_verified': base.exclude(etat=DECLARED).count(),
                'reports_led_to_action': base.filter(id__in=acted_ids).count(),
                'active_citizen_contributors': active_citizens,
            },
        })
        return Response(payload, status=status.HTTP_200_OK)
