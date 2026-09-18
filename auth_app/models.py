# App: auth_app | File: models.py
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from datetime import timedelta
import uuid
import secrets


class UserManager(BaseUserManager):
    def create_user(self, phone, role, password=None, **extra_fields):
        if not phone:
            raise ValueError("Phone number is required")
        user = self.model(phone=phone, role=role, **extra_fields)
        # Only admin accounts store a real password.
        # client/business accounts use an unusable password — login is passwordless.
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("role", "admin")
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_verified", True)
        extra_fields.setdefault("is_active", True)
        role = extra_fields.pop("role")
        return self.create_user(phone, role, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ("admin",    "Admin"),
        ("business", "Business"),
        ("client",   "Client"),
    ]

    SUBSCRIPTION_STATUS = [
        ("FREE",    "Free"),
        ("PENDING", "Pending"),
        ("ACTIVE",  "Active"),
        ("EXPIRED", "Expired"),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone           = models.CharField(max_length=20, unique=True, null=True, blank=True)
    email           = models.EmailField(unique=True, null=True, blank=True, db_index=True)
    role            = models.CharField(max_length=20, choices=ROLE_CHOICES)
    # Social sign-in identifiers (provider "sub" / user id).
    google_id       = models.CharField(max_length=255, null=True, blank=True, unique=True)
    apple_id        = models.CharField(max_length=255, null=True, blank=True, unique=True)
    is_verified     = models.BooleanField(default=True)   # client/business are auto-verified on register
    is_active       = models.BooleanField(default=True)
    is_staff        = models.BooleanField(default=False)
    is_banned       = models.BooleanField(default=False,
                        help_text="Banned users cannot log in or access any endpoint.")
    profile_picture = models.ImageField(upload_to="profile_pictures/", null=True, blank=True)
    city            = models.CharField(max_length=100, null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)
    subscription_status = models.CharField(max_length=20, choices=SUBSCRIPTION_STATUS, default="FREE")
    subscription_end    = models.DateTimeField(null=True, blank=True)
    current_plan        = models.ForeignKey(
        "admin_app.SubscriptionPlan",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="subscribed_users",
    )

    USERNAME_FIELD  = "phone"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = "users"

    def __str__(self):
        return f"{self.phone} ({self.role})"


class ClientProfile(models.Model):
    user            = models.OneToOneField(User, on_delete=models.CASCADE, related_name="client_profile")
    full_name       = models.CharField(max_length=200)
    email           = models.EmailField(unique=True, null=True, blank=True)
    wilaya          = models.CharField(max_length=100,
                        help_text="Algerian province / state (wilaya).")
    school          = models.CharField(max_length=200, null=True, blank=True,
                        help_text="School or university name (optional).")

    class Meta:
        db_table = "client_profiles"

    def __str__(self):
        return self.full_name


class BusinessProfile(models.Model):
    user          = models.OneToOneField(User, on_delete=models.CASCADE, related_name="business_profile")
    business_name = models.CharField(max_length=200)
    description   = models.TextField(null=True, blank=True)
    category      = models.ForeignKey(
        "admin_app.Category",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="businesses",
    )
    address   = models.CharField(max_length=300, null=True, blank=True)
    website   = models.URLField(null=True, blank=True)
    latitude  = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True,
                  help_text="Latitude for Google Maps pin (e.g. 36.737232).")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True,
                  help_text="Longitude for Google Maps pin (e.g. 3.086472).")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "business_profiles"

    def __str__(self):
        return self.business_name


class EmailOTP(models.Model):
    """
    One-time 6-digit code emailed to a user for passwordless email login /
    registration. Valid for 10 minutes and single-use.
    """
    PURPOSE_CHOICES = [
        ("login",             "Login"),
        ("register_client",   "Register Client"),
        ("register_business", "Register Business"),
    ]

    email      = models.EmailField(db_index=True)
    otp        = models.CharField(max_length=6)
    purpose    = models.CharField(max_length=30, choices=PURPOSE_CHOICES, default="login")
    is_used    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "email_otps"
        indexes = [models.Index(fields=["email", "otp", "is_used"])]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} · {self.purpose} · {'used' if self.is_used else 'active'}"

    def is_valid(self):
        return (not self.is_used) and (timezone.now() - self.created_at) < timedelta(minutes=10)

    @classmethod
    def generate_otp(cls, email, purpose="login"):
        # Invalidate previous unused codes for this email + purpose.
        cls.objects.filter(email=email, purpose=purpose, is_used=False).update(is_used=True)
        code = f"{secrets.randbelow(900000) + 100000}"   # cryptographically secure 6 digits
        return cls.objects.create(email=email, otp=code, purpose=purpose)

    @classmethod
    def recent_count(cls, email, minutes=10):
        """How many codes were sent to this email in the last `minutes` (rate-limit)."""
        since = timezone.now() - timedelta(minutes=minutes)
        return cls.objects.filter(email=email, created_at__gte=since).count()