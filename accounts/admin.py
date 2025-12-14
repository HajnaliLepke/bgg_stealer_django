from django.contrib import admin
from .models import WishlistItem

@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = (
        "title", "user", "status", "kind",
        "objectid", "rank", "weight",
        "min_players", "max_players",
        "min_playing_time", "max_playing_time",
        "year",
    )
    list_filter = ("status", "kind")
    search_fields = ("title", "user__username", "user__email", "objectid")
