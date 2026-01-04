from django.contrib import admin

from .models import (
    Account,
    Category,
    ImportBatch,
    ImportRow,
    Transaction,
    TransferGroup,
)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "created_at")
    list_filter = ("kind",)
    search_fields = ("name",)


@admin.register(TransferGroup)
class TransferGroupAdmin(admin.ModelAdmin):
    list_display = ("reference", "created_at")
    search_fields = ("reference",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "kind", "account", "amount", "category", "transfer_group", "source")
    list_filter = ("kind", "source", "account")
    search_fields = ("description",)
    autocomplete_fields = ("account", "category", "transfer_group")


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("filename", "status", "uploaded_at")
    list_filter = ("status",)
    search_fields = ("filename",)


@admin.register(ImportRow)
class ImportRowAdmin(admin.ModelAdmin):
    list_display = ("batch", "id", "created_at")
    list_filter = ("batch",)
    search_fields = ("batch__filename",)
