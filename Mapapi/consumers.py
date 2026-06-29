"""Consumers WebSocket temps réel.

- NotificationConsumer : /ws/notifications/ — flux des notifications de l'utilisateur
  connecté (qui a fait quoi). Groupe ``notifications_<user_id>``.
- DiscussionConsumer : /ws/incidents/<id>/discussion/ — messages de discussion
  d'un incident en temps réel. Groupe ``discussion_<incident_id>``.
- TaskConsumer : /ws/incidents/<id>/tasks/ — créations/màj de tâches en temps réel.
  Groupe ``tasks_<incident_id>``.

Les serveurs (signals) poussent via channel_layer.group_send(group, {'type': 'broadcast', 'payload': {...}}).
"""
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class _GroupConsumer(AsyncJsonWebsocketConsumer):
    """Base : rejoint un groupe si l'utilisateur est authentifié, relaie les
    messages 'broadcast' tels quels au client."""
    group_name = None

    async def connect(self):
        user = self.scope.get('user')
        if user is None or not getattr(user, 'is_authenticated', False):
            await self.close(code=4401)  # non authentifié
            return
        self.group_name = await self.resolve_group()
        if not self.group_name:
            await self.close(code=4403)  # non autorisé / cible invalide
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def resolve_group(self):
        raise NotImplementedError

    async def broadcast(self, event):
        # event = {'type': 'broadcast', 'payload': {...}}
        await self.send_json(event['payload'])


class NotificationConsumer(_GroupConsumer):
    async def resolve_group(self):
        return f"notifications_{self.scope['user'].id}"


class DiscussionConsumer(_GroupConsumer):
    async def resolve_group(self):
        incident_id = self.scope['url_route']['kwargs'].get('incident_id')
        return f"discussion_{incident_id}" if incident_id else None


class TaskConsumer(_GroupConsumer):
    async def resolve_group(self):
        incident_id = self.scope['url_route']['kwargs'].get('incident_id')
        return f"tasks_{incident_id}" if incident_id else None


class CollaborationConsumer(_GroupConsumer):
    """/ws/collaborations/ — collaborations de l'utilisateur connecté en temps réel
    (onglet collaboration + demandes). Groupe ``collaborations_<user_id>``."""
    async def resolve_group(self):
        return f"collaborations_{self.scope['user'].id}"
