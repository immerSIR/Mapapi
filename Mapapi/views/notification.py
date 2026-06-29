"""Notification & user-action endpoints."""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema, extend_schema_view

from ..serializer import *
from .common import CustomPageNumberPagination


@extend_schema_view(
    list=extend_schema(
        tags=['Notifications'],
        operation_id='notifications_list',
        summary='Mes notifications en attente',
        description=(
            "Notifications de l'utilisateur connecté liées à une collaboration "
            "en attente (`colaboration.status='pending'`). Authentification requise."
        ),
        responses={200: NotificationSerializer(many=True)},
    )
)
class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Notification.objects.filter(user=user, colaboration__status='pending')


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
