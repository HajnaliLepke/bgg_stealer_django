from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST

from .models import WishlistItem


def home(request):
    # send logged-in users to wishlist, otherwise to login
    if request.user.is_authenticated:
        return redirect("wishlist")
    return redirect("login")

@login_required
@require_http_methods(["GET"])
def wishlist_dashboard(request):
    q = (request.GET.get("q") or "").strip()

    items = WishlistItem.objects.filter(user=request.user)
    if q:
        items = items.filter(title__icontains=q)

    not_tried = items.filter(status=WishlistItem.Status.NOT_TRIED)
    positive = items.filter(status=WishlistItem.Status.POSITIVE)
    negative = items.filter(status=WishlistItem.Status.NEGATIVE)

    return render(
        request,
        "wishlist.html",
        {
            "q": q,
            "not_tried": not_tried,
            "positive": positive,
            "negative": negative,
        },
    )


@login_required
@require_POST
def set_wishlist_status(request, pk: int):
    item = get_object_or_404(WishlistItem, pk=pk, user=request.user)

    new_status = request.POST.get("status")
    allowed = {c[0] for c in WishlistItem.Status.choices}
    if new_status in allowed:
        item.status = new_status
        item.save(update_fields=["status"])

    # return to where user was (preserve search query, etc.)
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/wishlist/"
    return redirect(next_url)


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
