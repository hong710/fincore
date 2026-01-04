from django.urls import path
from .views.transaction_views import transaction_list
from .views.accounts_views import account_list

app_name = "fincore"

urlpatterns = [
    path("transactions/", transaction_list, name="transaction_list"),
    path("accounts/", account_list, name="account_list"),
]
