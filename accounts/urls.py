from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),

    path("wishlist/", views.wishlist_dashboard, name="wishlist"),
    path("wishlist/<int:game_id>/set-status/", views.set_game_status, name="wishlist_set_status"),
    path("wishlist/not-tried/", views.wishlist_not_tried_chunk, name="wishlist_not_tried_chunk"),
]
