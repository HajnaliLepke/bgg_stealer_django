from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST
from django.db.models import Q

from .models import BoardGame, UserGameStatus, Owner


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

@login_required
def wishlist_dashboard(request):
    q = (request.GET.get("q") or "").strip()
    owner = (request.GET.get("owner") or "").strip()
    kind = (request.GET.get("kind") or "").strip()

    games = BoardGame.objects.all()
    games = games.prefetch_related("owners")


    if owner:
        games = games.filter(owners__slug=owner)

    if kind:
        games = games.filter(kind=kind)

    if q:
        games = games.filter(
            Q(title__icontains=q) |
            Q(title_local__icontains=q) |
            Q(version_nickname__icontains=q)
        )

    # statuses for this user
    status_qs = UserGameStatus.objects.filter(user=request.user).select_related("game")

    positive_ids = set(status_qs.filter(status=UserGameStatus.Status.POSITIVE).values_list("game_id", flat=True))
    negative_ids = set(status_qs.filter(status=UserGameStatus.Status.NEGATIVE).values_list("game_id", flat=True))
    tried_ids = positive_ids | negative_ids

    positive = games.filter(id__in=positive_ids)
    negative = games.filter(id__in=negative_ids)
    not_tried = games.exclude(id__in=tried_ids)

    not_tried = attach_owner_list(not_tried)
    positive = attach_owner_list(positive)
    negative = attach_owner_list(negative)

    owners = Owner.objects.order_by("name").values_list("name", flat=True).distinct()

    return render(
        request,
        "wishlist.html",
        {
            "q": q,
            "owner": owner,
            "kind": kind,
            "owners": owners,

            "not_tried": not_tried,
            "positive": positive,
            "negative": negative,
        },
    )


@login_required
@require_POST
def set_game_status(request, game_id: int):
    game = get_object_or_404(BoardGame, id=game_id)

    new_status = (request.POST.get("status") or "").strip()

    if new_status == "NOT_TRIED":
        UserGameStatus.objects.filter(user=request.user, game=game).delete()
    elif new_status in {UserGameStatus.Status.POSITIVE, UserGameStatus.Status.NEGATIVE}:
        UserGameStatus.objects.update_or_create(
            user=request.user,
            game=game,
            defaults={"status": new_status},
        )

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/wishlist/"
    return redirect(next_url)