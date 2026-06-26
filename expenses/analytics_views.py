"""
Analytics API Views.

Endpoints:
  GET  /api/analytics/forecast/        — monthly forecast + accuracy
  GET  /api/analytics/categories/      — category breakdown with MoM
  GET  /api/analytics/anomalies/       — detected anomalies
  POST /api/analytics/anomalies/<id>/dismiss/ — dismiss anomaly
  GET  /api/analytics/savings/         — 6-month savings timeline
  GET  /api/analytics/recommendations/ — adaptive recommendations
  POST /api/analytics/feedback/        — submit 👍/👎 on recommendation
  POST /api/analytics/corrections/     — submit category correction (learning)
  GET  /api/analytics/snapshots/       — monthly snapshots history
"""

import logging

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .analytics_service import AnalyticsService, ANALYTICS_AVAILABLE
from .analytics_serializers import (
    AnomalyRecordSerializer,
    CategoryCorrectionSerializer,
    InsightFeedbackSerializer,
    MonthlySnapshotSerializer,
)
from .models import AnomalyRecord, CategoryCorrection, Expense, MonthlySnapshot, UserInsightFeedback

logger = logging.getLogger(__name__)


# ── Helper ────────────────────────────────────────────────────────────────────

def _svc(request) -> AnalyticsService:
    return AnalyticsService(request.user)


def _server_error(exc: Exception, context: str) -> Response:
    """Log exception and return a safe JSON 500 response."""
    logger.exception("Analytics error in %s: %s", context, exc)
    return Response(
        {'detail': 'Ошибка обработки данных. Попробуйте позже.'},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _unavailable_response() -> Response:
    return Response(
        {'error': 'Аналитика недоступна: numpy/pandas/scikit-learn не установлены'},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


# ── Forecast ──────────────────────────────────────────────────────────────────

class ForecastView(APIView):
    """GET — monthly forecast with linear regression + accuracy estimate."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not ANALYTICS_AVAILABLE:
            return _unavailable_response()
        try:
            data = _svc(request).calculate_monthly_forecast()
            return Response(data)
        except Exception as exc:
            return _server_error(exc, 'ForecastView')


# ── Category analysis ─────────────────────────────────────────────────────────

class CategoryAnalysisView(APIView):
    """GET — per-category breakdown with MoM comparison."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not ANALYTICS_AVAILABLE:
            return _unavailable_response()
        try:
            data = _svc(request).get_category_analysis()
            return Response({'categories': data})
        except Exception as exc:
            return _server_error(exc, 'CategoryAnalysisView')


# ── Anomalies ─────────────────────────────────────────────────────────────────

class AnomalyListView(APIView):
    """GET  — run anomaly detection; return results (persists to DB)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not ANALYTICS_AVAILABLE:
            return _unavailable_response()
        try:
            z = getattr(settings, 'ANALYTICS_ANOMALY_Z_THRESHOLD', 2.0)
            data = _svc(request).detect_anomalies(z_threshold=z)
            return Response({'anomalies': data})
        except Exception as exc:
            return _server_error(exc, 'AnomalyListView')


class AnomalyDismissView(APIView):
    """POST — mark an AnomalyRecord as dismissed (user says it's OK)."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        try:
            record = AnomalyRecord.objects.get(pk=pk, user=request.user)
        except AnomalyRecord.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        try:
            record.is_dismissed = True
            record.save(update_fields=['is_dismissed'])
            return Response({'status': 'dismissed'})
        except Exception as exc:
            return _server_error(exc, 'AnomalyDismissView')


# ── Savings timeline ──────────────────────────────────────────────────────────

class SavingsTimelineView(APIView):
    """GET — last 6 months income vs expenses vs savings."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not ANALYTICS_AVAILABLE:
            return _unavailable_response()
        try:
            months = int(request.query_params.get('months', 6))
            months = min(max(months, 2), 24)
            data   = _svc(request).calculate_savings_timeline(months=months)
            return Response({'timeline': data})
        except Exception as exc:
            return _server_error(exc, 'SavingsTimelineView')


# ── Recommendations ───────────────────────────────────────────────────────────

class RecommendationsView(APIView):
    """GET — adaptive personalised recommendations."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not ANALYTICS_AVAILABLE:
            return _unavailable_response()
        try:
            recs = _svc(request).generate_recommendations()
            return Response({'recommendations': recs})
        except Exception as exc:
            return _server_error(exc, 'RecommendationsView')


# ── Feedback (self-learning) ──────────────────────────────────────────────────

class FeedbackView(APIView):
    """POST — submit 👍 (rating=1) or 👎 (rating=-1) on a recommendation."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = InsightFeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return _server_error(exc, 'FeedbackView.post')

    def get(self, request):
        try:
            qs = UserInsightFeedback.objects.filter(user=request.user).order_by('-created_at')[:50]
            return Response(InsightFeedbackSerializer(qs, many=True).data)
        except Exception as exc:
            return _server_error(exc, 'FeedbackView.get')


# ── Category corrections (self-learning) ──────────────────────────────────────

class CategoryCorrectionView(APIView):
    """
    POST — user corrects a category; system learns for future suggestions.
    Also updates the Expense record itself.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        expense_id = request.data.get('expense_id')
        new_cat    = request.data.get('corrected_category')

        if not expense_id or not new_cat:
            return Response(
                {'detail': 'expense_id and corrected_category are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            expense = Expense.objects.get(pk=expense_id, user=request.user)
        except Expense.DoesNotExist:
            return Response({'detail': 'Expense not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            old_cat = expense.category
            if old_cat == new_cat:
                return Response({'detail': 'Category unchanged'})

            expense.category = new_cat
            expense.save(update_fields=['category'])

            correction, created = CategoryCorrection.objects.get_or_create(
                user=request.user,
                expense=expense,
                defaults={
                    'original_category':  old_cat,
                    'corrected_category': new_cat,
                    'expense_title':      expense.title,
                },
            )
            if not created:
                correction.corrected_category = new_cat
                correction.save(update_fields=['corrected_category'])

            return Response({
                'expense_id':          expense.id,
                'original_category':   old_cat,
                'corrected_category':  new_cat,
                'learned':             True,
            })
        except Exception as exc:
            return _server_error(exc, 'CategoryCorrectionView')


# ── Monthly snapshots ──────────────────────────────────────────────────────────

class MonthlySnapshotListView(APIView):
    """GET — list historical monthly snapshots."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            qs = MonthlySnapshot.objects.filter(user=request.user).order_by('-year', '-month')[:12]
            return Response(MonthlySnapshotSerializer(qs, many=True).data)
        except Exception as exc:
            return _server_error(exc, 'MonthlySnapshotListView')


class SaveSnapshotView(APIView):
    """POST — manually trigger a monthly snapshot save for year+month."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not ANALYTICS_AVAILABLE:
            return _unavailable_response()
        year  = request.data.get('year')
        month = request.data.get('month')
        if not year or not month:
            return Response({'detail': 'year and month required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            _svc(request).save_monthly_snapshot(int(year), int(month))
            return Response({'status': 'saved', 'year': year, 'month': month})
        except Exception as exc:
            return _server_error(exc, 'SaveSnapshotView')


# ── Category suggestion (self-learning) ───────────────────────────────────────

class SuggestCategoryView(APIView):
    """GET ?title=... — suggest category based on learned corrections."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not ANALYTICS_AVAILABLE:
            return _unavailable_response()
        try:
            title = request.query_params.get('title', '')
            if not title:
                return Response({'suggestion': None})
            suggestion = _svc(request).suggest_category(title)
            return Response({'suggestion': suggestion, 'title': title})
        except Exception as exc:
            return _server_error(exc, 'SuggestCategoryView')
