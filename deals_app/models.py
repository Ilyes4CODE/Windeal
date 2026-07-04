# App: deals_app | File: models.py
import uuid
import secrets
from django.db import models
from django.utils import timezone


class Deal(models.Model):
    """
    A discount offer ("Deal" on the client side, "Offer" on the business side).
    Owned by a business user; categorised; price-tracked.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        "auth_app.User",
        on_delete=models.CASCADE,
        related_name="deals",
        limit_choices_to={"role": "business"},
    )
    category = models.ForeignKey(
        "admin_app.Category",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deals",
    )

    title           = models.CharField(max_length=200)
    description     = models.TextField(blank=True, default="")
    image           = models.ImageField(upload_to="deals/", null=True, blank=True)

    discount_value  = models.CharField(max_length=50, default="",
                        help_text="Human-readable label, e.g. '50%' or '-1500 DZD'.")
    old_price       = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    new_price       = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    rating          = models.DecimalField(max_digits=3, decimal_places=2, default=0,
                        help_text="Average rating 0.00 - 5.00.")
    expiry_date     = models.DateField(null=True, blank=True)
    is_active       = models.BooleanField(default=True)
    is_featured     = models.BooleanField(default=False,
                        help_text="Admin-controlled flag. Featured deals appear in the Featured section.")

    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "deals"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Favorite(models.Model):
    """
    A many-to-many between a client user and a Deal, with timestamp.
    Unique pair (user, deal).
    """
    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user    = models.ForeignKey("auth_app.User", on_delete=models.CASCADE, related_name="favorites")
    deal    = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "favorites"
        constraints = [
            models.UniqueConstraint(fields=["user", "deal"], name="unique_user_deal_favorite"),
        ]
        ordering = ["-created_at"]


class RedemptionToken(models.Model):
    """
    One-time QR token a student generates to redeem a deal.
    Expires automatically (default: 10 minutes).
    Mark `used` when scanned by the business.
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user        = models.ForeignKey("auth_app.User", on_delete=models.CASCADE, related_name="redemption_tokens")
    deal        = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="redemption_tokens")
    token       = models.CharField(max_length=128, unique=True, db_index=True)
    expires_at  = models.DateTimeField()
    is_used     = models.BooleanField(default=False)
    used_at     = models.DateTimeField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "redemption_tokens"
        ordering = ["-created_at"]

    @staticmethod
    def make_token() -> str:
        return secrets.token_urlsafe(48)

    def is_valid(self) -> bool:
        return (not self.is_used) and (timezone.now() < self.expires_at)


class Redemption(models.Model):
    """
    Audit log of completed redemptions — used for the business dashboard,
    analytics and recent activity feed.
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business    = models.ForeignKey("auth_app.User", on_delete=models.CASCADE, related_name="received_redemptions")
    student     = models.ForeignKey("auth_app.User", on_delete=models.CASCADE, related_name="made_redemptions")
    deal        = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="redemptions")
    token       = models.ForeignKey(RedemptionToken, on_delete=models.SET_NULL, null=True, blank=True, related_name="redemption")
    status      = models.CharField(max_length=20, default="VERIFIED")
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "redemptions"
        ordering = ["-created_at"]


class Notification(models.Model):
    """
    A per-user in-app notification.
    """
    TYPE_CHOICES = [
        ("system",       "System"),
        ("payment",      "Payment"),
        ("subscription", "Subscription"),
        ("deal",         "Deal"),
        ("redemption",   "Redemption"),
    ]
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user        = models.ForeignKey("auth_app.User", on_delete=models.CASCADE, related_name="notifications")
    title       = models.CharField(max_length=200)
    body        = models.TextField(blank=True, default="")
    type        = models.CharField(max_length=30, choices=TYPE_CHOICES, default="system")
    is_read     = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
