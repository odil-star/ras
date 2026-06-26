from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import (
    RegisterView,
    LogoutView,
    MeView,
    ExpenseListCreateView,
    ExpenseDetailView,
    IncomeListCreateView,
    IncomeDetailView,
)
from .credit_views import CreditListCreateView, CreditDetailView, CreditPayView
from .analytics_views import (
    ForecastView,
    CategoryAnalysisView,
    AnomalyListView,
    AnomalyDismissView,
    SavingsTimelineView,
    RecommendationsView,
    FeedbackView,
    CategoryCorrectionView,
    MonthlySnapshotListView,
    SaveSnapshotView,
    SuggestCategoryView,
)

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────────────────
    path('register/',       RegisterView.as_view(),         name='register'),
    path('login/',          TokenObtainPairView.as_view(),  name='login'),
    path('login/refresh/',  TokenRefreshView.as_view(),     name='token_refresh'),
    path('logout/',         LogoutView.as_view(),            name='logout'),
    path('me/',             MeView.as_view(),                name='me'),

    # ── Expenses ──────────────────────────────────────────────────────────────
    path('expenses/',           ExpenseListCreateView.as_view(), name='expense-list'),
    path('expenses/<int:pk>/',  ExpenseDetailView.as_view(),     name='expense-detail'),

    # ── Income ────────────────────────────────────────────────────────────────
    path('incomes/',            IncomeListCreateView.as_view(),  name='income-list'),
    path('incomes/<int:pk>/',   IncomeDetailView.as_view(),      name='income-detail'),

    # ── Credits ───────────────────────────────────────────────────────────────
    path('credits/',                    CreditListCreateView.as_view(), name='credit-list'),
    path('credits/<int:pk>/',          CreditDetailView.as_view(),     name='credit-detail'),
    path('credits/<int:pk>/pay/',      CreditPayView.as_view(),        name='credit-pay'),

    # ── Analytics ─────────────────────────────────────────────────────────────
    path('analytics/forecast/',              ForecastView.as_view(),           name='analytics-forecast'),
    path('analytics/categories/',            CategoryAnalysisView.as_view(),   name='analytics-categories'),
    path('analytics/anomalies/',             AnomalyListView.as_view(),        name='analytics-anomalies'),
    path('analytics/anomalies/<int:pk>/dismiss/', AnomalyDismissView.as_view(), name='analytics-anomaly-dismiss'),
    path('analytics/savings/',               SavingsTimelineView.as_view(),    name='analytics-savings'),
    path('analytics/recommendations/',       RecommendationsView.as_view(),    name='analytics-recommendations'),
    path('analytics/feedback/',              FeedbackView.as_view(),           name='analytics-feedback'),
    path('analytics/corrections/',           CategoryCorrectionView.as_view(), name='analytics-corrections'),
    path('analytics/snapshots/',             MonthlySnapshotListView.as_view(),name='analytics-snapshots'),
    path('analytics/snapshots/save/',        SaveSnapshotView.as_view(),       name='analytics-snapshots-save'),
    path('analytics/suggest-category/',      SuggestCategoryView.as_view(),    name='analytics-suggest-category'),
]
