from django.contrib import admin
from django.contrib.sessions.models import Session

from .models import GameResult


@admin.register(GameResult)
class GameResultAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "match_type",
        "room_id",
        "black_player_name",
        "white_player_name",
        "winner",
        "loser",
        "result_reason",
        "time_limit",
        # "black_timeouts",
        # "white_timeouts",
        "created_at",
    )

    list_filter = (
        "match_type",
        "result_reason",
        "winner",
        "created_at",
    )

    search_fields = (
        "room_id",
        "black_player_name",
        "white_player_name",
    )

    ordering = ("-created_at",)

    readonly_fields = (
        "id",
        "match_type",
        "room_id",
        "black_player_name",
        "white_player_name",
        "winner",
        "loser",
        "result_reason",
        "time_limit",
        # "black_timeouts",
        # "white_timeouts",
        "created_at",
    )


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = (
        "session_key",
        "expire_date",
    )

    search_fields = (
        "session_key",
    )

    list_filter = (
        "expire_date",
    )