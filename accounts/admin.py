from django.contrib import admin
from .models import Owner, BoardGame, OwnerInventory, UserGameStatus


@admin.register(Owner)
class OwnerAdmin(admin.ModelAdmin):
    list_display = ("slug", "name")
    search_fields = ("slug", "name")


@admin.register(BoardGame)
class GameAdmin(admin.ModelAdmin):
    list_display = ("title_local", "title", "objectid", "kind", "year", "rank", "rating", "weight", "version_nickname")
    list_filter = ("kind",)
    search_fields = ("title", "title_local", "version_nickname", "objectid")


@admin.register(OwnerInventory)
class OwnerInventoryAdmin(admin.ModelAdmin):
    list_display = ("owner", "game", "imported_at")
    list_filter = ("owner",)
    search_fields = ("owner__slug", "owner__name", "game__title", "game__title_local", "game__objectid")


@admin.register(UserGameStatus)
class UserGameStatusAdmin(admin.ModelAdmin):
    list_display = ("user", "game", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("user__username", "game__title", "game__title_local", "game__objectid")

