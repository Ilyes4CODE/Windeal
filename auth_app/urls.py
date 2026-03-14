# App: auth_app | File: urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("register/client/", views.register_client, name="register_client"),
    path("register/business/", views.register_business, name="register_business"),
    path("verify/", views.verify_account, name="verify_account"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("profile/", views.get_profile, name="get_profile"),
    path("profile/update/", views.update_profile, name="update_profile"),
    path("payment/upload/", views.upload_payment, name="upload_payment"),
    path("subscription/status/", views.get_subscription_status, name="subscription_status"),
]