from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import Attendance, Member, Payment, Subscription


class ReportingService:
    def __init__(self, db: Session):
        self.db = db

    def _bounds(self, day: date):
        zone = ZoneInfo(settings.gym_timezone)
        start = datetime.combine(day, time.min, zone).astimezone(timezone.utc)
        return start, (start + timedelta(days=1))

    def dashboard(self, today: date | None = None):
        today = today or datetime.now(ZoneInfo(settings.gym_timezone)).date()
        month_start = today.replace(day=1)
        today_start, tomorrow_start = self._bounds(today)
        month_utc, _ = self._bounds(month_start)
        expiring = today + timedelta(days=7)
        scalar = self.db.scalar
        metrics = {
            "total_members": scalar(select(func.count()).select_from(Member)) or 0,
            "active_members": scalar(select(func.count()).select_from(Member).where(Member.status == "active")) or 0,
            "expired_memberships": scalar(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.status == "active", Subscription.end_date < today)
            )
            or 0,
            "expiring_soon": scalar(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.status == "active", Subscription.end_date.between(today, expiring))
            )
            or 0,
            "today_attendance": scalar(
                select(func.count()).select_from(Attendance).where(Attendance.attendance_date == today)
            )
            or 0,
            "today_revenue": scalar(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.paid_at >= today_start, Payment.paid_at < tomorrow_start
                )
            )
            or Decimal("0"),
            "monthly_revenue": scalar(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.paid_at >= month_utc, Payment.paid_at < tomorrow_start
                )
            )
            or Decimal("0"),
            "new_members_month": scalar(
                select(func.count())
                .select_from(Member)
                .where(Member.registration_date >= month_start, Member.registration_date <= today)
            )
            or 0,
        }
        recent_payments = list(
            self.db.scalars(
                select(Payment).options(selectinload(Payment.member)).order_by(Payment.paid_at.desc()).limit(5)
            )
        )
        expirations = list(
            self.db.scalars(
                select(Subscription)
                .options(selectinload(Subscription.member), selectinload(Subscription.plan))
                .where(Subscription.status == "active", Subscription.end_date.between(today, expiring))
                .order_by(Subscription.end_date)
                .limit(5)
            )
        )
        recent_members = list(
            self.db.scalars(select(Member).order_by(Member.registration_date.desc(), Member.id.desc()).limit(5))
        )
        return metrics, recent_payments, expirations, recent_members

    def report_rows(self, kind: str, start: date | None = None, end: date | None = None):
        today = datetime.now(ZoneInfo(settings.gym_timezone)).date()
        if kind == "active-members":
            return [
                ("Member #", "Name", "Phone", "Registered"),
                *[
                    (m.member_number, m.full_name, m.phone, m.registration_date)
                    for m in self.db.scalars(select(Member).where(Member.status == "active").order_by(Member.full_name))
                ],
            ]
        if kind in {"expired-memberships", "expiring-soon"}:
            filters = [Subscription.status == "active"]
            filters.append(
                Subscription.end_date < today
                if kind == "expired-memberships"
                else Subscription.end_date.between(today, today + timedelta(days=7))
            )
            rows = self.db.scalars(
                select(Subscription)
                .options(selectinload(Subscription.member), selectinload(Subscription.plan))
                .where(*filters)
                .order_by(Subscription.end_date)
            )
            return [
                ("Member #", "Name", "Plan", "End date"),
                *[(s.member.member_number, s.member.full_name, s.plan.name, s.end_date) for s in rows],
            ]
        if kind == "attendance":
            filters = []
            if start:
                filters.append(Attendance.attendance_date >= start)
            if end:
                filters.append(Attendance.attendance_date <= end)
            rows = self.db.scalars(
                select(Attendance)
                .options(selectinload(Attendance.member))
                .where(*filters)
                .order_by(Attendance.checked_in_at.desc())
            )
            return [
                ("Member #", "Name", "Date", "Check-in"),
                *[(a.member.member_number, a.member.full_name, a.attendance_date, a.checked_in_at) for a in rows],
            ]
        if kind in {"payments", "revenue"}:
            filters = []
            if start:
                filters.append(func.date(Payment.paid_at) >= start)
            if end:
                filters.append(func.date(Payment.paid_at) <= end)
            rows = list(
                self.db.scalars(
                    select(Payment)
                    .options(selectinload(Payment.member))
                    .where(*filters)
                    .order_by(Payment.paid_at.desc())
                )
            )
            if kind == "revenue":
                grouped: dict[str, Decimal] = {}
                for p in rows:
                    key = str(p.paid_at.date())
                    grouped[key] = grouped.get(key, Decimal("0")) + p.amount
                return [("Date", "Revenue"), *sorted(grouped.items(), reverse=True)]
            return [
                ("Reference", "Member", "Amount", "Method", "Paid at"),
                *[
                    (p.reference_number or f"PAY-{p.id:06d}", p.member.full_name, p.amount, p.method, p.paid_at)
                    for p in rows
                ],
            ]
        if kind == "new-members":
            filters = []
            if start:
                filters.append(Member.registration_date >= start)
            if end:
                filters.append(Member.registration_date <= end)
            rows = self.db.scalars(select(Member).where(*filters).order_by(Member.registration_date.desc()))
            return [
                ("Member #", "Name", "Phone", "Registered"),
                *[(m.member_number, m.full_name, m.phone, m.registration_date) for m in rows],
            ]
        raise ValueError("Unknown report type")
