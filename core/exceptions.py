# App: core | File: exceptions.py
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    request = context.get("request")
    lang = "en"
    if request:
        raw = request.headers.get("Accept-Language", "en")[:2].lower()
        lang = raw if raw in ("en", "ar", "fr") else "en"

    messages = {
        401: {"en": "Authentication credentials were not provided or are invalid.", "ar": "لم يتم تقديم بيانات المصادقة أو أنها غير صالحة.", "fr": "Les informations d'authentification n'ont pas été fournies ou sont invalides."},
        403: {"en": "You do not have permission to perform this action.", "ar": "ليس لديك إذن لتنفيذ هذا الإجراء.", "fr": "Vous n'avez pas la permission d'effectuer cette action."},
        404: {"en": "Resource not found.", "ar": "المورد غير موجود.", "fr": "Ressource introuvable."},
        405: {"en": "Method not allowed.", "ar": "الطريقة غير مسموح بها.", "fr": "Méthode non autorisée."},
        500: {"en": "An internal server error occurred.", "ar": "حدث خطأ داخلي في الخادم.", "fr": "Une erreur interne du serveur s'est produite."},
    }

    if response is not None:
        msg_map = messages.get(response.status_code, {"en": "An error occurred.", "ar": "حدث خطأ.", "fr": "Une erreur s'est produite."})
        return Response(
            {"success": False, "message": msg_map.get(lang, msg_map["en"]), "errors": response.data},
            status=response.status_code,
        )

    msg_map = messages[500]
    return Response(
        {"success": False, "message": msg_map.get(lang, msg_map["en"])},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
