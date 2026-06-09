import json
import re
import random
import uuid
import time

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt

from .models import GameResult


OFFLINE_ROOM_ID = "offline"


def init_game(first_turn="black", time_limit=None):
    def piece(t, o):
        return {"type": t, "owner": o}

    state = [[None] * 9 for _ in range(9)]

    # base は「黒側から見たときの白側配置」を表す。
    # 白の飛・角は黒側から見ると左に飛、右に角。
    # 黒の配置はこれを180度回転させる必要があるため、
    # y だけでなく x も反転して配置する。
    # これにより、各プレイヤーから見て「左が角、右が飛」になる。
    base = [
        ["香", "桂", "銀", "金", "王", "金", "銀", "桂", "香"],
        ["", "飛", "", "", "", "", "", "角", ""],
        ["歩"] * 9,
    ]

    for y, row in enumerate(base):
        for x, p in enumerate(row):
            if p:
                state[y][x] = piece(p, "white")
                state[8 - y][8 - x] = piece(p, "black")

    return {
        "state": state,
        "hands": {"black": [], "white": []},
        "turn": first_turn,
        "finished": False,
        "winner": None,
        "resigned": None,
        "postgame_choices": {"black": None, "white": None},
        "matchmaking": False,
        "players": {"black": None, "white": None},
        "player_names": {"black": None, "white": None},
        "time_limit": time_limit,
        "turn_started_at": time.time() if time_limit else None,
        "timeouts": {"black": 0, "white": 0},
        "timeout_loser": None,
    }


# オンライン部屋作成用の部屋状態です。
# ルームIDを共有して参加する「オンライン部屋作成」はここで管理します。
manual_rooms = {}

# ランダムマッチング用の部屋状態です。
# 「オンライン対戦」でランダムに相手を探す部屋は、手動作成ルームと分離します。
match_rooms = {}

# ランダムオンライン対戦の待機キューです。
# 実運用ではDBやRedisに保存するのが適切ですが、ローカル開発用としてメモリ上で管理します。
match_waiting = []


def ensure_session_key(request):
    """未ログインユーザーも識別できるよう、Djangoセッションキーを必ず発行します。"""
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def participant_token(request):
    """ルーム参加者をサーバー側で固定するための識別子です。"""
    if request.user.is_authenticated:
        return f"user:{request.user.id}"
    return f"session:{ensure_session_key(request)}"


def participant_display_name(request):
    """画面表示用のユーザー名です。未ログインの場合は None を返します。"""
    if request.user.is_authenticated:
        return request.user.username
    return None


def set_online_session(request, mode, room_id, player):
    request.session["online_mode"] = mode
    request.session["online_room_id"] = room_id
    request.session["online_player"] = player
    request.session.modified = True


def clear_online_session(request):
    for key in ["online_mode", "online_room_id", "online_player"]:
        request.session.pop(key, None)
    request.session.modified = True


def get_session_online_info(request):
    mode = request.session.get("online_mode")
    room_id = request.session.get("online_room_id")
    player = request.session.get("online_player")
    if mode not in ["room", "match"] or not room_id or player not in ["black", "white"]:
        return None, None, None
    return mode, room_id, player


def get_room_store(mode):
    return match_rooms if mode == "match" else manual_rooms


def get_session_online_game(request):
    mode, room_id, player = get_session_online_info(request)
    if not mode:
        return None, None, None, None

    rooms = get_room_store(mode)
    game = rooms.get(room_id)
    if not game:
        return None, None, None, None

    token = participant_token(request)
    players = game.get("players", {})
    if players.get(player) != token:
        return None, None, None, None

    return game, room_id, player, mode


def normalize_side(value):
    if value == "random":
        return random.choice(["black", "white"])
    if value in ["black", "white"]:
        return value
    return "black"


def opposite_side(side):
    return "white" if side == "black" else "black"


def get_manual_game(room_id):
    """オンライン部屋作成用のゲーム状態を取得します。"""
    if not room_id:
        room_id = uuid.uuid4().hex[:6].upper()

    if room_id not in manual_rooms:
        manual_rooms[room_id] = init_game()

    return manual_rooms[room_id]


def get_match_game(room_id):
    """ランダムマッチング用のゲーム状態を取得します。"""
    if not room_id:
        room_id = uuid.uuid4().hex[:6].upper()

    if room_id not in match_rooms:
        match_rooms[room_id] = init_game()

    return match_rooms[room_id]


def get_online_game(room_id, mode="room"):
    if mode == "match":
        return get_match_game(room_id)
    return get_manual_game(room_id)


def get_offline_game(request):
    if "offline_game" not in request.session:
        request.session["offline_game"] = init_game()
        request.session.modified = True

    return request.session["offline_game"]


def save_offline_game(request, game):
    request.session["offline_game"] = game
    request.session.modified = True


def get_request_game(request, room_id, mode="offline"):
    if room_id == OFFLINE_ROOM_ID or mode == "offline":
        return get_offline_game(request)

    return get_online_game(room_id, mode=mode)


def get_piece_moves(state, sx, sy, piece):
    moves = []
    owner = piece["owner"]
    direction = -1 if owner == "black" else 1

    def add(x, y):
        if 0 <= x < 9 and 0 <= y < 9:
            moves.append((x, y))

    def slide(dx, dy):
        x, y = sx + dx, sy + dy
        while 0 <= x < 9 and 0 <= y < 9:
            moves.append((x, y))
            if state[y][x]:
                break
            x += dx
            y += dy

    t = piece["type"]

    if t == "歩":
        add(sx, sy + direction)
    elif t == "香":
        slide(0, direction)
    elif t == "桂":
        add(sx - 1, sy + 2 * direction)
        add(sx + 1, sy + 2 * direction)
    elif t == "銀":
        add(sx, sy + direction)
        add(sx - 1, sy + direction)
        add(sx + 1, sy + direction)
        add(sx - 1, sy - direction)
        add(sx + 1, sy - direction)
    elif t in ["金", "と", "成香", "成桂", "成銀"]:
        add(sx, sy + direction)
        add(sx - 1, sy + direction)
        add(sx + 1, sy + direction)
        add(sx, sy - direction)
        add(sx - 1, sy)
        add(sx + 1, sy)
    elif t == "角":
        slide(1, 1)
        slide(-1, 1)
        slide(1, -1)
        slide(-1, -1)
    elif t == "馬":
        slide(1, 1)
        slide(-1, 1)
        slide(1, -1)
        slide(-1, -1)
        add(sx + 1, sy)
        add(sx - 1, sy)
        add(sx, sy + 1)
        add(sx, sy - 1)
    elif t == "飛":
        slide(1, 0)
        slide(-1, 0)
        slide(0, 1)
        slide(0, -1)
    elif t == "龍":
        slide(1, 0)
        slide(-1, 0)
        slide(0, 1)
        slide(0, -1)
        add(sx + 1, sy + 1)
        add(sx - 1, sy + 1)
        add(sx + 1, sy - 1)
        add(sx - 1, sy - 1)
    elif t == "王":
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx or dy:
                    add(sx + dx, sy + dy)

    return moves


def normalize_time_limit(value, default=None):
    """一手ごとの持ち時間を正規化します。None は無制限を表します。"""
    if value in [None, "", "none", "unlimited"]:
        return default

    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return default

    if seconds < 10 or seconds > 120 or seconds % 10 != 0:
        return default

    return seconds


def reset_turn_timer(game):
    if game.get("time_limit"):
        game["turn_started_at"] = time.time()
    else:
        game["turn_started_at"] = None


def switch_turn(game):
    game["turn"] = opposite_side(game.get("turn", "black"))
    reset_turn_timer(game)


def get_remaining_time(game):
    limit = game.get("time_limit")
    started_at = game.get("turn_started_at")
    if not limit or not started_at or game.get("finished"):
        return None

    remaining = int(limit - (time.time() - started_at) + 0.999)
    return max(0, remaining)


def process_timeouts(game):
    """時間切れをサーバー側で確定します。1回切れるごとに手番を交代し、3回で敗北。"""
    limit = game.get("time_limit")
    if not limit or game.get("finished"):
        return game

    players = game.get("players", {})
    if any(players.get(side) for side in ["black", "white"]) and not all(players.get(side) for side in ["black", "white"]):
        # オンラインで相手が未参加の間は時間を進めない。
        reset_turn_timer(game)
        return game

    if not game.get("turn_started_at"):
        reset_turn_timer(game)
        return game

    while not game.get("finished"):
        remaining = limit - (time.time() - game.get("turn_started_at", time.time()))
        if remaining > 0:
            break

        timeout_player = game.get("turn", "black")
        timeouts = game.setdefault("timeouts", {"black": 0, "white": 0})
        timeouts[timeout_player] = timeouts.get(timeout_player, 0) + 1

        if timeouts[timeout_player] >= 3:
            game["finished"] = True
            game["winner"] = opposite_side(timeout_player)
            game["timeout_loser"] = timeout_player
            break

        switch_turn(game)

    return game


def infer_match_type(game, room_id=None):
    """対戦結果保存用に、現在のゲームがどの対戦種別かを判定します。"""
    if room_id in [None, OFFLINE_ROOM_ID]:
        return "offline"
    if game.get("matchmaking"):
        return "match"
    return "room"


def result_reason(game):
    """ゲーム状態から勝敗理由を判定します。"""
    if game.get("resigned"):
        return "surrender"
    if game.get("timeout_loser"):
        return "timeout"
    return "king_capture"


def player_name_for_result(game, side, match_type):
    """Admin表示用のプレイヤー名を作ります。"""
    names = game.get("player_names", {})
    name = names.get(side)
    if name:
        return name

    if match_type == "offline":
        return "先行" if side == "black" else "後手"

    return "未取得"


def record_game_result(game, room_id=None):
    """勝敗が確定した対戦結果をDBへ1回だけ保存します。

    state_view はポーリングで何度も呼ばれるため、
    game["result_recorded_id"] を使って重複保存を防ぎます。
    """
    if not game.get("finished") or not game.get("winner"):
        return

    if game.get("result_recorded_id"):
        return

    match_type = infer_match_type(game, room_id)
    winner = game.get("winner")
    loser = opposite_side(winner)
    # timeouts = game.get("timeouts", {})

    result = GameResult.objects.create(
        match_type=match_type,
        room_id="" if room_id in [None, OFFLINE_ROOM_ID] else str(room_id),
        black_player_name=player_name_for_result(game, "black", match_type),
        white_player_name=player_name_for_result(game, "white", match_type),
        winner=winner,
        loser=loser,
        result_reason=result_reason(game),
        time_limit=game.get("time_limit"),
        # black_timeouts=timeouts.get("black", 0),
        # white_timeouts=timeouts.get("white", 0),
    )
    game["result_recorded_id"] = result.id



def serialize_game(game, room_id=None):
    process_timeouts(game)
    data = dict(game)
    data["room"] = room_id or OFFLINE_ROOM_ID
    data["remaining_time"] = get_remaining_time(game)
    return data


def apply_move(game, data, player=None):
    process_timeouts(game)
    if game.get("finished"):
        return game

    x, y = data["x"], data["y"]
    selected = data.get("selected")
    selected_hand = data.get("selectedHand")
    promote = data.get("promote", False)

    state = game["state"]
    hands = game["hands"]
    turn = game["turn"]

    # オンライン対戦では、自分の手番以外は操作できない
    if player in ["black", "white"] and player != turn:
        return game

    # ランダムオンライン対戦では、相手が見つかるまで操作不可
    if game.get("matchmaking") and not all(game.get("players", {}).get(side) for side in ["black", "white"]):
        return game

    def is_double_pawn(state, x, owner):
        for yy in range(9):
            p = state[yy][x]
            if p and p["type"] == "歩" and p["owner"] == owner:
                return True
        return False

    def would_cause_double_pawn(state, sx, sy, tx, ty, piece):
        temp = [row[:] for row in state]
        temp[ty][tx] = piece
        temp[sy][sx] = None

        count = 0
        for yy in range(9):
            p = temp[yy][tx]
            if p and p["type"] == "歩" and p["owner"] == piece["owner"]:
                count += 1
        return count >= 2

    # ===== 打ち込み =====
    if selected_hand:
        if selected_hand["owner"] != turn:
            return game

        if state[y][x]:
            return game

        p = hands[selected_hand["owner"]][selected_hand["index"]]

        if p["type"] == "歩" and is_double_pawn(state, x, p["owner"]):
            return game

        state[y][x] = p
        hands[selected_hand["owner"]].pop(selected_hand["index"])
        switch_turn(game)
        return game

    # ===== 移動 =====
    if selected:
        sx, sy = selected["x"], selected["y"]
        piece = state[sy][sx]
        target = state[y][x]

        if not piece:
            return game

        if sx == x and sy == y:
            return game

        # 相手の王将は動かせない
        if piece["type"] == "王" and piece["owner"] != turn:
            return game

        valid_moves = get_piece_moves(state, sx, sy, piece)
        if (x, y) not in valid_moves:
            return game

        # 自分の王将は取れない
        if target and target["type"] == "王" and target["owner"] == turn:
            return game

        # 王将は現在の手番側の駒でしか取れない
        if target and target["type"] == "王" and target["owner"] != turn:
            if piece["owner"] != turn:
                return game

        if piece["type"] == "歩" and would_cause_double_pawn(state, sx, sy, x, y, piece):
            return game

        if promote:
            promote_map = {
                "歩": "と",
                "香": "成香",
                "桂": "成桂",
                "銀": "成銀",
                "角": "馬",
                "飛": "龍",
            }
            if piece["type"] in promote_map:
                piece = {"type": promote_map[piece["type"]], "owner": piece["owner"]}

        if target:
            if target["type"] == "王":
                game["finished"] = True
                game["winner"] = turn
            else:
                demote_map = {
                    "と": "歩",
                    "成香": "香",
                    "成桂": "桂",
                    "成銀": "銀",
                    "馬": "角",
                    "龍": "飛",
                }
                original_type = demote_map.get(target["type"], target["type"])
                hands[turn].append({"type": original_type, "owner": target["owner"]})

        state[y][x] = piece
        state[sy][sx] = None

        if not game["finished"]:
            switch_turn(game)

    return game



def resign_game(game, player=None):
    """投了処理。player が指定されている場合はそのプレイヤーが投了、
    指定がない場合は現在の手番が投了したものとして扱う。"""
    if game.get("finished"):
        return game

    resign_player = player if player in ["black", "white"] else game.get("turn", "black")
    winner = "white" if resign_player == "black" else "black"

    game["finished"] = True
    game["winner"] = winner
    game["resigned"] = resign_player
    return game




def reset_room_for_rematch(old_game):
    """オンライン再戦用に盤面だけ初期化し、プレイヤー情報と持ち時間設定は維持する。"""
    new_game = init_game(first_turn="black", time_limit=old_game.get("time_limit"))
    new_game["players"] = dict(old_game.get("players", {"black": None, "white": None}))
    new_game["player_names"] = dict(old_game.get("player_names", {"black": None, "white": None}))
    new_game["matchmaking"] = old_game.get("matchmaking", False)
    new_game["matched"] = old_game.get("matched", False)
    if "creator_player" in old_game:
        new_game["creator_player"] = old_game.get("creator_player")
    new_game["postgame_choices"] = {"black": None, "white": None}
    return new_game


def json_error(message, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)


def serialize_auth_user(request):
    if request.user.is_authenticated:
        return {"authenticated": True, "username": request.user.username}
    return {"authenticated": False, "username": None}




MIN_PASSWORD_LENGTH = 8
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9]+$")


def is_valid_account_input(username, password):
    """ユーザー登録用の入力検証。

    HTMLの minlength や pattern はブラウザ側の補助にすぎないため、
    必ずサーバー側でも検証する。
    """
    username = (username or "").strip()
    password = password or ""

    if not username or not password:
        return "ユーザー名とパスワードを入力してください。"

    if USERNAME_PATTERN.fullmatch(username) is None:
        return "ユーザー名は英数字のみ使用できます。"

    if len(password) < MIN_PASSWORD_LENGTH:
        return "パスワードは8文字以上で入力してください。"

    return None

def start(request):
    return render(request, "appindex/start.html")

def title(request):
    return render(request, "appindex/title.html")


def login_page(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(request, username=username, password=password)
        if user is None:
            return render(request, "appindex/login.html", {
                "error": "ユーザー名またはパスワードが間違っています。",
                "username": username,
            })

        login(request, user)
        return redirect("title")

    registered = request.GET.get("registered") == "1"
    return render(request, "appindex/login.html", {
        "success": "登録成功" if registered else ""
    })


def register_page(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        validation_error = is_valid_account_input(username, password)
        if validation_error:
            return render(request, "appindex/register.html", {
                "error": validation_error,
                "username": username,
            })

        if User.objects.filter(username=username).exists():
            return render(request, "appindex/register.html", {
                "error": "すでにその名前は使用されています。",
                "username": username,
            })

        # 最終防御：登録直前にも必ず8文字以上を確認する。
        if len(password) < MIN_PASSWORD_LENGTH:
            return render(request, "appindex/register.html", {
                "error": "パスワードは8文字以上で入力してください。",
                "username": username,
            })

        User.objects.create_user(username=username, password=password)
        return redirect("/login?registered=1")

    return render(request, "appindex/register.html")


def index(request):
    # タイトル画面から side 付きで開始したときだけ、
    # ブラウザごとのオフライン盤面を新規作成する。
    # これにより対局中に /shogi を再表示しても、状態が不意に初期化されない。
    if "side" in request.GET:
        first_turn = normalize_side(request.GET.get("side", "black"))
        time_limit = normalize_time_limit(request.GET.get("time_limit"), default=None)
        game = init_game(first_turn=first_turn, time_limit=time_limit)
        save_offline_game(request, game)
    else:
        get_offline_game(request)

    return render(request, "appindex/shogi.html")


def online_room(request):
    """オンライン部屋作成から入る対戦画面。URLには room_id/player を出さず、セッションから取得します。"""
    game, room_id, player, mode = get_session_online_game(request)
    if not game or mode != "room":
        return redirect("title")

    return render(request, "appindex/shogi.html", {
        "online_room": room_id,
        "online_player": player,
        "online_mode": "room",
    })


def match_room(request):
    """ランダムマッチングから入る対戦画面。URLには room_id/player を出さず、セッションから取得します。"""
    if not request.user.is_authenticated:
        return redirect("login_page")

    game, room_id, player, mode = get_session_online_game(request)
    if not game or mode != "match":
        return redirect("title")

    return render(request, "appindex/shogi.html", {
        "online_room": room_id,
        "online_player": player,
        "online_mode": "match",
    })


def create_room(request):
    # オンライン部屋作成はログイン必須。
    # 未ログインの場合はログインページへ移動させる。
    if not request.user.is_authenticated:
        return redirect("login_page")

    creator_side = normalize_side(request.GET.get("side", "black"))
    time_limit = normalize_time_limit(request.GET.get("time_limit"), default=None)
    room_id = uuid.uuid4().hex[:6].upper()
    token = participant_token(request)

    game = init_game(first_turn="black", time_limit=time_limit)
    game["creator_player"] = creator_side
    game["players"][creator_side] = token
    game.setdefault("player_names", {"black": None, "white": None})[creator_side] = participant_display_name(request)
    manual_rooms[room_id] = game

    set_online_session(request, "room", room_id, creator_side)
    return redirect("online_waiting")


def join_room(request):
    room_id = request.GET.get("room", "").strip().upper()
    if not room_id or room_id not in manual_rooms:
        return redirect("title")

    game = manual_rooms[room_id]
    creator_side = game.get("creator_player", "black")
    join_side = opposite_side(creator_side)
    token = participant_token(request)

    game.setdefault("players", {"black": None, "white": None})
    existing = game["players"].get(join_side)
    if existing and existing != token:
        # すでに別ブラウザ/別ユーザーが参加済みの場合は参加させない。
        return redirect("title")

    game["players"][join_side] = token
    game.setdefault("player_names", {"black": None, "white": None})[join_side] = participant_display_name(request)
    reset_turn_timer(game)
    set_online_session(request, "room", room_id, join_side)
    return redirect("online_room")


@csrf_exempt
def online_room_status(request):
    """オンライン部屋作成の参加待機状態を確認します。"""
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "login_required": True}, status=401)

    game, room_id, player, mode = get_session_online_game(request)
    if not game or mode != "room":
        return JsonResponse({"ok": False, "error": "部屋情報が見つかりません。"}, status=404)

    players = game.get("players", {})
    matched = all(players.get(side) for side in ["black", "white"])

    if matched:
        reset_turn_timer(game)

    return JsonResponse({
        "ok": True,
        "matched": matched,
        "redirect": "/online/play",
    })


@csrf_exempt
def online_room_cancel(request):
    """オンライン部屋作成の参加待機を取り消します。"""
    if request.method != "POST":
        return HttpResponseBadRequest("POST method is required")

    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "login_required": True}, status=401)

    game, room_id, player, mode = get_session_online_game(request)

    if game and mode == "room" and room_id in manual_rooms:
        players = game.get("players", {})
        matched = all(players.get(side) for side in ["black", "white"])

        # 相手がまだ参加していない待機中の部屋だけ削除します。
        # すでに成立済みの場合は、部屋削除ではなくセッション解除だけにします。
        if not matched:
            manual_rooms.pop(room_id, None)

    clear_online_session(request)
    return JsonResponse({"ok": True, "redirect": "/"})


@csrf_exempt
def auth_status(request):
    return JsonResponse(serialize_auth_user(request))


@csrf_exempt
def register_user(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST method is required")

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return json_error("入力データが不正です。")

    username = data.get("username", "").strip()
    password = data.get("password", "")

    validation_error = is_valid_account_input(username, password)
    if validation_error:
        return json_error(validation_error)

    if User.objects.filter(username=username).exists():
        return json_error("すでにその名前は使用されています。")

    # 最終防御：API経由でも8文字未満は登録しない。
    if len(password) < MIN_PASSWORD_LENGTH:
        return json_error("パスワードは8文字以上で入力してください。")

    User.objects.create_user(username=username, password=password)
    return JsonResponse({"ok": True, "redirect": "/login?registered=1"})


@csrf_exempt
def login_user(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST method is required")

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return json_error("入力データが不正です。")

    username = data.get("username", "").strip()
    password = data.get("password", "")

    user = authenticate(request, username=username, password=password)
    if user is None:
        return json_error("ユーザーネームまたはパスワードが違います。", status=401)

    login(request, user)
    return JsonResponse({"ok": True, **serialize_auth_user(request)})


def logout_user(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST method is required")

    logout(request)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, **serialize_auth_user(request)})

    return redirect("title")


def online_waiting(request):
    """オンライン対戦の待機画面。

    ランダムマッチングだけでなく、オンライン部屋作成でも、
    相手が参加するまではこの画面で待機します。
    URLには room_id/player を出さず、セッションから参照します。
    """
    if not request.user.is_authenticated:
        return redirect("login_page")

    mode, room_id, player = get_session_online_info(request)
    if mode not in ["room", "match"] or not room_id or player not in ["black", "white"]:
        return redirect("title")

    rooms = get_room_store(mode)
    game = rooms.get(room_id)
    if not game:
        return redirect("title")

    if mode == "room":
        wait_badge = "オンライン部屋作成"
        wait_title = "参加待機中です"
        wait_message = "相手がルームIDを入力して参加するまでお待ちください。"
        wait_info = "相手が参加すると、2秒後に対局画面へ移動します。"
        status_url = "/online/room/status"
        cancel_url = "/online/room/cancel"
    else:
        wait_badge = "オンライン対戦"
        wait_title = "マッチング中です"
        wait_message = "対戦相手を探しています。しばらくお待ちください。"
        wait_info = "対戦相手が見つかり次第、対局画面へ移動します。"
        status_url = "/online/match/status"
        cancel_url = "/online/match/cancel"

    return render(request, "appindex/waiting.html", {
        "online_player": player,
        "online_mode": mode,
        "wait_badge": wait_badge,
        "wait_title": wait_title,
        "wait_message": wait_message,
        "wait_info": wait_info,
        "status_url": status_url,
        "cancel_url": cancel_url,
        # オンライン部屋作成の待機画面だけ、相手に共有する部屋IDを表示する。
        "wait_room_id": room_id if mode == "room" else "",
    })


@csrf_exempt
def random_match(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST method is required")

    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "login_required": True, "error": "オンライン対戦にはログインが必要です。"}, status=401)

    token = participant_token(request)

    # すでに待機中なら待機画面へ戻す。
    for waiting in match_waiting:
        if waiting["token"] == token:
            set_online_session(request, "match", waiting["room"], waiting["player"])
            return JsonResponse({
                "ok": True,
                "matched": False,
                "redirect": "/online/waiting",
            })

    # すでに対戦ルームに入っている場合は、その画面へ戻す。
    for room_id, game in match_rooms.items():
        if game.get("matchmaking") and not game.get("finished"):
            players = game.get("players", {})
            for side in ["black", "white"]:
                if players.get(side) == token:
                    set_online_session(request, "match", room_id, side)
                    return JsonResponse({
                        "ok": True,
                        "matched": all(players.get(s) for s in ["black", "white"]),
                        "redirect": "/online/waiting",
                    })

    # 別ユーザーの待機があればマッチ成立。
    for i, waiting in enumerate(match_waiting):
        if waiting["token"] != token:
            match_waiting.pop(i)
            room_id = waiting["room"]
            waiting_player = waiting["player"]
            player = opposite_side(waiting_player)

            game = match_rooms[room_id]
            game.setdefault("players", {"black": None, "white": None})
            game["players"][player] = token
            game.setdefault("player_names", {"black": None, "white": None})[player] = participant_display_name(request)
            game["matchmaking"] = True
            game["matched"] = True
            reset_turn_timer(game)

            set_online_session(request, "match", room_id, player)
            return JsonResponse({
                "ok": True,
                "matched": True,
                "redirect": "/online/waiting",
            })

    # 待機者がいない場合は新規部屋で待機。
    room_id = uuid.uuid4().hex[:24]
    player = "black"
    game = init_game(first_turn="black", time_limit=90)
    game["matchmaking"] = True
    game["matched"] = False
    game["players"] = {"black": token, "white": None}
    game["player_names"] = {"black": participant_display_name(request), "white": None}
    match_rooms[room_id] = game
    match_waiting.append({"token": token, "room": room_id, "player": player})

    set_online_session(request, "match", room_id, player)
    return JsonResponse({
        "ok": True,
        "matched": False,
        "redirect": "/online/waiting",
    })


@csrf_exempt
def random_match_status(request):
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "login_required": True}, status=401)

    game, room_id, player, mode = get_session_online_game(request)
    if not game or mode != "match":
        return JsonResponse({"ok": False, "error": "マッチング情報が見つかりません。"}, status=404)

    players = game.get("players", {})
    matched = all(players.get(side) for side in ["black", "white"])
    if matched:
        game["matched"] = True

    return JsonResponse({
        "ok": True,
        "matched": matched,
        "redirect": "/match/play",
    })


@csrf_exempt
def random_match_cancel(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST method is required")

    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "login_required": True}, status=401)

    token = participant_token(request)
    mode, room_id, player = get_session_online_info(request)

    # 待機キューから削除する。
    match_waiting[:] = [w for w in match_waiting if w.get("token") != token]

    # まだマッチング成立前ならルームも削除する。
    if mode == "match" and room_id and room_id in match_rooms:
        game = match_rooms[room_id]
        players = game.get("players", {})
        matched = all(players.get(side) for side in ["black", "white"])
        if not matched:
            match_rooms.pop(room_id, None)

    clear_online_session(request)
    return JsonResponse({"ok": True, "redirect": "/"})


def state_view(request):
    game, room_id, player, mode = get_session_online_game(request)
    if game:
        return JsonResponse(serialize_game(game, room_id))

    game = get_offline_game(request)
    data = serialize_game(game, OFFLINE_ROOM_ID)
    save_offline_game(request, game)
    return JsonResponse(data)


@csrf_exempt
def move(request):
    if request.method != "POST":
        game = get_offline_game(request)
        return JsonResponse(serialize_game(game, OFFLINE_ROOM_ID))

    data = json.loads(request.body.decode("utf-8"))

    game, room_id, player, mode = get_session_online_game(request)
    if game:
        apply_move(game, data, player=player)
        return JsonResponse(serialize_game(game, room_id))

    game = get_offline_game(request)
    apply_move(game, data, player=None)
    save_offline_game(request, game)
    return JsonResponse(serialize_game(game, OFFLINE_ROOM_ID))


@csrf_exempt
def reset(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}

    game, room_id, player, mode = get_session_online_game(request)
    if game:
        old_game = game
        new_game = reset_room_for_rematch(old_game)
        if mode == "match":
            match_rooms[room_id] = new_game
        else:
            manual_rooms[room_id] = new_game
        return JsonResponse(serialize_game(new_game, room_id))

    old_game = get_offline_game(request)
    game = init_game(time_limit=old_game.get("time_limit"))
    save_offline_game(request, game)
    return JsonResponse(serialize_game(game, OFFLINE_ROOM_ID))


@csrf_exempt
def postgame_choice(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST method is required")

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        data = {}

    choice = data.get("choice")
    if choice not in ["rematch", "title"]:
        return JsonResponse({"ok": False, "error": "choice must be rematch or title"}, status=400)

    game, room_id, player, mode = get_session_online_game(request)

    # オフライン対戦では、再戦・タイトルのどちらでも即リセットできる。
    if not game:
        old_offline_game = get_offline_game(request)
        offline_game = init_game(time_limit=old_offline_game.get("time_limit"))
        save_offline_game(request, offline_game)
        return JsonResponse({"ok": True, "action": choice, "game": serialize_game(offline_game, OFFLINE_ROOM_ID)})

    if not game.get("finished"):
        return JsonResponse({"ok": True, "action": "not_finished", "game": serialize_game(game, room_id)})

    choices = game.setdefault("postgame_choices", {"black": None, "white": None})
    opponent = opposite_side(player)

    # どちらかが先にタイトルを選んでいた場合、その後の再戦は成立しない。
    if choice == "rematch" and choices.get(opponent) == "title":
        return JsonResponse({"ok": True, "action": "rematch_failed", "game": serialize_game(game, room_id)})

    choices[player] = choice

    if choice == "title":
        clear_online_session(request)
        return JsonResponse({"ok": True, "action": "title", "game": serialize_game(game, room_id)})

    # 両者が再戦を選んだら、同じルーム・同じ色のまま再戦開始。
    if choices.get(opponent) == "rematch":
        new_game = reset_room_for_rematch(game)
        if mode == "match":
            match_rooms[room_id] = new_game
        else:
            manual_rooms[room_id] = new_game
        return JsonResponse({"ok": True, "action": "rematch_started", "game": serialize_game(new_game, room_id)})

    return JsonResponse({"ok": True, "action": "waiting", "game": serialize_game(game, room_id)})


@csrf_exempt
def surrender(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST method is required")

    game, room_id, player, mode = get_session_online_game(request)
    if game:
        resign_game(game, player=player)
        return JsonResponse(serialize_game(game, room_id))

    game = get_offline_game(request)
    resign_game(game)
    save_offline_game(request, game)
    return JsonResponse(serialize_game(game, OFFLINE_ROOM_ID))
