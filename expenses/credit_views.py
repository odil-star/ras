import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from .models import Credit, CreditPayment
from .serializers import CreditSerializer, CreditPaymentSerializer

logger = logging.getLogger(__name__)


class CreditListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class   = CreditSerializer

    def get_queryset(self):
        return (
            Credit.objects
            .filter(user=self.request.user)
            .prefetch_related('payments')
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def list(self, request, *args, **kwargs):
        try:
            qs = self.get_queryset()
            serializer = self.get_serializer(qs, many=True)
            return Response({
                'count':   qs.count(),
                'active':  qs.filter(is_active=True).count(),
                'credits': serializer.data,
            })
        except Exception as exc:
            logger.exception("CreditListCreateView.list error: %s", exc)
            return Response(
                {'detail': 'Ошибка загрузки кредитов'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except Exception as exc:
            logger.exception("CreditListCreateView.create error: %s", exc)
            return Response(
                {'detail': 'Ошибка создания кредита'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CreditDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class   = CreditSerializer

    def get_queryset(self):
        return (
            Credit.objects
            .filter(user=self.request.user)
            .prefetch_related('payments')
        )

    def update(self, request, *args, **kwargs):
        try:
            kwargs['partial'] = True
            return super().update(request, *args, **kwargs)
        except Exception as exc:
            logger.exception("CreditDetailView.update error: %s", exc)
            return Response(
                {'detail': 'Ошибка обновления кредита'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except Exception as exc:
            logger.exception("CreditDetailView.destroy error: %s", exc)
            return Response(
                {'detail': 'Ошибка удаления кредита'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CreditPayView(APIView):
    """Record an actual payment against a credit and update its balance."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            credit = get_object_or_404(Credit, pk=pk, user=request.user)

            # ── Validate amount ──────────────────────────────────────────────
            amount_raw = request.data.get('amount')
            if amount_raw is None:
                return Response({'error': 'Укажите сумму платежа'}, status=400)
            try:
                amount = Decimal(str(amount_raw))
                if amount <= 0:
                    return Response({'error': 'Сумма должна быть больше 0'}, status=400)
            except (TypeError, ValueError, InvalidOperation):
                return Response({'error': 'Некорректная сумма'}, status=400)

            payment_date_str = request.data.get('payment_date') or str(date.today())
            note = str(request.data.get('note') or '')

            # ── Calculate current remaining principal ────────────────────────
            paid_principal_total = sum(
                Decimal(str(p.principal)) for p in credit.payments.all()
            )
            remaining = Decimal(str(credit.amount)) - paid_principal_total

            if remaining <= Decimal('0.01'):
                return Response({'error': 'Кредит уже полностью погашен'}, status=400)

            # ── Split payment into interest + principal ──────────────────────
            monthly_rate = Decimal(str(credit.annual_rate)) / Decimal('1200')
            interest_due = (remaining * monthly_rate).quantize(Decimal('0.01'))

            auto_closed = False
            if amount >= remaining:
                # Payment covers the entire remaining principal → close credit
                principal     = remaining
                interest_part = max(Decimal('0'), min(interest_due, amount - principal))
                credit.is_active = False
                credit.status    = 'paid_off'
                credit.save()
                auto_closed = True
            else:
                interest_part = interest_due
                principal     = max(Decimal('0'), amount - interest_part)

            payment = CreditPayment.objects.create(
                credit=credit,
                amount=amount,
                principal=principal.quantize(Decimal('0.01')),
                interest=interest_part.quantize(Decimal('0.01')),
                payment_date=payment_date_str,
                note=note,
            )

            # Return updated credit with all computed fields
            credit.refresh_from_db()
            serializer = CreditSerializer(
                credit,
                context={'request': request},
            )
            # prefetch payments so SerializerMethodField works
            credit._prefetched_objects_cache = {}
            serializer = CreditSerializer(
                Credit.objects.prefetch_related('payments').get(pk=credit.pk),
                context={'request': request},
            )

            return Response({
                'auto_closed': auto_closed,
                'payment':     CreditPaymentSerializer(payment).data,
                'credit':      serializer.data,
            })

        except Exception as exc:
            logger.exception("CreditPayView.post error: %s", exc)
            return Response(
                {'error': 'Ошибка при проведении платежа'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
