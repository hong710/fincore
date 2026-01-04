from django.urls import path
from .views.transaction_views import transaction_list

app_name = "fincore"

urlpatterns = [
    path("transactions/", transaction_list, name="transaction_list"),
]
