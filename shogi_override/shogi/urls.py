from django.urls import path
from . import views

urlpatterns = [
    path("", views.start, name="start"),
    path("title", views.title, name="title"),
    path("login", views.login_page, name="login_page"),
    path("register", views.register_page, name="register_page"),
    path("shogi", views.index, name="index"),

    # URLには room_id/player を出さず、Djangoセッションから参照します。
    path("online/create", views.create_room, name="create_room"),
    path("online/join", views.join_room, name="join_room"),
    path("online/play", views.online_room, name="online_room"),

    path("online/match", views.random_match, name="random_match"),
    path("online/match/status", views.random_match_status, name="random_match_status"),
    path("online/match/cancel", views.random_match_cancel, name="random_match_cancel"),
    path("online/waiting", views.online_waiting, name="online_waiting"),
    path("online/room/status", views.online_room_status, name="online_room_status"),
    path("online/room/cancel", views.online_room_cancel, name="online_room_cancel"),
    path("match/play", views.match_room, name="match_room"),

    path("auth/status", views.auth_status, name="auth_status"),
    path("auth/register", views.register_user, name="register_user"),
    path("auth/login", views.login_user, name="login_user"),
    path("auth/logout", views.logout_user, name="logout_user"),
    path("state", views.state_view, name="state"),
    path("move", views.move, name="move"),
    path("reset", views.reset, name="reset"),
    path("postgame-choice", views.postgame_choice, name="postgame_choice"),
    path("surrender", views.surrender, name="surrender"),
]
