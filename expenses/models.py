from django.db import models
from django.contrib.auth.models import User


class Income(models.Model):
    CATEGORY_CHOICES = [
        ('salary',     'Зарплата'),
        ('freelance',  'Фриланс'),
        ('business',   'Бизнес'),
        ('investment', 'Инвестиции'),
        ('gift',       'Подарок'),
        ('other',      'Другое'),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='incomes')
    title      = models.CharField(max_length=255)
    amount     = models.DecimalField(max_digits=12, decimal_places=2)
    category   = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='salary')
    created_at = models.DateTimeField(auto_now_add=True)
    note       = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} — {self.title} (+{self.amount})'


class Expense(models.Model):
    CATEGORY_CHOICES = [
        ('food',          'Еда'),
        ('transport',     'Транспорт'),
        ('business',      'Бизнес'),
        ('health',        'Здоровье'),
        ('education',     'Образование'),
        ('entertainment', 'Развлечения'),
        ('shopping',      'Покупки'),
        ('utilities',     'Коммунальные'),
        ('credit',        'Кредит'),
        ('other',         'Другое'),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='expenses')
    title      = models.CharField(max_length=255)
    amount     = models.DecimalField(max_digits=12, decimal_places=2)
    category   = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='other')
    created_at = models.DateTimeField(auto_now_add=True)
    note       = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} — {self.title} ({self.amount})'


# ── Analytics Models ────────────────────────────────────────────────────────

class UserInsightFeedback(models.Model):
    """Stores user 👍/👎 on AI recommendations for self-learning."""
    RATING_CHOICES = [(1, 'Полезно'), (-1, 'Не полезно')]

    user                = models.ForeignKey(User, on_delete=models.CASCADE, related_name='insight_feedbacks')
    recommendation_type = models.CharField(max_length=120)
    recommendation_text = models.TextField()
    rating              = models.SmallIntegerField(choices=RATING_CHOICES)
    context_data        = models.JSONField(default=dict, blank=True)
    created_at          = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [models.Index(fields=['user', 'recommendation_type'])]

    def __str__(self):
        label = dict(self.RATING_CHOICES).get(self.rating, '?')
        return f'{self.user.username} — {self.recommendation_type}: {label}'


class CategoryCorrection(models.Model):
    """Stores category corrections for self-learning re-categorization."""
    user               = models.ForeignKey(User, on_delete=models.CASCADE, related_name='category_corrections')
    expense            = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='corrections')
    original_category  = models.CharField(max_length=50)
    corrected_category = models.CharField(max_length=50)
    expense_title      = models.CharField(max_length=255)
    created_at         = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [models.Index(fields=['user', 'original_category', 'corrected_category'])]

    def __str__(self):
        return f'{self.user.username}: {self.original_category} → {self.corrected_category} ({self.expense_title})'


class AnomalyRecord(models.Model):
    """Persists detected spending anomalies; allows user to dismiss them."""
    user              = models.ForeignKey(User, on_delete=models.CASCADE, related_name='anomalies')
    expense           = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='anomalies')
    category          = models.CharField(max_length=50)
    amount            = models.DecimalField(max_digits=12, decimal_places=2)
    avg_amount        = models.DecimalField(max_digits=12, decimal_places=2)
    deviation_factor  = models.FloatField()
    is_dismissed      = models.BooleanField(default=False)
    detected_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering  = ['-deviation_factor']
        unique_together = ['user', 'expense']
        indexes   = [models.Index(fields=['user', 'is_dismissed'])]

    def __str__(self):
        return f'{self.user.username} — {self.category}: {self.amount} (×{self.deviation_factor:.1f})'


class Credit(models.Model):
    """User credit / loan record with annuity calculation support."""
    STATUS_CHOICES = [
        ('active',   'Активный'),
        ('paid_off', 'Погашен'),
    ]

    user        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='credits')
    title       = models.CharField(max_length=255)
    amount      = models.DecimalField(max_digits=15, decimal_places=2)
    annual_rate = models.DecimalField(max_digits=6, decimal_places=3)
    term_months = models.PositiveIntegerField()
    start_date  = models.DateField()
    bank        = models.CharField(max_length=255, blank=True, default='')
    is_active   = models.BooleanField(default=True)
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} — {self.title} ({self.amount})'


class CreditPayment(models.Model):
    """Actual payment recorded against a credit."""
    credit       = models.ForeignKey(Credit, on_delete=models.CASCADE, related_name='payments')
    amount       = models.DecimalField(max_digits=15, decimal_places=2)
    principal    = models.DecimalField(max_digits=15, decimal_places=2)
    interest     = models.DecimalField(max_digits=15, decimal_places=2)
    payment_date = models.DateField()
    note         = models.CharField(max_length=255, blank=True, default='')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['payment_date', 'created_at']

    def __str__(self):
        return f'{self.credit.title} — {self.amount} ({self.payment_date})'


class MonthlySnapshot(models.Model):
    """Monthly aggregated analytics snapshot for historical comparison."""
    user           = models.ForeignKey(User, on_delete=models.CASCADE, related_name='monthly_snapshots')
    year           = models.PositiveSmallIntegerField()
    month          = models.PositiveSmallIntegerField()
    total_expenses = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_income   = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    by_category    = models.JSONField(default=dict)
    analysis_meta  = models.JSONField(default=dict)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'year', 'month']
        ordering        = ['-year', '-month']

    def __str__(self):
        return f'{self.user.username} — {self.year}/{self.month:02d}'
