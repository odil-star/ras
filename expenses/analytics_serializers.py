from rest_framework import serializers
from .models import UserInsightFeedback, CategoryCorrection, AnomalyRecord, MonthlySnapshot


class InsightFeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model  = UserInsightFeedback
        fields = ['id', 'recommendation_type', 'recommendation_text', 'rating', 'context_data', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_rating(self, value):
        if value not in (1, -1):
            raise serializers.ValidationError('rating must be 1 or -1')
        return value


class CategoryCorrectionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CategoryCorrection
        fields = ['id', 'expense', 'original_category', 'corrected_category', 'expense_title', 'created_at']
        read_only_fields = ['id', 'expense_title', 'original_category', 'created_at']


class AnomalyRecordSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()

    class Meta:
        model  = AnomalyRecord
        fields = ['id', 'expense_id', 'category', 'label', 'amount', 'avg_amount',
                  'deviation_factor', 'is_dismissed', 'detected_at']

    def get_label(self, obj):
        from .analytics_service import CAT_LABELS_RU
        return CAT_LABELS_RU.get(obj.category, obj.category)


class MonthlySnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model  = MonthlySnapshot
        fields = ['id', 'year', 'month', 'total_expenses', 'total_income',
                  'by_category', 'analysis_meta', 'created_at']
        read_only_fields = ['id', 'created_at']
