"""Prediction & chat history endpoints."""
import json

from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status, generics
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from ..serializer import *
from .common import CustomPageNumberPagination


@extend_schema_view(get=extend_schema(
    tags=['Prédiction & IA'],
    operation_id='predictions_list',
    summary="Lister toutes les prédictions",
    description="Retourne la liste de toutes les prédictions IA (`Prediction`). "
                "Endpoint public (aucune authentification requise).",
    responses={200: PredictionSerializer(many=True)},
))
class PredictionView(generics.ListAPIView):
    permission_classes = ()
    queryset = Prediction.objects.all()
    serializer_class = PredictionSerializer

def history_list(request):
    histories = ChatHistory.objects.all()  # Retrieve all history records
    data = {"histories": list(histories.values("session_id", "question", "answer"))}
    return JsonResponse(data)

@csrf_exempt  # Disable CSRF token for this view for simplicity
def add_history(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            history = ChatHistory(
                user_id=data['session_id'],
                question=data['question'],
                answer=data['answer']
            )
            history.save()
            return JsonResponse({"message": "History added successfully!"}, status=201)
        except (KeyError, TypeError) as e:
            return JsonResponse({"error": str(e)}, status=400)
    else:
        return HttpResponse(status=405)  # Method Not Allowed


@extend_schema_view(get=extend_schema(
    tags=['Prédiction & IA'],
    operation_id='predictions_retrieve',
    summary="Prédiction(s) par prediction_id",
    description="Retourne la/les prédiction(s) dont le champ `prediction_id` correspond "
                "à l'identifiant fourni (résultat sous forme de liste). Endpoint public.",
    parameters=[
        OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="prediction_id de la prédiction"),
    ],
    responses={200: PredictionSerializer(many=True)},
))
class PredictionViewByID(generics.ListAPIView):
    permission_classes = ()
    serializer_class = PredictionSerializer

    def get_queryset(self):
        prediction_id = self.kwargs['id']
        queryset = Prediction.objects.filter(prediction_id=prediction_id)
        return queryset


@extend_schema_view(get=extend_schema(
    tags=['Prédiction & IA'],
    operation_id='predictions_by_incident',
    summary="Prédictions d'un incident",
    description="Retourne la/les prédiction(s) liée(s) à l'incident dont l'id est fourni "
                "(consommé par le frontend `getIncidentPredictionService`). Endpoint public.",
    parameters=[
        OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="id de l'incident"),
    ],
    responses={200: PredictionSerializer(many=True)},
))
class PredictionViewByIncidentID(generics.ListAPIView):
    permission_classes = ()
    serializer_class = PredictionSerializer

    def get_queryset(self):
        incident_id = self.kwargs['id']
        queryset = Prediction.objects.filter(incident_id=incident_id)
        return queryset


@extend_schema_view(get=extend_schema(
    tags=['Prédiction & IA'],
    operation_id='predictions_chat_history',
    summary="Historique de chat par session",
    description="Retourne l'historique de chat (`ChatHistory`) filtré par `session_id` "
                "(résultat sous forme de liste). Endpoint public.",
    parameters=[
        OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="session_id de la conversation"),
    ],
    responses={200: ChatHistorySerializer(many=True)},
))
class ChatHistoryViewByIncident(generics.ListAPIView):
    permission_classes = ()
    serializer_class = ChatHistorySerializer

    def get_queryset(self):
        session_id = self.kwargs['id']
        queryset = ChatHistory.objects.filter(session_id=session_id)
        return queryset
