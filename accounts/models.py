from django.conf import settings
from django.db import models


class Owner(models.Model):
    slug = models.SlugField(max_length=120, unique=True)  # e.g. gemklub_corvin
    name = models.CharField(max_length=200)               # display name (can equal slug)

    def __str__(self) -> str:
        return self.name


class BoardGame(models.Model):
    class Kind(models.TextChoices):
        STANDALONE = "STANDALONE", "Standalone"
        EXPANSION = "EXPANSION", "Expansion"
        OTHER = "OTHER", "Other"

    # Titles
    title = models.CharField(max_length=255)                 # originalname
    title_local = models.CharField(max_length=255, blank=True, default="")  # objectname
    version_nickname = models.CharField(max_length=255, blank=True, default="")

    # Identifiers / ranking
    objectid = models.PositiveIntegerField(db_index=True)    # BGG id
    rank = models.PositiveIntegerField(null=True, blank=True)

    # Ratings / weight
    rating = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)  # average
    weight = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)  # avgweight

    # Players / time / year
    min_players = models.PositiveSmallIntegerField(null=True, blank=True)
    max_players = models.PositiveSmallIntegerField(null=True, blank=True)
    min_playing_time = models.PositiveSmallIntegerField(null=True, blank=True)
    max_playing_time = models.PositiveSmallIntegerField(null=True, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)  # yearpublished

    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)

    # Optional
    image_url = models.URLField(blank=True, default="")

    # Availability (many owners)
    owners = models.ManyToManyField(Owner, through="OwnerInventory", related_name="games")

    class Meta:
        constraints = [
            # One row per unique “game version”
            models.UniqueConstraint(fields=["objectid", "title"], name="uniq_objectid_version"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.objectid})"


class OwnerInventory(models.Model):
    owner = models.ForeignKey(Owner, on_delete=models.CASCADE)
    game = models.ForeignKey(BoardGame, on_delete=models.CASCADE)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "game"], name="uniq_owner_game"),
        ]


class UserGameStatus(models.Model):
    class Status(models.TextChoices):
        POSITIVE = "POSITIVE", "Positive"
        NEGATIVE = "NEGATIVE", "Negative"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="game_statuses")
    game = models.ForeignKey(BoardGame, on_delete=models.CASCADE, related_name="user_statuses")
    status = models.CharField(max_length=10, choices=Status.choices)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "game"], name="uniq_user_game_status"),
        ]
