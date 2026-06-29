"""Notification & user-action endpoints."""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema, extend_schema_view

from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from ..serializer import *
from .common import CustomPageNumberPagination, NotificationPagination


@extend_schema_view(
    list=extend_schema(
        tags=['Notifications'],
        operation_id='notifications_list',
        summary='Mes notifications',
        description=(
            "Toutes les notifications de l'utilisateur connecté, **plus récentes "
            "d'abord**, paginées (20/page, `?page=&page_size=`). Chaque notification "
            "porte un champ `link` (cible de redirection au clic). Filtre `?read=true|false` "
            "(ex. `?read=false` pour les non lues → `count` = nombre de non lues). "
            "Authentification requise."
        ),
        parameters=[
            OpenApiParameter('read', OpenApiTypes.BOOL, OpenApiParameter.QUERY,
                             description="Filtre lues/non lues (true|false)."),
        ],
        responses={200: NotificationSerializer(many=True)},
    )
)
class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NotificationPagination

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user).order_by('-created_at')
        read = self.request.query_params.get('read')
        if read is not None:
            qs = qs.filter(read=(str(read).lower() in ('1', 'true', 'yes')))
        return qs


@extend_schema_view(
    list=extend_schema(
        tags=['Notifications'],
        operation_id='user_actions_list',
        summary='Mes actions (journal)',
        description="Journal des actions de l'utilisateur connecté. Authentification requise.",
        responses={200: UserActionSerializer(many=True)},
    )
)
class UserActionView(viewsets.ModelViewSet):
    queryset = UserAction.objects.all()
    serializer_class = UserActionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
