from django.urls import path
from .views.transaction_views import transaction_list, transaction_table
from .views.import_views import (
    account_imports,
    import_commit,
    import_review,
    import_rollback,
    import_delete,
    import_stage,
)
from .views.accounts_views import (
    account_list,
    account_create,
    account_table,
    account_archive,
    account_delete,
    account_update,
)

app_name = "fincore"

urlpatterns = [
    path("transactions/", transaction_list, name="transaction_list"),
    path("transactions/table/", transaction_table, name="transaction_table"),
    path("imports/stage/", import_stage, name="import_stage"),
    path("accounts/<int:account_id>/imports/", account_imports, name="account_imports"),
    path("imports/<int:batch_id>/review/", import_review, name="import_review"),
    path("imports/<int:batch_id>/commit/", import_commit, name="import_commit"),
    path("imports/<int:batch_id>/rollback/", import_rollback, name="import_rollback"),
    path("imports/<int:batch_id>/delete/", import_delete, name="import_delete"),
    path("accounts/", account_list, name="account_list"),
    path("accounts/table/", account_table, name="account_table"),
    path("accounts/create/", account_create, name="account_create"),
    path("accounts/update/", account_update, name="account_update"),
    path("accounts/<int:pk>/archive/", account_archive, name="account_archive"),
    path("accounts/<int:pk>/delete/", account_delete, name="account_delete"),
]
