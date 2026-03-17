# App: core | File: messages.py
MESSAGES = {
    # ── Registration ──────────────────────────────────────────────────────────
    "user_created": {
        "en": "Account created successfully.",
        "ar": "تم إنشاء الحساب بنجاح.",
        "fr": "Compte créé avec succès.",
    },

    # ── Auth ──────────────────────────────────────────────────────────────────
    "login_success": {
        "en": "Login successful.",
        "ar": "تم تسجيل الدخول بنجاح.",
        "fr": "Connexion réussie.",
    },
    "login_failed": {
        "en": "Invalid credentials.",
        "ar": "بيانات الاعتماد غير صحيحة.",
        "fr": "Identifiants invalides.",
    },
    "user_exists": {
        "en": "Account found.",
        "ar": "تم العثور على الحساب.",
        "fr": "Compte trouvé.",
    },
    "user_not_found": {
        "en": "No account found with this phone number.",
        "ar": "لا يوجد حساب مرتبط بهذا الرقم.",
        "fr": "Aucun compte trouvé avec ce numéro de téléphone.",
    },
    "account_banned": {
        "en": "Your account has been banned. Please contact support.",
        "ar": "تم حظر حسابك. يرجى التواصل مع الدعم.",
        "fr": "Votre compte a été banni. Veuillez contacter le support.",
    },
    "account_inactive": {
        "en": "Account is inactive. Please contact support.",
        "ar": "الحساب غير نشط. يرجى التواصل مع الدعم.",
        "fr": "Compte inactif. Veuillez contacter le support.",
    },
    "logout_success": {
        "en": "Logged out successfully.",
        "ar": "تم تسجيل الخروج بنجاح.",
        "fr": "Déconnexion réussie.",
    },

    # ── Profile ───────────────────────────────────────────────────────────────
    "profile_updated": {
        "en": "Profile updated successfully.",
        "ar": "تم تحديث الملف الشخصي بنجاح.",
        "fr": "Profil mis à jour avec succès.",
    },
    "profile_fetched": {
        "en": "Profile fetched successfully.",
        "ar": "تم جلب الملف الشخصي بنجاح.",
        "fr": "Profil récupéré avec succès.",
    },

    # ── Errors ────────────────────────────────────────────────────────────────
    "phone_exists": {
        "en": "Phone number already registered.",
        "ar": "رقم الهاتف مسجل مسبقاً.",
        "fr": "Numéro de téléphone déjà enregistré.",
    },
    "email_exists": {
        "en": "Email already registered.",
        "ar": "البريد الإلكتروني مسجل مسبقاً.",
        "fr": "Email déjà enregistré.",
    },
    "unauthorized": {
        "en": "You are not authorized to perform this action.",
        "ar": "غير مصرح لك بتنفيذ هذا الإجراء.",
        "fr": "Vous n'êtes pas autorisé à effectuer cette action.",
    },
    "not_found": {
        "en": "Resource not found.",
        "ar": "المورد غير موجود.",
        "fr": "Ressource introuvable.",
    },
    "validation_error": {
        "en": "Validation error.",
        "ar": "خطأ في التحقق.",
        "fr": "Erreur de validation.",
    },
    "server_error": {
        "en": "An internal server error occurred.",
        "ar": "حدث خطأ داخلي في الخادم.",
        "fr": "Une erreur interne du serveur s'est produite.",
    },

    # ── Role guards ───────────────────────────────────────────────────────────
    "admin_only": {
        "en": "This action is restricted to admins only.",
        "ar": "هذا الإجراء مقتصر على المسؤولين فقط.",
        "fr": "Cette action est réservée aux administrateurs uniquement.",
    },
    "business_only": {
        "en": "This action is restricted to business accounts only.",
        "ar": "هذا الإجراء مقتصر على حسابات الأعمال فقط.",
        "fr": "Cette action est réservée aux comptes professionnels uniquement.",
    },
    "client_only": {
        "en": "This action is restricted to client accounts only.",
        "ar": "هذا الإجراء مقتصر على حسابات العملاء فقط.",
        "fr": "Cette action est réservée aux comptes clients uniquement.",
    },
    "banned": {
        "en": "Your account has been banned.",
        "ar": "تم حظر حسابك.",
        "fr": "Votre compte a été banni.",
    },

    # ── Payment ───────────────────────────────────────────────────────────────
    "payment_uploaded": {
        "en": "Payment receipt uploaded successfully. Awaiting admin approval.",
        "ar": "تم رفع إيصال الدفع بنجاح. في انتظار موافقة المسؤول.",
        "fr": "Reçu de paiement téléchargé avec succès. En attente d'approbation.",
    },
    "payment_approved": {
        "en": "Payment approved. Subscription activated.",
        "ar": "تمت الموافقة على الدفع. تم تفعيل الاشتراك.",
        "fr": "Paiement approuvé. Abonnement activé.",
    },
    "payment_rejected": {
        "en": "Payment rejected.",
        "ar": "تم رفض الدفع.",
        "fr": "Paiement rejeté.",
    },
    "payment_already_reviewed": {
        "en": "Payment has already been reviewed.",
        "ar": "تمت مراجعة الدفع مسبقاً.",
        "fr": "Le paiement a déjà été examiné.",
    },
    "invalid_plan": {
        "en": "Selected plan does not exist or is inactive.",
        "ar": "الخطة المحددة غير موجودة أو غير نشطة.",
        "fr": "Le plan sélectionné n'existe pas ou est inactif.",
    },
    "subscription_status_fetched": {
        "en": "Subscription status fetched successfully.",
        "ar": "تم جلب حالة الاشتراك بنجاح.",
        "fr": "Statut d'abonnement récupéré avec succès.",
    },

    # ── Admin panel ───────────────────────────────────────────────────────────
    "plan_created":   {"en": "Plan created successfully.",   "ar": "تم إنشاء الخطة بنجاح.",      "fr": "Plan créé avec succès."},
    "plan_updated":   {"en": "Plan updated successfully.",   "ar": "تم تحديث الخطة بنجاح.",      "fr": "Plan mis à jour avec succès."},
    "plan_deleted":   {"en": "Plan deleted successfully.",   "ar": "تم حذف الخطة بنجاح.",        "fr": "Plan supprimé avec succès."},
    "plan_fetched":   {"en": "Plans fetched successfully.",  "ar": "تم جلب الخطط بنجاح.",        "fr": "Plans récupérés avec succès."},
    "category_created": {"en": "Category created successfully.", "ar": "تم إنشاء الفئة بنجاح.",  "fr": "Catégorie créée avec succès."},
    "category_updated": {"en": "Category updated successfully.", "ar": "تم تحديث الفئة بنجاح.",  "fr": "Catégorie mise à jour avec succès."},
    "category_deleted": {"en": "Category deleted successfully.", "ar": "تم حذف الفئة بنجاح.",    "fr": "Catégorie supprimée avec succès."},
    "category_fetched": {"en": "Categories fetched successfully.", "ar": "تم جلب الفئات بنجاح.", "fr": "Catégories récupérées avec succès."},
    "user_toggled":     {"en": "User status updated successfully.", "ar": "تم تحديث حالة المستخدم بنجاح.", "fr": "Statut de l'utilisateur mis à jour avec succès."},
    "user_banned":      {"en": "User has been banned.",      "ar": "تم حظر المستخدم.",            "fr": "L'utilisateur a été banni."},
    "user_unbanned":    {"en": "User has been unbanned.",    "ar": "تم رفع الحظر عن المستخدم.",   "fr": "L'utilisateur a été débanni."},
    "subscription_updated": {"en": "Subscription status updated successfully.", "ar": "تم تحديث حالة الاشتراك بنجاح.", "fr": "Statut d'abonnement mis à jour avec succès."},
    "users_fetched":    {"en": "Users fetched successfully.", "ar": "تم جلب المستخدمين بنجاح.",   "fr": "Utilisateurs récupérés avec succès."},
    "payments_fetched": {"en": "Payments fetched successfully.", "ar": "تم جلب المدفوعات بنجاح.", "fr": "Paiements récupérés avec succès."},
}


def get_message(key, lang="en"):
    lang = lang if lang in ("en", "ar", "fr") else "en"
    msg  = MESSAGES.get(key, {})
    return msg.get(lang, msg.get("en", "Unknown message."))