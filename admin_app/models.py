# App: admin_app | File: models.py
from django.db import models
import uuid


class AppSetting(models.Model):
    """
    Global, admin-controlled app configuration. Single row (id=1).

    `subscription_mode`:
      - "free"  → the whole app is free; clients can redeem deals without any
                  subscription (this is the launch default).
      - "plans" → redemption requires an ACTIVE WINDEAL+ subscription.
    """
    SUBSCRIPTION_MODES = [
        ("free",  "Free — everyone can redeem, no subscription needed"),
        ("plans", "Plans — redemption requires an active subscription"),
    ]

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    subscription_mode = models.CharField(max_length=10, choices=SUBSCRIPTION_MODES, default="free")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "app_settings"

    def __str__(self):
        return f"AppSetting (mode={self.subscription_mode})"

    def save(self, *args, **kwargs):
        self.id = 1                      # enforce singleton
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj

    @classmethod
    def is_free(cls):
        return cls.load().subscription_mode == "free"


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    photo = models.ImageField(upload_to="categories/", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "categories"
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class SubscriptionPlan(models.Model):
    PLAN_DURATION = [
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
        ("semi_annual", "Semi-Annual"),
        ("annual", "Annual"),
        ("custom", "Custom"),
    ]

    TARGET_ROLE = [
        ("client", "Client"),
        ("business", "Business"),
        ("both", "Both"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_type = models.CharField(max_length=20, choices=PLAN_DURATION)
    duration_days = models.PositiveIntegerField(help_text="Number of days this plan lasts")
    target_role = models.CharField(max_length=20, choices=TARGET_ROLE, default="both")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscription_plans"

    def __str__(self):
        return f"{self.name} - {self.duration_type}"


class Payment(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "auth_app.User",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        null=True,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    receipt = models.FileField(upload_to="payment_receipts/")
    payment_method = models.CharField(max_length=100, blank=True, default="",
        help_text="How the user paid (e.g. CCP, BaridiMob, bank transfer).")
    reference_number = models.CharField(max_length=200, blank=True, default="",
        help_text="User-supplied payment reference / transaction number.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    reviewed_by = models.ForeignKey(
        "auth_app.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_payments",
    )
    rejection_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments"

    def __str__(self):
        return f"Payment {self.id} - {self.status}"