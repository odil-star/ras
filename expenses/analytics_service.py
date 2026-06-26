"""
Analytics Service — Pandas + Scikit-learn driven expense intelligence.

Provides:
  - Monthly forecast with linear regression + accuracy estimate
  - Category breakdown with MoM comparison
  - Anomaly detection via Z-score
  - Savings timeline (last 6 months)
  - Adaptive recommendations weighted by user feedback
  - Self-learning: category correction suggestions
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

CAT_LABELS_RU: dict[str, str] = {
    'food':          'Еда',
    'transport':     'Транспорт',
    'business':      'Бизнес',
    'health':        'Здоровье',
    'education':     'Образование',
    'entertainment': 'Развлечения',
    'shopping':      'Покупки',
    'utilities':     'Коммунальные',
    'credit':        'Кредит',
    'other':         'Другое',
}


def _to_period(d: date) -> pd.Period:
    return pd.Period(d, 'M')


def _period_label(p: pd.Period) -> str:
    month_names = [
        '', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
    ]
    return f"{month_names[p.month]} {p.year}"


# ── Core service ─────────────────────────────────────────────────────────────

class AnalyticsService:
    """Stateless analytics service; instantiate per request."""

    def __init__(self, user) -> None:
        self.user = user

    # ── Data loaders ─────────────────────────────────────────────────────────

    def _expense_df(self) -> pd.DataFrame:
        from .models import Expense
        qs = Expense.objects.filter(user=self.user).values(
            'id', 'title', 'amount', 'category', 'created_at',
        )
        if not qs.exists():
            return pd.DataFrame()
        df = pd.DataFrame(list(qs))
        df['amount']     = df['amount'].astype(float)
        # Convert to UTC then strip tz info to avoid pandas PeriodArray warning
        dt = pd.to_datetime(df['created_at'], utc=True)
        dt = dt.dt.tz_convert('UTC').dt.tz_localize(None)
        df['created_at']   = dt
        df['date']         = dt.dt.date
        df['year_month']   = dt.dt.to_period('M')
        df['day_of_month'] = dt.dt.day
        df['cat_label']    = df['category'].map(lambda c: CAT_LABELS_RU.get(c, c))
        return df

    def _income_df(self) -> pd.DataFrame:
        from .models import Income
        qs = Income.objects.filter(user=self.user).values('amount', 'created_at')
        if not qs.exists():
            return pd.DataFrame()
        df = pd.DataFrame(list(qs))
        df['amount']     = df['amount'].astype(float)
        # Strip timezone before period conversion
        dt = pd.to_datetime(df['created_at'], utc=True)
        dt = dt.dt.tz_convert('UTC').dt.tz_localize(None)
        df['created_at'] = dt
        df['year_month'] = dt.dt.to_period('M')
        return df

    def _feedback_weights(self) -> dict[str, float]:
        """Aggregate user feedback into per-type multipliers for self-learning."""
        from .models import UserInsightFeedback
        qs = UserInsightFeedback.objects.filter(user=self.user).values(
            'recommendation_type', 'rating',
        )
        weights: dict[str, float] = {}
        counts:  dict[str, int]   = {}
        for row in qs:
            t = row['recommendation_type']
            weights[t] = weights.get(t, 0) + row['rating']
            counts[t]  = counts.get(t, 0) + 1

        result: dict[str, float] = {}
        for t, total in weights.items():
            avg = total / counts[t]
            # Map [-1, +1] → [0.2, 2.0]  so never-helpful → almost suppressed
            result[t] = max(0.2, 1.0 + avg)
        return result

    def _learned_category_map(self) -> dict[str, dict[str, str]]:
        """
        Return title→category mapping learned from user corrections.
        { expense_title_lower: corrected_category }
        """
        from .models import CategoryCorrection
        qs = CategoryCorrection.objects.filter(user=self.user).values(
            'expense_title', 'corrected_category',
        )
        return {row['expense_title'].lower(): row['corrected_category'] for row in qs}

    # ── 1. Monthly forecast ───────────────────────────────────────────────────

    def calculate_monthly_forecast(self) -> dict[str, Any]:
        """
        Linear-regression forecast on cumulative daily spend.
        Accuracy is derived from historical month-to-month coefficient of variation.
        """
        df = self._expense_df()
        today         = date.today()
        current_p     = _to_period(today)
        days_in_month = current_p.days_in_month
        days_elapsed  = today.day
        days_remaining = days_in_month - days_elapsed

        if df.empty:
            return {
                'current_total': 0, 'forecast_total': 0,
                'days_elapsed': days_elapsed, 'days_remaining': days_remaining,
                'days_in_month': days_in_month, 'accuracy_percent': 0,
                'avg_daily': 0, 'method': 'no_data',
            }

        cur_df = df[df['year_month'] == current_p]
        current_total = float(cur_df['amount'].sum())

        # Historical monthly totals (excluding current month)
        hist_monthly = (
            df[df['year_month'] != current_p]
            .groupby('year_month')['amount'].sum()
        )

        # Try regression on cumulative daily spending
        method = 'avg_daily'
        forecast_total = 0.0

        if not cur_df.empty and days_elapsed >= 3:
            daily_sum = cur_df.groupby('day_of_month')['amount'].sum()
            cumulative = daily_sum.sort_index().cumsum()
            X = cumulative.index.values.reshape(-1, 1).astype(float)
            y = cumulative.values.astype(float)
            if len(X) >= 3:
                try:
                    model = LinearRegression()
                    model.fit(X, y)
                    forecast_total = float(model.predict([[days_in_month]])[0])
                    forecast_total = max(forecast_total, current_total)
                    method = 'linear_regression'
                except Exception as exc:
                    logger.warning("LR failed: %s", exc)

        if method == 'avg_daily' or forecast_total <= 0:
            avg_d = current_total / days_elapsed if days_elapsed > 0 else 0
            forecast_total = avg_d * days_in_month
            method = 'avg_daily'

        # Accuracy from historical consistency
        if len(hist_monthly) >= 2:
            hist_std  = float(hist_monthly.std())
            hist_mean = float(hist_monthly.mean())
            cv        = hist_std / hist_mean if hist_mean > 0 else 1.0
            # CV of 0 → 95%, CV of 1 → 50%, CV >2 → 30%
            accuracy = max(30.0, min(95.0, 95.0 - cv * 45.0))
        elif len(hist_monthly) == 1:
            accuracy = 65.0
        else:
            accuracy = 55.0

        return {
            'current_total':   round(current_total, 2),
            'forecast_total':  round(max(forecast_total, 0), 2),
            'days_elapsed':    days_elapsed,
            'days_remaining':  days_remaining,
            'days_in_month':   days_in_month,
            'accuracy_percent': round(accuracy, 1),
            'avg_daily':       round(current_total / days_elapsed if days_elapsed > 0 else 0, 2),
            'method':          method,
        }

    # ── 2. Category analysis ─────────────────────────────────────────────────

    def get_category_analysis(self) -> list[dict]:
        """Per-category spending with MoM comparison and trend."""
        df = self._expense_df()
        if df.empty:
            return []

        today     = date.today()
        cur_p     = _to_period(today)
        prev_p    = cur_p - 1

        cur_grp   = df[df['year_month'] == cur_p].groupby('category')['amount'].sum()
        prev_grp  = df[df['year_month'] == prev_p].groupby('category')['amount'].sum()
        cur_total = float(cur_grp.sum())

        all_cats = set(cur_grp.index) | set(prev_grp.index)
        result   = []
        for cat in all_cats:
            cur_amt  = float(cur_grp.get(cat, 0))
            prev_amt = float(prev_grp.get(cat, 0))
            pct_total = (cur_amt / cur_total * 100) if cur_total > 0 else 0

            if prev_amt > 0:
                change_pct = ((cur_amt - prev_amt) / prev_amt) * 100
            elif cur_amt > 0:
                change_pct = 100.0
            else:
                change_pct = 0.0

            if   change_pct > 10:  trend = 'up'
            elif change_pct < -10: trend = 'down'
            else:                  trend = 'stable'

            result.append({
                'category':          cat,
                'label':             CAT_LABELS_RU.get(cat, cat),
                'current_amount':    round(cur_amt,   2),
                'previous_amount':   round(prev_amt,  2),
                'percent_of_total':  round(pct_total, 1),
                'change_percent':    round(change_pct, 1),
                'trend':             trend,
            })

        return sorted(result, key=lambda x: x['current_amount'], reverse=True)

    # ── 3. Anomaly detection ──────────────────────────────────────────────────

    def detect_anomalies(self, z_threshold: float = 2.0) -> list[dict]:
        """
        Z-score anomaly detection per category using last 90 days as baseline.
        Saves new anomalies to AnomalyRecord; marks dismissed ones.
        """
        from .models import AnomalyRecord

        df = self._expense_df()
        if df.empty or len(df) < 5:
            return []

        cutoff = date.today() - timedelta(days=90)
        recent = df[df['date'] >= cutoff].copy()
        if recent.empty:
            return []

        dismissed_ids: set[int] = set(
            AnomalyRecord.objects.filter(user=self.user, is_dismissed=True)
            .values_list('expense_id', flat=True)
        )

        anomalies: list[dict] = []
        for category, cat_df in recent.groupby('category'):
            if len(cat_df) < 3:
                continue

            mean = float(cat_df['amount'].mean())
            std  = float(cat_df['amount'].std())
            if std < 1:
                continue

            for _, row in cat_df.iterrows():
                z = (float(row['amount']) - mean) / std
                if z <= z_threshold:
                    continue

                exp_id = int(row['id'])
                if exp_id in dismissed_ids:
                    continue

                # Persist if not already stored (silently skip on DB lock)
                try:
                    AnomalyRecord.objects.get_or_create(
                        user=self.user,
                        expense_id=exp_id,
                        defaults={
                            'category':         category,
                            'amount':           row['amount'],
                            'avg_amount':       round(mean, 2),
                            'deviation_factor': round(z, 2),
                        },
                    )
                except Exception as exc:
                    logger.warning("Failed to persist anomaly record: %s", exc)
                anomalies.append({
                    'expense_id':       exp_id,
                    'title':            row['title'],
                    'category':         category,
                    'label':            CAT_LABELS_RU.get(category, category),
                    'amount':           float(row['amount']),
                    'avg_amount':       round(mean, 2),
                    'deviation_factor': round(z, 2),
                    'date':             str(row['date']),
                    'is_dismissed':     False,
                })

        return sorted(anomalies, key=lambda x: x['deviation_factor'], reverse=True)

    # ── 4. Savings timeline ───────────────────────────────────────────────────

    def calculate_savings_timeline(self, months: int = 6) -> list[dict]:
        """Month-by-month income vs expenses vs savings for the last N months."""
        df_exp = self._expense_df()
        df_inc = self._income_df()

        today      = date.today()
        cur_p      = _to_period(today)
        periods    = [cur_p - i for i in range(months - 1, -1, -1)]

        exp_monthly = (
            df_exp.groupby('year_month')['amount'].sum()
            if not df_exp.empty else pd.Series(dtype=float)
        )
        inc_monthly = (
            df_inc.groupby('year_month')['amount'].sum()
            if not df_inc.empty else pd.Series(dtype=float)
        )

        result = []
        for p in periods:
            exp = float(exp_monthly.get(p, 0))
            inc = float(inc_monthly.get(p, 0))
            result.append({
                'period':        str(p),
                'period_label':  _period_label(p),
                'expenses':      round(exp, 2),
                'income':        round(inc, 2),
                'savings':       round(inc - exp, 2),
                'is_current':    p == cur_p,
            })
        return result

    # ── 5. Recommendations (adaptive) ────────────────────────────────────────

    def generate_recommendations(self) -> list[dict]:
        """
        Generate personalised recommendations.
        Weights are derived from UserInsightFeedback (self-learning).
        """
        categories = self.get_category_analysis()
        anomalies  = self.detect_anomalies()
        weights    = self._feedback_weights()

        recs: list[dict] = []

        # R1 — top spending category
        if categories:
            top = categories[0]
            rtype = 'reduce_top_category'
            w = weights.get(rtype, 1.0)
            if w >= 0.2:
                recs.append({
                    'type':      rtype,
                    'priority':  'high',
                    'icon':      'reduce',
                    'title':     f'Оптимизируйте «{top["label"]}»',
                    'text':      (
                        f'Категория занимает {top["percent_of_total"]}% расходов этого месяца. '
                        f'Снижение на 15% сэкономит ~{round(top["current_amount"] * 0.15):,} сум.'
                    ).replace(',', ' '),
                    'category':          top['category'],
                    'potential_saving':  round(top['current_amount'] * 0.15, 2),
                    'weight':            round(w, 2),
                    'link':              '/budget',
                    'action':            'Установить лимит',
                })

        # R2 — fast-growing categories
        growing = [c for c in categories if c['change_percent'] > 20 and c['current_amount'] > 0]
        for cat in growing[:2]:
            rtype = f'control_growth_{cat["category"]}'
            w = weights.get(rtype, 1.0)
            if w >= 0.2:
                recs.append({
                    'type':      rtype,
                    'priority':  'high',
                    'icon':      'trending-up',
                    'title':     f'Рост расходов на «{cat["label"]}»',
                    'text':      (
                        f'Расходы выросли на {cat["change_percent"]:.0f}% vs прошлый месяц. '
                        f'Установите лимит, чтобы держать под контролем.'
                    ),
                    'category':         cat['category'],
                    'potential_saving': round(cat['current_amount'] * 0.1, 2),
                    'weight':           round(w, 2),
                    'link':             '/budget',
                    'action':           'Настроить бюджет',
                })

        # R3 — anomaly-based
        if anomalies:
            an = anomalies[0]
            rtype = 'anomaly_review'
            w = weights.get(rtype, 1.0)
            if w >= 0.2:
                recs.append({
                    'type':      rtype,
                    'priority':  'high',
                    'icon':      'warning',
                    'title':     'Аномальная трата обнаружена',
                    'text':      (
                        f'«{an["title"]}» в категории «{an["label"]}» '
                        f'в {an["deviation_factor"]:.1f}× превышает средний уровень '
                        f'({int(an["avg_amount"]):,} сум).'
                    ).replace(',', ' '),
                    'category': an['category'],
                    'weight':   round(w, 2),
                    'link':     '/expenses',
                    'action':   'Посмотреть расходы',
                })

        # R4 — diversification if top-3 > 80%
        if len(categories) >= 3:
            top3_sum = sum(c['current_amount'] for c in categories[:3])
            total    = sum(c['current_amount'] for c in categories)
            if total > 0:
                top3_pct = top3_sum / total * 100
                rtype = 'diversify_spending'
                w = weights.get(rtype, 1.0)
                if top3_pct > 75 and w >= 0.2:
                    recs.append({
                        'type':     rtype,
                        'priority': 'medium',
                        'icon':     'pie-chart',
                        'title':    'Концентрация расходов',
                        'text':     (
                            f'{top3_pct:.0f}% бюджета уходит в 3 категории. '
                            f'Детальный анализ поможет найти точки экономии.'
                        ),
                        'weight': round(w, 2),
                        'link':   '/analytics',
                        'action': 'Открыть аналитику',
                    })

        # R5 — save more if good savings rate
        savings_list = self.calculate_savings_timeline(months=2)
        if len(savings_list) >= 2:
            prev = savings_list[-2]
            if prev['income'] > 0 and prev['savings'] > prev['income'] * 0.25:
                rtype = 'increase_savings'
                w = weights.get(rtype, 1.0)
                if w >= 0.2:
                    recs.append({
                        'type':     rtype,
                        'priority': 'low',
                        'icon':     'savings',
                        'title':    'Отличный темп сбережений!',
                        'text':     (
                            f'В прошлом месяце вы сэкономили {int(prev["savings"]):,} сум. '
                            f'Рассмотрите инвестиции или накопления.'
                        ).replace(',', ' '),
                        'weight': round(w, 2),
                        'link':   '/income',
                        'action': 'Добавить доход',
                    })

        # Sort: priority ×weight  (high=3, medium=2, low=1)
        pmap = {'high': 3, 'medium': 2, 'low': 1}
        recs.sort(key=lambda r: pmap.get(r['priority'], 1) * r.get('weight', 1), reverse=True)
        return recs

    # ── 6. Self-learning: suggest category ───────────────────────────────────

    def suggest_category(self, title: str) -> str | None:
        """
        Suggest a category for an expense title based on learned corrections.
        Returns corrected category or None if no learning available.
        """
        learned = self._learned_category_map()
        title_lower = title.lower().strip()

        # Exact match
        if title_lower in learned:
            return learned[title_lower]

        # Substring match
        for known_title, cat in learned.items():
            if known_title in title_lower or title_lower in known_title:
                return cat

        return None

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def save_monthly_snapshot(self, year: int, month: int) -> None:
        """Persist a monthly analytics snapshot to MonthlySnapshot."""
        from .models import MonthlySnapshot

        df     = self._expense_df()
        df_inc = self._income_df()
        target = pd.Period(f'{year}-{month:02d}', 'M')

        exp_df  = df[df['year_month'] == target] if not df.empty else pd.DataFrame()
        inc_df  = df_inc[df_inc['year_month'] == target] if not df_inc.empty else pd.DataFrame()

        total_exp = float(exp_df['amount'].sum()) if not exp_df.empty else 0.0
        total_inc = float(inc_df['amount'].sum()) if not inc_df.empty else 0.0

        by_cat = {}
        if not exp_df.empty:
            by_cat = {k: round(float(v), 2) for k, v in exp_df.groupby('category')['amount'].sum().items()}

        MonthlySnapshot.objects.update_or_create(
            user=self.user, year=year, month=month,
            defaults={
                'total_expenses': total_exp,
                'total_income':   total_inc,
                'by_category':    by_cat,
                'analysis_meta':  {'snapshot_method': 'auto'},
            },
        )
