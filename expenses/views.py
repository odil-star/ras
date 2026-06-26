from django.contrib.auth.models import User
from django.db.models import Sum
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django_filters.rest_framework import DjangoFilterBackend
from .models import Expense, Income
from .serializers import (
    RegisterSerializer,
    UserSerializer,
    ExpenseSerializer,
    ExpenseListSerializer,
    IncomeSerializer,
    IncomeListSerializer,
)
import django_filters


# ── Auth ───────────────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    queryset           = User.objects.all()
    serializer_class   = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'user':    UserSerializer(user).data,
            'refresh': str(refresh),
            'access':  str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'detail': 'Вы вышли из системы'})
        except Exception:
            return Response({'detail': 'Неверный токен'}, status=status.HTTP_400_BAD_REQUEST)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


# ── Expenses ───────────────────────────────────────────────────────────────

class ExpenseFilter(django_filters.FilterSet):
    category  = django_filters.CharFilter(field_name='category')
    date_from = django_filters.DateFilter(field_name='created_at__date', lookup_expr='gte')
    date_to   = django_filters.DateFilter(field_name='created_at__date', lookup_expr='lte')

    class Meta:
        model  = Expense
        fields = ['category', 'date_from', 'date_to']


class ExpenseListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend]
    filterset_class    = ExpenseFilter

    def get_queryset(self):
        return Expense.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return ExpenseListSerializer
        return ExpenseSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset   = self.filter_queryset(self.get_queryset())
        total      = queryset.aggregate(total=Sum('amount'))['total'] or 0
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count':    queryset.count(),
            'total':    float(total),
            'expenses': serializer.data,
        })


class ExpenseDetailView(generics.RetrieveDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class   = ExpenseListSerializer

    def get_queryset(self):
        return Expense.objects.filter(user=self.request.user)


# ── Income ─────────────────────────────────────────────────────────────────

class IncomeFilter(django_filters.FilterSet):
    category  = django_filters.CharFilter(field_name='category')
    date_from = django_filters.DateFilter(field_name='created_at__date', lookup_expr='gte')
    date_to   = django_filters.DateFilter(field_name='created_at__date', lookup_expr='lte')

    class Meta:
        model  = Income
        fields = ['category', 'date_from', 'date_to']


class IncomeListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend]
    filterset_class    = IncomeFilter

    def get_queryset(self):
        return Income.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return IncomeListSerializer
        return IncomeSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset   = self.filter_queryset(self.get_queryset())
        total      = queryset.aggregate(total=Sum('amount'))['total'] or 0
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count':   queryset.count(),
            'total':   float(total),
            'incomes': serializer.data,
        })


class IncomeDetailView(generics.RetrieveDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class   = IncomeListSerializer

    def get_queryset(self):
        return Income.objects.filter(user=self.request.user)
