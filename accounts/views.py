from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST
from django.db.models import Q
from django.core.paginator import Paginator

from .models import BoardGame, UserGameStatus, Owner

PAGE_SIZE = 10

GREEN_BUCKETS = {
    "WANT_TO_TRY",
    "WANT_TO_PLAY_MORE",
    "WANT_TO_BUY",
    "BOUGHT",
}
RED_BUCKETS = {
    "NOT_WANT_TO_TRY",
    "NOT_WANT_TO_PLAY_MORE",
}


def home(request):
    # send logged-in users to wishlist, otherwise to login
    if request.user.is_authenticated:
        return redirect("wishlist")
    return redirect("login")

@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    error = None
    if request.method == "POST":
        identifier = (request.POST.get("identifier") or "").strip()
        password = request.POST.get("password") or ""

        # Allow username OR email
        username = identifier
        if "@" in identifier:
            user_obj = User.objects.filter(email__iexact=identifier).first()
            if user_obj:
                username = user_obj.username

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("home")

        error = "Invalid username/email or password."

    return render(request, "login.html", {"mode": "login", "error": error})


@require_http_methods(["GET", "POST"])
def signup_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    error = None
    if request.method == "POST":
        identifier = (request.POST.get("identifier") or "").strip()
        password = request.POST.get("password") or ""

        # If they typed an email, use it as email and derive a username
        email = identifier if "@" in identifier else ""
        username = identifier.split(
            "@")[0] if "@" in identifier else identifier

        if not username or not password:
            error = "Please fill in all fields."
        elif User.objects.filter(username__iexact=username).exists():
            error = "That username is already taken."
        else:
            user = User.objects.create_user(
                username=username, email=email, password=password)
            login(request, user)
            return redirect("home")

    return render(request, "login.html", {"mode": "signup", "error": error})


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return redirect("login")


def attach_owner_list(qs):
    # returns list of dicts so templates can do game.owner_list easily
    out = []
    for g in qs:
        owners_csv = ", ".join(o.name for o in g.owners.all())
        out.append({"game": g, "owners_csv": owners_csv})
    return out

def _base_filtered_games(request):
    q = (request.GET.get("q") or "").strip()
    owner = (request.GET.get("owner") or "").strip()
    kind = (request.GET.get("kind") or "").strip()

    qs = BoardGame.objects.all()

    if owner:
        qs = qs.filter(owners__slug=owner)

    if kind:
        qs = qs.filter(kind=kind)

    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(title_local__icontains=q) |
            Q(version_nickname__icontains=q)
        )

    # important for M2M joins
    qs = qs.distinct()

    # load owners efficiently for "Available at: ..."
    qs = qs.prefetch_related("owners")

    return qs, q, owner, kind

def _bucket_queryset(games_qs, user, bucket: str):
    """
    bucket is one of:
      - "NOT_TRIED" (special: no status row)
      - any UserGameStatus.Status value
    """
    status_qs = UserGameStatus.objects.filter(user=user)

    if bucket == "NOT_TRIED":
        tried_ids = status_qs.values_list("game_id", flat=True)
        return games_qs.exclude(id__in=tried_ids)

    # bucket is a real status
    ids = status_qs.filter(status=bucket).values_list("game_id", flat=True)
    return games_qs.filter(id__in=ids)

def _bucket_accent(bucket: str) -> str:
    if bucket in GREEN_BUCKETS:
        return "green"
    if bucket in RED_BUCKETS:
        return "red"
    return "primary"

@login_required
def wishlist_dashboard(request):
    games_qs, q, owner, kind = _base_filtered_games(request)

    owners = Owner.objects.order_by("name").all()

    buckets = [
        {"key": "NOT_TRIED", "label": "Not tried yet"},
        {"key": "WANT_TO_TRY", "label": "Want to try"},
        {"key": "WANT_TO_PLAY_MORE", "label": "Want to play more"},
        {"key": "WANT_TO_BUY", "label": "Want to buy"},
        {"key": "BOUGHT", "label": "Bought"},
        {"key": "NOT_WANT_TO_TRY", "label": "Not want to try"},
        {"key": "NOT_WANT_TO_PLAY_MORE", "label": "Not want to play more"},
    ]

    # Initial page for each column
    bucket_pages = {}
    bucket_counts = {}

    for bucket in buckets:
        key = bucket["key"]
        qs = _bucket_queryset(games_qs, request.user, key).order_by("id")
        paginator = Paginator(qs, PAGE_SIZE)
        page = paginator.get_page(1)
        bucket["count"] = paginator.count
        bucket["page"] = page
        bucket["accent"] = _bucket_accent(key)

    return render(
        request,
        "wishlist.html",
        {
            "q": q,
            "owner": owner,
            "kind": kind,
            "owners": owners,

            "buckets": buckets,
            "bucket_pages": bucket_pages,
            "bucket_counts": bucket_counts,
        },
    )

@login_required
def wishlist_bucket_chunk(request, bucket: str):
    # bucket is "NOT_TRIED" or one of status values
    page_num = int(request.GET.get("page") or "1")

    games_qs, q, owner, kind = _base_filtered_games(request)

    qs = _bucket_queryset(games_qs, request.user, bucket).order_by("id")
    paginator = Paginator(qs, PAGE_SIZE)
    page = paginator.get_page(page_num)

    return render(
        request,
        "partials/bucket_chunk.html",
        {
            "bucket": bucket,
            "page_obj": page,
            "accent": _bucket_accent(bucket),
            "q": q,
            "owner": owner,
            "kind": kind,
        },
    )



@login_required
@require_POST
def set_game_status(request, game_id: int):
    game = get_object_or_404(BoardGame, id=game_id)
    new_status = (request.POST.get("status") or "").strip()

    if new_status == "CLEAR":
        UserGameStatus.objects.filter(user=request.user, game=game).delete()
    elif new_status in dict(UserGameStatus.Status.choices):
        UserGameStatus.objects.update_or_create(
            user=request.user,
            game=game,
            defaults={"status": new_status},
        )

    return redirect(request.POST.get("next") or "wishlist")