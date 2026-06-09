let state, hands, turn;
let selected = null;
let selectedHand = null;
let game = null;

const CONFIG = window.SHOGI_CONFIG || { mode: "offline", room: "offline", player: null };
const IS_ONLINE = CONFIG.mode === "room" || CONFIG.mode === "match";
const IS_RANDOM_MATCH = CONFIG.mode === "match";
const IS_MANUAL_ROOM = CONFIG.mode === "room";
const ROOM_ID = CONFIG.room || "offline";
const PLAYER = CONFIG.player || null;

const PROMOTE_MAP = {
  "歩": "と",
  "香": "成香",
  "桂": "成桂",
  "銀": "成銀",
  "角": "馬",
  "飛": "龍"
};

function canPromote(piece) {
  return PROMOTE_MAP[piece.type] !== undefined;
}

function inPromotionZone(y, owner) {
  return owner === "black" ? y <= 2 : y >= 6;
}

function buildUrl(path) {
  return path;
}

function playerLabel(value) {
  if (!value) return "";

  // オンライン対戦では、黒/白ではなくユーザー名を優先して表示します。
  // ユーザー名がない場合、自分は「あなた」、相手は「相手」と表示します。
  if (IS_ONLINE) {
    const names = (game && game.player_names) ? game.player_names : {};
    if (names[value]) return names[value];
    if (PLAYER && value === PLAYER) return "あなた";
    if (PLAYER && value !== PLAYER) return "相手";
  }

  if (value === "black") return "先行";
  if (value === "white") return "後手";
  return "";
}

function opponentSide(side) {
  return side === "black" ? "white" : "black";
}

function isBoardRotatedForPlayer() {
  return IS_ONLINE && PLAYER === "white";
}

function boardCoordForDisplay(displayX, displayY) {
  if (isBoardRotatedForPlayer()) {
    return { x: 8 - displayX, y: 8 - displayY };
  }
  return { x: displayX, y: displayY };
}

function pieceText(piece) {
  if (!piece) return "";

  // オンライン対戦では、各プレイヤーの視点で表示する。
  // 自分の駒は▽なし、相手の駒は▽あり。
  if (IS_ONLINE && PLAYER) {
    return piece.owner === PLAYER ? piece.type : "▽" + piece.type;
  }

  // オフライン対戦では従来通り、黒は▽なし、白は▽あり。
  return piece.owner === "black" ? piece.type : "▽" + piece.type;
}

const PIECE_IMAGE_MAP = {
  "歩": "hu.png",
  "香": "kyousha.png",
  "桂": "keima.png",
  "銀": "gin.png",
  "金": "kin.png",
  "角": "kaku.png",
  "飛": "hisha.png",
  "と": "tokin.png",
  "成香": "narikyou.png",
  "成桂": "narikei.png",
  "成銀": "narigin.png",
  "馬": "ryouma.png",
  "龍": "ryuuou.png"
};

function pieceImageFile(piece) {
  if (!piece) return "";

  // 王将は先手側（black）を ou.png、後手側（white）を gyoku.png として扱う。
  // gyoku.png が無い場合は onerror で ou.png にフォールバックする。
  if (piece.type === "王") {
    return piece.owner === "black" ? "ou.png" : "gyoku.png";
  }

  return PIECE_IMAGE_MAP[piece.type] || "";
}

function shouldRotatePiece(piece) {
  if (!piece) return false;

  // オンラインでは、相手の駒だけ180度回転させる。
  if (IS_ONLINE && PLAYER) {
    return piece.owner !== PLAYER;
  }

  // オフラインでは従来表示に合わせ、白側の駒を180度回転させる。
  return piece.owner === "white";
}

function createPieceNode(piece, count = 0) {
  const wrap = document.createElement("div");
  wrap.className = "piece-visual";

  if (!piece) return wrap;

  const fileName = pieceImageFile(piece);
  const fallbackText = pieceText(piece);

  if (fileName) {
    const img = document.createElement("img");
    img.className = "piece-img";
    img.draggable = false;
    img.setAttribute("draggable", "false");
    if (shouldRotatePiece(piece)) img.classList.add("rotated");
    img.alt = fallbackText;
    img.src = `/static/images/${fileName}`;

    img.onerror = () => {
      if (piece.type === "王" && fileName === "gyoku.png") {
        img.onerror = null;
        img.src = "/static/images/ou.png";
        return;
      }

      img.remove();
      const fallback = document.createElement("span");
      fallback.className = "piece-fallback";
      if (shouldRotatePiece(piece)) fallback.classList.add("rotated");
      fallback.textContent = fallbackText;
      wrap.appendChild(fallback);
    };

    wrap.appendChild(img);
  } else {
    const fallback = document.createElement("span");
    fallback.className = "piece-fallback";
    if (shouldRotatePiece(piece)) fallback.classList.add("rotated");
    fallback.textContent = fallbackText;
    wrap.appendChild(fallback);
  }

  if (count > 1) {
    const badge = document.createElement("span");
    badge.className = "piece-count-badge";
    badge.textContent = `×${count}`;
    wrap.appendChild(badge);
  }

  return wrap;
}

function updateHandLabels() {
  const labels = document.querySelectorAll(".handLabel");
  if (labels.length < 2) return;

  if (IS_ONLINE && PLAYER) {
    const opponent = opponentSide(PLAYER);
    labels[0].textContent = `${playerLabel(opponent)}の持ち駒`;
    labels[1].textContent = `${playerLabel(PLAYER)}の持ち駒`;
  } else {
    labels[0].textContent = "後手の持ち駒";
    labels[1].textContent = "先行の持ち駒";
  }
}

function isWaitingForOpponent() {
  if (!IS_ONLINE || !game || !game.matchmaking) return false;
  const players = game.players || {};
  return !(players.black && players.white);
}

function buildResultMessage() {
  if (!game || !game.finished) return "";

  let message;

  // オンライン対戦では、勝者側は従来どおり「◯◯ win」、
  // 敗者側は「You lose」と表示する。
  if (IS_ONLINE && PLAYER && game.winner && PLAYER !== game.winner) {
    message = "You lose";
  } else {
    const winnerText = playerLabel(game.winner);
    message = `${winnerText} win`;
  }

  if (game.resigned) {
    if (IS_ONLINE && PLAYER === game.winner) {
      message += `<br><span class="result-subtext">相手が投了しました</span>`;
    } else if (IS_ONLINE && PLAYER === game.resigned) {
      message += `<br><span class="result-subtext">あなたが投了しました</span>`;
    } else {
      message += `<br><span class="result-subtext">${playerLabel(game.resigned)}が投了しました</span>`;
    }
  }

  if (game.timeout_loser) {
    if (IS_ONLINE && PLAYER === game.timeout_loser) {
      message += `<br><span class="result-subtext">時間切れが3回になりました</span>`;
    } else if (IS_ONLINE && PLAYER === game.winner) {
      message += `<br><span class="result-subtext">相手の時間切れが3回になりました</span>`;
    } else {
      message += `<br><span class="result-subtext">${playerLabel(game.timeout_loser)}の時間切れが3回になりました</span>`;
    }
  }

  if (IS_ONLINE && PLAYER) {
    const myChoice = getMyPostgameChoice();
    const opponentChoice = getOpponentPostgameChoice();

    if (myChoice === "rematch" && !opponentChoice) {
      message += `<br><span class="result-subtext">相手の選択を待っています</span>`;
    } else if (!myChoice && opponentChoice === "rematch") {
      message += `<br><span class="result-subtext">相手が再戦を希望しています</span>`;
    } else if (opponentChoice === "title") {
      message += `<br><span class="result-subtext">相手はタイトルに戻りました</span>`;
    }
  }

  return message;
}

function showConfirmModal({ title, message = "", okText = "OK", cancelText = "キャンセル" }) {
  const overlay = document.getElementById("confirmOverlay");
  const titleEl = document.getElementById("confirmTitle");
  const messageEl = document.getElementById("confirmMessage");
  const okBtn = document.getElementById("confirmOkBtn");
  const cancelBtn = document.getElementById("confirmCancelBtn");

  if (!overlay || !titleEl || !messageEl || !okBtn || !cancelBtn) {
    return Promise.resolve(window.confirm(title));
  }

  titleEl.textContent = title;
  messageEl.textContent = message;
  okBtn.textContent = okText;
  cancelBtn.textContent = cancelText;
  cancelBtn.style.display = cancelText ? "" : "none";
  overlay.classList.remove("hidden");

  return new Promise((resolve) => {
    function close(result) {
      overlay.classList.add("hidden");
      cancelBtn.style.display = "";
      okBtn.removeEventListener("click", onOk);
      cancelBtn.removeEventListener("click", onCancel);
      overlay.removeEventListener("click", onOverlayClick);
      resolve(result);
    }

    function onOk() {
      close(true);
    }

    function onCancel() {
      close(false);
    }

    function onOverlayClick(e) {
      if (e.target === overlay) close(false);
    }

    okBtn.addEventListener("click", onOk);
    cancelBtn.addEventListener("click", onCancel);
    overlay.addEventListener("click", onOverlayClick);
  });
}

function confirmSurrenderModal(message = "投了すると相手の勝利になります。") {
  return showConfirmModal({
    title: "本当に投了しますか？",
    message,
    okText: "投了する",
    cancelText: "キャンセル"
  });
}

function confirmPromotionModal() {
  return showConfirmModal({
    title: "成りますか？",
    message: "この駒を成る場合は「成る」を選択してください。",
    okText: "成る",
    cancelText: "成らない"
  });
}


function showInfoModal(title, message = "", okText = "OK") {
  return showConfirmModal({
    title,
    message,
    okText,
    cancelText: ""
  });
}

function getPostgameChoices() {
  return (game && game.postgame_choices) ? game.postgame_choices : {};
}

function getOpponentPlayer() {
  if (!PLAYER) return null;
  return PLAYER === "black" ? "white" : "black";
}

function getMyPostgameChoice() {
  const choices = getPostgameChoices();
  return PLAYER ? choices[PLAYER] : null;
}

function getOpponentPostgameChoice() {
  const choices = getPostgameChoices();
  const opponent = getOpponentPlayer();
  return opponent ? choices[opponent] : null;
}

let postgameRedirecting = false;
async function handlePostgameStateAfterFetch() {
  if (!IS_ONLINE || !game || !game.finished || postgameRedirecting) return;

  const myChoice = getMyPostgameChoice();
  const opponentChoice = getOpponentPostgameChoice();

  if (myChoice === "rematch" && opponentChoice === "title") {
    postgameRedirecting = true;
    await showInfoModal("再戦できませんでした", "タイトルに戻ります。", "OK");
    window.location.href = "/";
  }
}

function formatRemainingTime(seconds) {
  if (seconds === null || seconds === undefined) return "無制限";
  const value = Math.max(0, Number(seconds) || 0);
  return `${value}秒`;
}

function timeoutCountText() {
  if (!game || !game.timeouts) return "";
  const black = game.timeouts.black || 0;
  const white = game.timeouts.white || 0;
  if (IS_ONLINE && PLAYER) {
    const me = game.timeouts[PLAYER] || 0;
    const opponent = game.timeouts[opponentSide(PLAYER)] || 0;
    return `　時間切れ: あなた ${me}/3・相手 ${opponent}/3`;
  }
  return `　時間切れ: 先行 ${black}/3・後手 ${white}/3`;
}


async function fetchState() {
  const res = await fetch(buildUrl("/state"));
  const data = await res.json();

  const previousTurn = turn;
  game = data;
  state = data.state;
  hands = data.hands;
  turn = data.turn;
  if (previousTurn && previousTurn !== turn) {
    clearClickSelection();
  }

  render();
  handlePostgameStateAfterFetch();
}

function render() {
  const board = document.getElementById("board");
  board.innerHTML = "";

  updateHandLabels();

  const matchInfo = document.getElementById("matchInfo");
  if (matchInfo) {
    if (IS_ONLINE) {
      const waitingText = isWaitingForOpponent() ? '　<span class="waiting-text">マッチング中：相手を待っています</span>' : '';
      const modeLabel = IS_RANDOM_MATCH ? "オンライン対戦" : "オンライン部屋対戦";
      const roomText = IS_MANUAL_ROOM ? `　ルームID: <strong>${ROOM_ID}</strong>` : "";
      matchInfo.innerHTML = `${modeLabel}${roomText}　あなた: <strong>${playerLabel(PLAYER)}</strong>${waitingText}`;
    } else {
      matchInfo.textContent = "オフライン対戦";
    }
  }

  const turnDisplay = document.getElementById("turnDisplay");
  if (turnDisplay) {
    if (isWaitingForOpponent()) {
      turnDisplay.textContent = "相手を待っています";
    } else if (IS_ONLINE && PLAYER !== turn && !(game && game.finished)) {
      turnDisplay.textContent = `${playerLabel(turn)}の番（相手の手番です）`;
    } else {
      turnDisplay.textContent = `${playerLabel(turn)}の番`;
    }
  }

  const timerDisplay = document.getElementById("timerDisplay");
  if (timerDisplay) {
    if (game && game.finished) {
      timerDisplay.textContent = "";
    } else if (isWaitingForOpponent()) {
      timerDisplay.textContent = "";
    } else if (game && game.time_limit) {
      timerDisplay.textContent = `残り時間: ${formatRemainingTime(game.remaining_time)}${timeoutCountText()}`;
      timerDisplay.classList.toggle("timer-warning", Number(game.remaining_time) <= 10);
    } else {
      timerDisplay.textContent = "残り時間: 無制限";
      timerDisplay.classList.remove("timer-warning");
    }
  }

  const validMoves = getValidMoves();
  const overlay = document.getElementById("overlay");
  const resultText = document.getElementById("resultText");

  if (game && game.finished) {
    if (resultText) resultText.innerHTML = buildResultMessage();
    if (overlay) overlay.classList.remove("hidden");
  } else {
    if (overlay) overlay.classList.add("hidden");
  }

  const resetBtn = document.getElementById("resetBtn");
  if (resetBtn) {
    resetBtn.textContent = IS_ONLINE ? "再戦する" : "リセット";
    resetBtn.disabled = Boolean(IS_ONLINE && getMyPostgameChoice() === "rematch");
  }

  const surrenderBtn = document.getElementById("surrenderBtn");
  if (surrenderBtn) {
    surrenderBtn.disabled = Boolean((game && game.finished) || isWaitingForOpponent());
    surrenderBtn.textContent = "投了";
  }

  // オンラインでは自分の駒が下、相手の駒が上になるように盤面を回転表示します。
  for (let displayY = 0; displayY < 9; displayY++) {
    const tr = document.createElement("tr");

    for (let displayX = 0; displayX < 9; displayX++) {
      const coord = boardCoordForDisplay(displayX, displayY);
      const x = coord.x;
      const y = coord.y;
      const cell = state[y][x];

      const td = document.createElement("td");
      if (cell) {
        td.appendChild(createPieceNode(cell));
      }

      if (selected && selected.x === x && selected.y === y) {
        td.classList.add("selected");
      }

      if (validMoves.some(m => m.x === x && m.y === y)) {
        td.classList.add("valid");
      }

      td.dataset.x = x;
      td.dataset.y = y;
      td.addEventListener("click", (e) => onBoardClick(e, x, y));

      tr.appendChild(td);
    }

    board.appendChild(tr);
  }

  renderHands();
}

function groupHands(hand) {
  const map = {};

  hand.forEach((p, i) => {
    const key = p.type + "_" + p.owner;

    if (!map[key]) {
      map[key] = {
        type: p.type,
        owner: p.owner,
        count: 0,
        indices: []
      };
    }

    map[key].count++;
    map[key].indices.push(i);
  });

  return Object.values(map);
}

function renderHands() {
  const leftHand = document.getElementById("whiteHand");
  const rightHand = document.getElementById("blackHand");

  leftHand.innerHTML = "";
  rightHand.innerHTML = "";

  // オンラインでは「左＝相手の持ち駒」「右＝自分の持ち駒」にします。\n  // オフラインでは従来通り「左＝白」「右＝黒」です。
  const leftOwner = IS_ONLINE && PLAYER ? opponentSide(PLAYER) : "white";
  const rightOwner = IS_ONLINE && PLAYER ? PLAYER : "black";

  groupHands(hands[leftOwner]).forEach(group => {
    const el = document.createElement("div");
    el.className = "piece hand-piece";
    el.appendChild(createPieceNode(group, group.count));

    if (selectedHand && selectedHand.owner === leftOwner && selectedHand.index === group.indices[0]) {
      el.classList.add("selected");
    }
    el.addEventListener("click", (e) => onHandClick(e, leftOwner, group.indices[0]));
    leftHand.appendChild(el);
  });

  groupHands(hands[rightOwner]).forEach(group => {
    const el = document.createElement("div");
    el.className = "piece hand-piece";
    el.appendChild(createPieceNode(group, group.count));

    if (selectedHand && selectedHand.owner === rightOwner && selectedHand.index === group.indices[0]) {
      el.classList.add("selected");
    }
    el.addEventListener("click", (e) => onHandClick(e, rightOwner, group.indices[0]));
    rightHand.appendChild(el);
  });
}

function isDoublePawn(state, x, owner) {
  for (let y = 0; y < 9; y++) {
    const p = state[y][x];
    if (p && p.type === "歩" && p.owner === owner) return true;
  }
  return false;
}

function wouldCauseDoublePawn(state, sx, sy, tx, ty, piece) {
  const temp = state.map(row => row.slice());
  temp[ty][tx] = piece;
  temp[sy][sx] = null;

  let count = 0;
  for (let y = 0; y < 9; y++) {
    const p = temp[y][tx];
    if (p && p.type === "歩" && p.owner === piece.owner) count++;
  }
  return count >= 2;
}

function getActiveMoveContext() {
  if (selected) {
    const piece = state[selected.y][selected.x];
    if (!piece) return null;
    return { piece, source: { type: "board", x: selected.x, y: selected.y } };
  }

  if (selectedHand) {
    const piece = hands[selectedHand.owner][selectedHand.index];
    if (!piece) return null;
    return { piece, source: { type: "hand", owner: selectedHand.owner, index: selectedHand.index } };
  }

  return null;
}

function getValidMoves() {
  const moves = [];
  const context = getActiveMoveContext();

  if (!context) return moves;

  const piece = context.piece;
  const source = context.source;

  if (IS_ONLINE && PLAYER !== turn) return moves;
  if (isWaitingForOpponent()) return moves;

  // ===== 持ち駒 =====
  if (source.type === "hand") {
    const p = piece;

    for (let y = 0; y < 9; y++) {
      for (let x = 0; x < 9; x++) {
        if (state[y][x]) continue;
        if (p.type === "歩" && isDoublePawn(state, x, p.owner)) continue;
        moves.push({ x, y });
      }
    }
    return moves;
  }

  // ===== 盤面移動 =====
  if (source.type === "board") {
    const rawMoves = getPieceMoves(piece, source.x, source.y);

    for (const m of rawMoves) {
      if (m.x === source.x && m.y === source.y) continue;

      const target = state[m.y][m.x];

      // 自分の王将は取れない
      if (target && target.type === "王" && target.owner === turn) continue;

      // 王将は現在の手番側の駒でしか取れない
      if (target && target.type === "王" && target.owner !== turn && piece.owner !== turn) continue;

      if (piece.type === "歩") {
        if (wouldCauseDoublePawn(state, source.x, source.y, m.x, m.y, piece)) continue;
      }

      moves.push(m);
    }
  }

  return moves;
}

async function handleClickDrop(x, y) {
  const context = getActiveMoveContext();
  if (!context) return;

  const source = { ...context.source };
  const piece = { ...context.piece };

  const timerDisplay = document.getElementById("timerDisplay");
  if (timerDisplay) {
    if (game && game.finished) {
      timerDisplay.textContent = "";
    } else if (isWaitingForOpponent()) {
      timerDisplay.textContent = "";
    } else if (game && game.time_limit) {
      timerDisplay.textContent = `残り時間: ${formatRemainingTime(game.remaining_time)}${timeoutCountText()}`;
      timerDisplay.classList.toggle("timer-warning", Number(game.remaining_time) <= 10);
    } else {
      timerDisplay.textContent = "残り時間: 無制限";
      timerDisplay.classList.remove("timer-warning");
    }
  }

  const validMoves = getValidMoves();
  if (!validMoves.some(m => m.x === x && m.y === y)) return;

  if (source.type === "board") {
    if (source.x === x && source.y === y) return;

    clearClickSelection();

    let promote = false;
    if (
      canPromote(piece) &&
      (inPromotionZone(source.y, piece.owner) || inPromotionZone(y, piece.owner))
    ) {
      promote = await confirmPromotionModal();
    }

    sendMove({
      selected: { x: source.x, y: source.y },
      selectedHand: null,
      x,
      y,
      promote
    });
  } else {
    clearClickSelection();
    sendMove({
      selected: null,
      selectedHand: {
        owner: source.owner,
        index: source.index
      },
      x,
      y,
      promote: false
    });
  }
}

function clearClickSelection() {
  selected = null;
  selectedHand = null;
}

function canSelectBoardPiece(piece) {
  if (!piece) return false;
  if (game && game.finished) return false;
  if (IS_ONLINE && PLAYER !== turn) return false;
  if (isWaitingForOpponent()) return false;

  // 相手の王将は動かせない
  if (piece.type === "王" && piece.owner !== turn) return false;

  return true;
}

function onBoardClick(e, x, y) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

  if (game && game.finished) return;
  if (IS_ONLINE && PLAYER !== turn) return;
  if (isWaitingForOpponent()) return;

  const target = state[y][x];

  // 同じ盤上の駒をもう一度クリックしたら選択解除
  if (selected && selected.x === x && selected.y === y) {
    clearClickSelection();
    render();
    return;
  }

  // すでに盤上の駒または持ち駒を選択している場合
  if (selected || selectedHand) {
    const timerDisplay = document.getElementById("timerDisplay");
  if (timerDisplay) {
    if (game && game.finished) {
      timerDisplay.textContent = "";
    } else if (isWaitingForOpponent()) {
      timerDisplay.textContent = "";
    } else if (game && game.time_limit) {
      timerDisplay.textContent = `残り時間: ${formatRemainingTime(game.remaining_time)}${timeoutCountText()}`;
      timerDisplay.classList.toggle("timer-warning", Number(game.remaining_time) <= 10);
    } else {
      timerDisplay.textContent = "残り時間: 無制限";
      timerDisplay.classList.remove("timer-warning");
    }
  }

  const validMoves = getValidMoves();

    // 合法手なら移動・打ち込み
    if (validMoves.some(m => m.x === x && m.y === y)) {
      handleClickDrop(x, y);
      return;
    }

    // 非合法マスでも、選択可能な盤上の駒なら選び直す
    if (canSelectBoardPiece(target)) {
      selected = { x, y };
      selectedHand = null;
      render();
      return;
    }

    // 空マスや選択不可の駒をクリックしたら選択解除
    clearClickSelection();
    render();
    return;
  }

  // 未選択状態なら、選択可能な駒だけ選択
  if (canSelectBoardPiece(target)) {
    selected = { x, y };
    selectedHand = null;
    render();
  }
}

function onHandClick(e, owner, index) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

  if (game && game.finished) return;
  if (IS_ONLINE && PLAYER !== turn) return;
  if (isWaitingForOpponent()) return;
  if (owner !== turn) return;

  // 同じ持ち駒をもう一度クリックしたら選択解除
  if (selectedHand && selectedHand.owner === owner && selectedHand.index === index) {
    clearClickSelection();
    render();
    return;
  }

  selected = null;
  selectedHand = { owner, index };
  render();
}

function getPieceMoves(piece, sx, sy) {
  const moves = [];
  const dir = piece.owner === "black" ? -1 : 1;

  function add(x, y) {
    if (x < 0 || x >= 9 || y < 0 || y >= 9) return;
    moves.push({ x, y });
  }

  function slide(dx, dy) {
    let x = sx + dx;
    let y = sy + dy;

    while (x >= 0 && x < 9 && y >= 0 && y < 9) {
      moves.push({ x, y });
      if (state[y][x]) break;
      x += dx;
      y += dy;
    }
  }

  switch (piece.type) {
    case "歩":
      add(sx, sy + dir);
      break;
    case "香":
      slide(0, dir);
      break;
    case "桂":
      add(sx - 1, sy + 2 * dir);
      add(sx + 1, sy + 2 * dir);
      break;
    case "銀":
      add(sx, sy + dir);
      add(sx - 1, sy + dir);
      add(sx + 1, sy + dir);
      add(sx - 1, sy - dir);
      add(sx + 1, sy - dir);
      break;
    case "金":
    case "と":
    case "成香":
    case "成桂":
    case "成銀":
      add(sx, sy + dir);
      add(sx - 1, sy + dir);
      add(sx + 1, sy + dir);
      add(sx, sy - dir);
      add(sx - 1, sy);
      add(sx + 1, sy);
      break;
    case "角":
      slide(1, 1); slide(-1, 1); slide(1, -1); slide(-1, -1);
      break;
    case "馬":
      slide(1, 1); slide(-1, 1); slide(1, -1); slide(-1, -1);
      add(sx + 1, sy); add(sx - 1, sy); add(sx, sy + 1); add(sx, sy - 1);
      break;
    case "飛":
      slide(1, 0); slide(-1, 0); slide(0, 1); slide(0, -1);
      break;
    case "龍":
      slide(1, 0); slide(-1, 0); slide(0, 1); slide(0, -1);
      add(sx + 1, sy + 1); add(sx - 1, sy + 1); add(sx + 1, sy - 1); add(sx - 1, sy - 1);
      break;
    case "王":
      for (let dx = -1; dx <= 1; dx++) {
        for (let dy = -1; dy <= 1; dy++) {
          if (dx === 0 && dy === 0) continue;
          add(sx + dx, sy + dy);
        }
      }
      break;
  }

  return moves;
}

function sendMove(data) {
  return fetch("/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  })
    .then(res => res.json())
    .then(data => {
      game = data;
      state = data.state;
      hands = data.hands;
      turn = data.turn;
      render();
      return data;
    });
}

function postgameChoice(choice) {
  return fetch("/postgame-choice", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ choice })
  })
    .then(res => res.json())
    .then(data => {
      if (data.game) {
        game = data.game;
        state = data.game.state;
        hands = data.game.hands;
        turn = data.game.turn;
        render();
      }
      return data;
    });
}

function resetGame() {
  return fetch("/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  })
    .then(res => res.json())
    .then(data => {
      game = data;
      state = data.state;
      hands = data.hands;
      turn = data.turn;
      render();
      return data;
    });
}

function surrenderGame() {
  return fetch("/surrender", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  })
    .then(res => res.json())
    .then(data => {
      game = data;
      state = data.state;
      hands = data.hands;
      turn = data.turn;
      render();
      return data;
    });
}

function confirmSurrenderIfNeeded(message) {
  if (game && game.finished) return Promise.resolve(true);
  return confirmSurrenderModal(message);
}

const resetBtn = document.getElementById("resetBtn");
if (resetBtn) {
  resetBtn.onclick = async () => {
    if (IS_ONLINE && game && game.finished) {
      const result = await postgameChoice("rematch");

      if (result.action === "rematch_failed") {
        await showInfoModal("再戦できませんでした", "タイトルに戻ります。", "OK");
        window.location.href = "/";
        return;
      }

      if (result.action === "rematch_started") {
        return;
      }

      render();
      return;
    }

    resetGame();
  };
}

const titleBtn = document.getElementById("titleBtn");
if (titleBtn) {
  titleBtn.onclick = async () => {
    if (IS_ONLINE && game && game.finished) {
      await postgameChoice("title");
      window.location.href = "/";
      return;
    }

    if (IS_ONLINE && game && !game.finished) {
      const ok = await confirmSurrenderIfNeeded("タイトルに戻ると投了になり、相手の勝利になります。");
      if (!ok) return;
      surrenderGame().then(() => {
        window.location.href = "/";
      });
      return;
    }

    resetGame().then(() => {
      window.location.href = "/title";
    });
  };
}

const navTitleLink = document.getElementById("navTitleLink");
if (navTitleLink) {
  navTitleLink.onclick = async (e) => {
    if (IS_ONLINE && game && game.finished) {
      e.preventDefault();
      await postgameChoice("title");
      window.location.href = navTitleLink.href || "/";
      return;
    }

    if (!(IS_ONLINE && game && !game.finished)) return;

    e.preventDefault();
    const ok = await confirmSurrenderIfNeeded("タイトルに戻ると投了になり、相手の勝利になります。");
    if (!ok) return;

    surrenderGame().then(() => {
      window.location.href = navTitleLink.href || "/";
    });
  };
}

const surrenderBtn = document.getElementById("surrenderBtn");
if (surrenderBtn) {
  surrenderBtn.onclick = async () => {
    if (game && game.finished) return;

    const resignPlayer = IS_ONLINE ? PLAYER : turn;
    const label = playerLabel(resignPlayer);
    const ok = await confirmSurrenderIfNeeded(`${label}が投了すると相手の勝利になります。`);
    if (!ok) return;

    surrenderGame();
  };
}

fetchState();

// 持ち時間の減少と時間切れ判定はサーバー側を基準にするため、
// オンライン・オフラインどちらも定期的に状態を取得します。
setInterval(fetchState, 1000);


