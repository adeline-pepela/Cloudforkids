from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("", views.pricing, name="pricing"),
    path("mine/", views.my_plan, name="my_plan"),
    # Daraja refuses callback addresses containing "mpesa", "safaricom", "query" and similar words.
    path("pay/confirm/<str:token>/", views.mpesa_callback, name="mpesa_callback"),
    path("pay/payout/result/<str:token>/", views.b2c_result, name="b2c_result"),
    path("pay/payout/timeout/<str:token>/", views.b2c_timeout, name="b2c_timeout"),
    path("pay/balance/result/<str:token>/", views.balance_result, name="balance_result"),
    path("pay/balance/timeout/<str:token>/", views.balance_timeout, name="balance_timeout"),
    path("payment/<int:payment_id>/", views.payment_status, name="payment"),
    path("payment/<int:payment_id>/check/", views.payment_check, name="payment_check"),
    path("payment/<int:payment_id>/simulate/", views.payment_simulate, name="payment_simulate"),
    path("certificate/<str:code>/", views.certificate, name="certificate"),
    path("receipt/<int:payment_id>/", views.receipt, name="receipt"),
    path("sponsor/<str:token>/", views.sponsor, name="sponsor"),
    path("sponsor/payment/<str:token>/", views.sponsor_payment, name="sponsor_payment"),
    path("sponsor/payment/<str:token>/check/", views.sponsor_payment_check, name="sponsor_payment_check"),
    path("sponsor/payment/<str:token>/simulate/", views.sponsor_payment_simulate, name="sponsor_payment_simulate"),
    path("sponsor/receipt/<str:token>/", views.sponsor_receipt, name="sponsor_receipt"),
    path("<slug:slug>/checkout/", views.checkout, name="checkout"),
]
