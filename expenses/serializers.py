from django.contrib.auth.models import User
from rest_framework import serializers
from .models import Expense, Income, Credit, CreditPayment


class RegisterSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(write_only=True, min_length=6)
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model  = User
        fields = ['username', 'email', 'password', 'password2']

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password': 'Пароли не совпадают'})
        return data

    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(**validated_data)
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ['id', 'username', 'email', 'date_joined']


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Expense
        fields = ['id', 'title', 'amount', 'category', 'note', 'created_at']
        read_only_fields = ['id', 'created_at']


class ExpenseListSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(
        source='get_category_display', read_only=True
    )

    class Meta:
        model  = Expense
        fields = ['id', 'title', 'amount', 'category', 'category_display', 'note', 'created_at']


class IncomeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Income
        fields = ['id', 'title', 'amount', 'category', 'note', 'created_at']
        read_only_fields = ['id', 'created_at']


class IncomeListSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(
        source='get_category_display', read_only=True
    )

    class Meta:
        model  = Income
        fields = ['id', 'title', 'amount', 'category', 'category_display', 'note', 'created_at']


class CreditPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CreditPayment
        fields = ['id', 'amount', 'principal', 'interest', 'payment_date', 'note', 'created_at']
        read_only_fields = ['id', 'principal', 'interest', 'created_at']


class CreditSerializer(serializers.ModelSerializer):
    payments          = CreditPaymentSerializer(many=True, read_only=True)
    remaining_balance = serializers.SerializerMethodField()
    total_paid        = serializers.SerializerMethodField()
    total_interest    = serializers.SerializerMethodField()
    paid_principal    = serializers.SerializerMethodField()

    class Meta:
        model  = Credit
        fields = [
            'id', 'title', 'amount', 'annual_rate', 'term_months',
            'start_date', 'bank', 'is_active', 'status', 'created_at',
            'payments', 'remaining_balance', 'total_paid', 'total_interest', 'paid_principal',
        ]
        read_only_fields = ['id', 'created_at', 'status']

    def get_remaining_balance(self, obj):
        paid = sum(float(p.principal) for p in obj.payments.all())
        return round(max(0.0, float(obj.amount) - paid), 2)

    def get_total_paid(self, obj):
        return round(sum(float(p.amount) for p in obj.payments.all()), 2)

    def get_total_interest(self, obj):
        return round(sum(float(p.interest) for p in obj.payments.all()), 2)

    def get_paid_principal(self, obj):
        return round(sum(float(p.principal) for p in obj.payments.all()), 2)
