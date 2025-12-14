from django.conf import settings
from django.db import models


class WishlistItem(models.Model):
    class Status(models.TextChoices):
        NOT_TRIED = "NOT_TRIED", "Not Tried Yet"
        POSITIVE = "POSITIVE", "Positive"
        NEGATIVE = "NEGATIVE", "Negative"

    class Kind(models.TextChoices):
        STANDALONE = "STANDALONE", "Standalone"
        EXPANSION = "EXPANSION", "Expansion"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items")

    # Core
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.STANDALONE)
    image_url = models.URLField(blank=True)

    # BGG-ish metadata
    objectid = models.PositiveIntegerField(null=True, blank=True, db_index=True)  # BGG id
    year = models.PositiveIntegerField(null=True, blank=True)
    rank = models.PositiveIntegerField(null=True, blank=True)  # overall rank (or whatever you store)
    weight = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)  # e.g. 3.24
    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)

    min_players = models.PositiveSmallIntegerField(null=True, blank=True)
    max_players = models.PositiveSmallIntegerField(null=True, blank=True)

    min_playing_time = models.PositiveSmallIntegerField(null=True, blank=True)  # minutes
    max_playing_time = models.PositiveSmallIntegerField(null=True, blank=True)  # minutes

    # Your workflow status
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_TRIED)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
        ]        

    def __str__(self) -> str:
        return f"{self.objectid}, {self.title}: {self.kind} ({self.user} - {self.status})"