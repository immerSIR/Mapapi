"""Routes WebSocket (temps réel)."""
from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path('ws/notifications/', consumers.NotificationConsumer.as_asgi()),
    path('ws/incidents/<int:incident_id>/discussion/', consumers.DiscussionConsumer.as_asgi()),
    path('ws/incidents/<int:incident_id>/tasks/', consumers.TaskConsumer.as_asgi()),
]
