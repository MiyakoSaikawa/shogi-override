from django.db import models


class GameResult(models.Model):
    MATCH_TYPE_CHOICES = [
        ("offline", "オフライン対戦"),
        ("room", "オンライン部屋作成"),
        ("match", "オンライン対戦"),
    ]

    SIDE_CHOICES = [
        ("black", "先手/黒"),
        ("white", "後手/白"),
    ]

    RESULT_REASON_CHOICES = [
        ("king_capture", "王将取得"),
        ("surrender", "投了"),
        ("timeout", "時間切れ"),
    ]

    match_type = models.CharField("対戦種別", max_length=20, choices=MATCH_TYPE_CHOICES, default="offline")
    room_id = models.CharField("ルームID", max_length=64, blank=True)

    black_player_name = models.CharField("先手/黒プレイヤー", max_length=150, blank=True)
    white_player_name = models.CharField("後手/白プレイヤー", max_length=150, blank=True)

    winner = models.CharField("勝者", max_length=10, choices=SIDE_CHOICES)
    loser = models.CharField("敗者", max_length=10, choices=SIDE_CHOICES)
    result_reason = models.CharField("勝敗理由", max_length=20, choices=RESULT_REASON_CHOICES)

    time_limit = models.IntegerField("一手ごとの持ち時間(秒)", null=True, blank=True)
    # black_timeouts = models.IntegerField("先手/黒 時間切れ回数", default=0)
    # white_timeouts = models.IntegerField("後手/白 時間切れ回数", default=0)

    created_at = models.DateTimeField("記録日時", auto_now_add=True)

    class Meta:
        verbose_name = "対戦結果"
        verbose_name_plural = "対戦結果"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_match_type_display()} - {self.get_winner_display()}勝利 ({self.get_result_reason_display()})"
