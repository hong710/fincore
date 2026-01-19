from django.urls import path
from .views.transaction_views import (
    transaction_list,
    transaction_table,
    transaction_bulk_action,
    transaction_delete,
    transaction_update,
)
from .views.category_views import (
    category_list,
    category_table,
    category_create,
    category_update,
    category_delete,
)
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
    path("transactions/bulk-action/", transaction_bulk_action, name="transaction_bulk_action"),
    path("transactions/<int:pk>/delete/", transaction_delete, name="transaction_delete"),
    path("transactions/update/", transaction_update, name="transaction_update"),
    path("categories/", category_list, name="category_list"),
    path("categories/table/", category_table, name="category_table"),
    path("categories/create/", category_create, name="category_create"),
    path("categories/update/", category_update, name="category_update"),
    path("categories/<int:pk>/delete/", category_delete, name="category_delete"),
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
