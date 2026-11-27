# ================================================================ 适配器部分
# 以下为本投稿原创：UIObs → ExpectState 映射（复用 r13 已验证口径）+ expectimax 决策。
# 映射函数 _num/_as_int/_status_fields/_stance_from_obs 与正则逐字取自
# submissions/gkagent-ei-r13/algo.py（249 项检查 + 7642 步真实观测回放验证）。

HERE = Path(__file__).resolve().parent

# 真机每回合基础出牌数（B3 核实）；额外次数由 num.playable 反推（r13 同口径）。
BASE_PLAY_LIMIT = 1
# 卡表查不到时的保守牌费（r13 同口径）：0 分 3 费，搜索自然少打。
DEFAULT_CARD_COST = 3

# ---- 考试成长 g / 定制 c 的透明子集 → CardSpec 字段（r13 _G_TARGET 同语义，列号换字段名）
_G_TARGET = {
    "lesson_add": ("score", 1),
    "cost_add": ("cost", 1),
    "cost_reduce": ("cost", -1),
    "review_add": ("impression", 1),
    "lesson_buff_add": ("focus", 1),
    "aggressive_add": ("motivation", 1),
    "lesson_depend_block_add": ("block_scale", 1),
    "lesson_depend_exam_review_add": ("impression_scale", 1),
    "parameter_buff_turn_add": ("condition", 1),
}


def _apply_segment_spec(spec: CardSpec, target: str, value: int) -> CardSpec | None:
    hit = _G_TARGET.get(target)
    if hit is None:
        return None
    name, sign = hit
    updated = max(getattr(spec, name) + sign * value, 0)
    return replace(spec, **{name: updated})


def _augment_spec(spec: CardSpec, raw: dict) -> tuple[CardSpec, int, int]:
    """把 obs 卡的 g（成长）/c（定制）里**透明子集**加进 CardSpec（r13 _augment_profile 同逻辑）。

    定制 id 形如 p_card_custom-<pp档列表>-g_effect-<段>-g_effect-<段>…，obs 的
    [[id, count]] 的 count 是档位（1 起）；档数与段数一致时按档取段，否则保守忽略。
    wrapper / 嵌套效果 / 认不出的段一律忽略（不猜）。
    """
    applied = ignored = 0
    for gid in raw.get("g") or ():
        m = _RE_G.match(str(gid))
        if m:
            nxt = _apply_segment_spec(spec, m.group(1), int(m.group(2)))
            if nxt is not None:
                spec = nxt
                applied += 1
                continue
        ignored += 1
    for item in raw.get("c") or ():
        try:
            cid, count = str(item[0]), int(item[1])
        except (TypeError, ValueError, IndexError):
            ignored += 1
            continue
        m = _RE_CUSTOM.match(cid)
        if not m or "wrapper" in cid:
            ignored += 1
            continue
        tiers, rest = m.group(1).split("_"), m.group(2)
        if not rest.startswith("g_effect-") or "e_effect" in rest or "p_card" in rest:
            ignored += 1
            continue
        segments = rest[len("g_effect-"):].split("-g_effect-")
        parsed = [_RE_SEG.match(s) for s in segments]
        if len(parsed) != len(tiers) or any(p is None for p in parsed) or not 1 <= count <= len(parsed):
            ignored += 1
            continue
        seg = parsed[count - 1]
        nxt = _apply_segment_spec(spec, seg.group(1), int(seg.group(2)))
        if nxt is not None:
            spec = nxt
            applied += 1
        else:
            ignored += 1
    return spec, applied, ignored


# ---------------------------------------------------------------- 卡表（全字段 CardSpec）
class _CardTable:
    """(id,upgrade) → 全字段 CardSpec。card_specs.json 由生产链预计算：
    scripts/sim_produce._effect_fields + _spec_from_row + eval_expectimax._with_once
    （与 r13 card_profiles.json 同一来源，但保留 turns/hold/熱意 等全部字段，搜索无损）。
    """

    def __init__(self, path: Path) -> None:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("format") != "gkagent.expectimax_card_specs.v1":
            raise ValueError(f"unsupported card_specs format: {doc.get('format')!r}")
        self.rows: dict[str, dict] = doc.get("cards") or {}
        self.levels: dict[str, list[int]] = {}
        for key in self.rows:
            cid, _, lv = key.partition("|")
            self.levels.setdefault(cid, []).append(int(lv))
        for levels in self.levels.values():
            levels.sort()

    def base_spec(self, card_id: str, upgrade: int) -> CardSpec | None:
        row = self.rows.get(f"{card_id}|{upgrade}")
        if row is None:
            levels = self.levels.get(card_id) or []
            if levels:
                # 强化超出卡表最高档：取 ≤u 的最高已知档（没有则最低档），保守低估（r13 同口径）。
                lower = [lv for lv in levels if lv <= upgrade]
                lv = max(lower) if lower else min(levels)
                row = self.rows.get(f"{card_id}|{lv}")
        if row is None:
            return None
        kwargs = {f.name: row[f.name] for f in fields(CardSpec) if f.name in row}
        return CardSpec(**kwargs)


def _unknown_spec(card_id: str) -> CardSpec:
    return CardSpec(name=card_id or "unknown", cost=DEFAULT_CARD_COST, score=0.0)


# ---------------------------------------------------------------- 属性倍率（obs.exam.permil）
def _turn_coefficient(permil: list, types: list, turn: int) -> float:
    """第 turn 回合（1 起）的真实属性倍率 = permil[types[turn-1]-1]/1000。

    课程题 permil=[0,0,0] / types=[] → 1.0（未知不猜）；越界/坏值 → 1.0。
    """
    if not permil or len(permil) < 3 or not types:
        return 1.0
    idx = turn - 1
    if idx < 0 or idx >= len(types):
        return 1.0
    color = _as_int(types[idx], 1)
    if not 1 <= color <= 3:
        return 1.0
    value = _num(permil[color - 1])
    return value / 1000.0 if value > 0 else 1.0


def _is_lesson(obs: dict, meta: dict | None, loadout: dict | None) -> bool:
    """课程题判定：exam.step 是整数（课程 step_id）/ types 空 / round=lesson / meta.step_type 整数。

    考试（audition）的 step 是 "AUDITION_MID1/MID2/FINAL" 字符串且 types 非空。
    """
    exam = obs.get("exam") or {}
    step = exam.get("step")
    if isinstance(step, str) and step.startswith("AUDITION"):
        return False
    if isinstance(step, int):
        return True
    if not (exam.get("types") or []):
        return True
    if isinstance((loadout or {}).get("round"), str) and loadout["round"] == "lesson":
        return True
    if isinstance((meta or {}).get("step_type"), int):
        return True
    return False


# ---------------------------------------------------------------- 叶子：期望分数目标
@dataclass(frozen=True)
class ScoreLeaf:
    """gkbench 按**原始分数**排名，没有有意义的 CLEAR/PERFECT 终线：
    档位效用 AnalyticLeafValue.utility 在 clear=0 时恒 0（搜索退化），
    crit 是逐回合审查基准不是终线（高分支全饱和）。沿用 scripts/local_bench.py
    ScoreObjectiveLeaf 的口径：效用 = 当前分 + 预测未来分 μ。

    尺度适配（本投稿相对生产 AnalyticLeafValue 的唯一叶子改动，可 ablation）：
    μ 是白值单位（集中/均值牌面/好印象年金），真实考试未来分还要乘属性倍率
    （hajime 4–6×、hif 20–48×）。``scale`` = 剩余未来回合 permil 倍率均值，
    把 μ 换算成真实分单位，与 _card_award 里已乘 attribute_coefficient 的即时分同尺度。
    scale=1.0 = 不缩放（ablation / 课程）。搜索核心本身与生产逐字一致。
    """

    inner: AnalyticLeafValue
    scale: float = 1.0

    def predict(self, state: ExpectState) -> tuple[float, float]:
        return self.inner.predict(state)

    def utility(self, state: ExpectState) -> float:
        mu, _sigma = self.inner.predict(state)
        return float(state.score) + float(mu) * float(self.scale)


# ---------------------------------------------------------------- 算法
class ExpectimaxAlgo(Algorithm):
    """回合内 expectimax 搜索（public-safe）：枚举本回合合法出牌序列，
    抽牌走精确超几何机会节点（deck 无序多重集 → 期望），回合末解析式 V_leaf
    估未来分，取期望分最高的首牌。只读 ctx.obs，不读种子、不用 worlds。
    """

    name = "gkagent-expectimax"
    title = "gkagent expectimax (public-safe)"
    needs_gkms = False
    sees_seed = False
    privileged = False
    about = {
        "summary": "回合内 expectimax 精确搜索：合法出牌序列 × 超几何抽牌机会节点 × 解析式叶子期望分",
        "sees": "screen",
        "detail": [
            "搜索核心逐字提取自生产 gkagent/sim/expectimax.py（回合内路径），同 ExpectState 对拍一致",
            "UIObs→ExpectState 映射复用 r13 已验证适配器（249 项检查 + 7642 步回放）",
            "卡表全字段 CardSpec 用生产训练链预计算（card_specs.json），g/c 透明子集增强",
            "真实属性倍率来自 obs.exam.permil（考试当前回合），叶子 μ 按剩余回合倍率均值缩放",
            "叶子目标 = 当前分 + 期望未来分（gkbench 按原始分排名；local_bench ScoreObjectiveLeaf 同口径）",
            "硬规矩：有可出牌绝不 end；搜索异常如实记 meta.error 并退回合法牌；不读种子、不用世界",
        ],
        "family": "gkagent-expectimax",
        "family_name": "gkagent expectimax",
    }

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self.table = _CardTable(HERE / "card_specs.json")
        self._card_cache: dict[tuple, CardSpec] = {}
        # augment=1：把 obs 的 g/c 透明子集加进 CardSpec（默认开）；0 = 纯卡表基线（ablation）。
        self.augment = bool(_as_int(params.get("augment"), 1))
        # scale_leaf=1：叶子 μ × 剩余回合属性倍率均值（默认开）；0 = 白值 μ（ablation）。
        self.scale_leaf = bool(_as_int(params.get("scale_leaf"), 1))
        self.sigma = max(float(params.get("sigma", 80.0) or 80.0), 0.0)
        self.budget_ms = max(float(params.get("budget_ms", 4200.0) or 4200.0), 50.0)
        self.max_nodes = max(int(params.get("max_nodes", 200_000) or 200_000), 1)
        self.draw_enum_limit = max(int(params.get("draw_enum_limit", 8) or 8), 0)
        self._played_total = 0
        self._p_item_count = 0
        self._episode_meta: dict[str, Any] = {}
        self._aug_applied = 0
        self._aug_ignored = 0

    # ------------------------------------------------------------ 卡表
    def _card(self, raw: dict) -> CardSpec:
        card_id = str(raw.get("id") or "")
        upgrade = max(_as_int(raw.get("u"), 0), 0)
        cg = (json.dumps(raw.get("c") or [], sort_keys=True),
              json.dumps(raw.get("g") or [], sort_keys=True)) if self.augment else ("[]", "[]")
        key = (card_id, upgrade, cg)
        cached = self._card_cache.get(key)
        if cached is not None:
            return cached
        spec = self.table.base_spec(card_id, upgrade)
        if spec is None:
            spec = _unknown_spec(card_id)
        elif self.augment and (raw.get("c") or raw.get("g")):
            spec, applied, ignored = _augment_spec(spec, raw)
            self._aug_applied += applied
            self._aug_ignored += ignored
        self._card_cache[key] = spec
        return spec

    def _zone(self, obs: dict, key: str) -> tuple[CardSpec, ...]:
        return tuple(self._card(c) for c in obs.get(key) or ())

    # ------------------------------------------------------------ 状态（r13 映射口径）
    def _state(self, obs: dict) -> ExpectState:
        exam = obs.get("exam") or {}
        num = obs.get("num") or {}
        turn = max(_as_int(exam.get("turn"), 1), 1)
        limit = max(_as_int(exam.get("limit"), turn), turn)
        turns_left = max(limit - turn + 1, 0)
        status = _status_fields(obs, turns_left)
        plays_used = max(_as_int(num.get("plays"), 0), 0)
        playable = max(_as_int(num.get("playable"), 0), 0)
        hand = self._zone(obs, "hand")
        deck = self._zone(obs, "deck")
        discard = self._zone(obs, "grave")       # 引擎口径：played 已在 grave，不重复并
        excluded = self._zone(obs, "lost")
        held = self._zone(obs, "hold")
        all_cards = hand + deck + discard + held
        min_cost = min((int(c.cost) for c in all_cards), default=0)
        permil = exam.get("permil") or []
        types = exam.get("types") or []
        coefficient = _turn_coefficient(permil, types, turn)
        return ExpectState(
            hand=hand,
            deck=deck,
            discard=discard,
            excluded=excluded,
            held=held,
            stamina=max(_as_int(num.get("stamina"), 0), 0),
            stamina_max=max(_as_int(num.get("max_stamina"), 0), 0),
            vitality=max(_as_int(num.get("block"), 0), 0),
            score=max(_as_int(num.get("score"), 0), 0),
            turns_left=turns_left,
            total_turns=limit,
            plays_used=plays_used,
            play_limit=BASE_PLAY_LIMIT,
            extra_plays=max(playable + plays_used - BASE_PLAY_LIMIT, 0),
            # clear/perfect：obs 的 crit 是逐回合审查基准（课程题全 0），不是终线；
            # 叶子用期望分数目标，不依赖档位线 → 保守 0（r13 同口径）。
            clear=0,
            perfect=0,
            condition_turns=int(status["condition_turns"]),
            perfect_condition_turns=int(status["perfect_condition_turns"]),
            poor_condition_turns=int(status["poor_condition_turns"]),
            focus=int(status["focus"]),
            impression=int(status["impression"]),
            motivation=int(status["motivation"]),
            condition_additive=int(status["condition_additive"]),
            condition_additive_turns=int(status["condition_additive_turns"]),
            review_multiple=int(status["review_multiple"]),
            review_multiple_turns=int(status["review_multiple_turns"]),
            full_power_lesson_multiple=int(status["full_power_lesson_multiple"]),
            full_power_lesson_multiple_turns=int(status["full_power_lesson_multiple_turns"]),
            parameter_buff=0,                    # turn_parameter_buff：UIObs 无对应图标，保守 0
            stance=_stance_from_obs(obs, int(status["full_power_point"])),
            attribute_coefficient=coefficient,
            min_cost=min_cost,
            cards_played_total=self._played_total,
            cost_reduction=int(status["cost_reduction"]),
            cost_increase=int(status["cost_increase"]),
            half_cost_turns=int(status["half_cost_turns"]),
            double_cost_turns=int(status["double_cost_turns"]),
            # 不建模（r13 同局限，如实记录）：饮料/P 道具效果/附魔/回忆/支援卡/gimmick；
            # known_draw/discard_order 保持默认（public-safe，多重集期望）。
            p_items=(),
            drinks=(),
        )

    def _leaf_scale(self, obs: dict, state: ExpectState) -> float:
        if not self.scale_leaf:
            return 1.0
        exam = obs.get("exam") or {}
        permil = exam.get("permil") or []
        types = exam.get("types") or []
        turn = max(_as_int(exam.get("turn"), 1), 1)
        limit = max(_as_int(exam.get("limit"), turn), turn)
        future = [_turn_coefficient(permil, types, t) for t in range(turn + 1, limit + 1)]
        if future:
            return sum(future) / len(future)
        return state.attribute_coefficient

    # ------------------------------------------------------------ 决策
    def begin(self, ctx: Any) -> None:
        self._played_total = 0
        self._aug_applied = 0
        self._aug_ignored = 0
        self._card_cache.clear()
        loadout = getattr(ctx, "loadout", None)
        ids = loadout.get("produce_item_ids") if isinstance(loadout, dict) else None
        self._p_item_count = len(ids) if isinstance(ids, (list, tuple)) else 0
        meta = getattr(ctx, "meta", None)
        self._episode_meta = {}
        if isinstance(meta, dict):
            rivals = meta.get("rival_scores") or []
            tops = [_as_int(r.get("score_max"), 0) for r in rivals if isinstance(r, dict)]
            self._episode_meta = {"limit_turn": meta.get("limit_turn"),
                                  "rival_top": max(tops, default=0)}

    def decide(self, ctx: Any) -> Decision:
        obs = ctx.obs
        legal = [tuple(a) for a in obs.get("legal") or ()]
        if not legal:
            return Decision(("end",), {"why": "obs.legal 为空，保守结束回合"})
        play_indices = [int(a[1]) for a in legal if a[0] == "play" and len(a) > 1]
        hand_len = len(obs.get("hand") or ())
        play_indices = [i for i in play_indices if 0 <= i < hand_len]
        if not play_indices:
            # 没有可出牌（或下标越界）：end 合法就 end；否则取第一个合法动作（select 等）。
            if ("end",) in legal:
                return Decision(("end",), {"why": "没有可出牌，结束回合"})
            return Decision(legal[0], {"why": "非出牌决策，取第一个合法动作"})
        try:
            state = self._state(obs)
            lesson = _is_lesson(obs, getattr(ctx, "meta", None), getattr(ctx, "loadout", None))
            leaf_scale = self._leaf_scale(obs, state)
            leaf = ScoreLeaf(AnalyticLeafValue(sigma=self.sigma), scale=leaf_scale)
            budget_ms = self.budget_ms
            ctx_budget = _num(getattr(ctx, "budget", 0))
            if ctx_budget > 0:
                budget_ms = min(budget_ms, max((ctx_budget - 0.8) * 1000.0, 200.0))
            result = expectimax_with_stats(
                state,
                leaf,
                time_budget_ms=budget_ms,
                max_nodes=self.max_nodes,
                draw_enum_limit=self.draw_enum_limit,
                allow_drinks=False,              # 不喝饮料（r13 同口径；生产真机链路同）
            )
            idx: int | None = None
            if result.card is not None:
                idx = next((i for i in play_indices if state.hand[i] == result.card), None)
            why = "expectimax 回合内搜索（期望分）"
            if idx is None:
                # 搜索选了 SKIP（或异常中断无结果）：硬规矩有可出牌绝不 end →
                # 按已算出的动作价值取最大 play；没有价值信息退回第一张合法牌。
                best_name, best_val = None, -math.inf
                for name, value in result.actions:
                    if value > best_val:
                        best_name, best_val = name, value
                if best_name is not None:
                    idx = next((i for i in play_indices if state.hand[i].name == best_name), None)
                if idx is None:
                    idx = play_indices[0]
                    why = "搜索未给出可出牌结果，硬规矩退回第一张合法牌"
                else:
                    why = "搜索选 SKIP，硬规矩按动作价值出牌"
            action = ("play", idx)
            self._played_total += 1
            order = sorted(result.actions, key=lambda item: item[1], reverse=True)
            meta: dict[str, Any] = {
                "why": why,
                "mode": "lesson" if lesson else "exam",
                "coeff": round(state.attribute_coefficient, 4),
                "leaf_scale": round(leaf_scale, 4),
                "utility": round(float(result.utility), 2),
                "skip_utility": round(float(result.skip_utility), 2),
                "nodes": int(result.nodes),
                "ms": round(float(result.elapsed_ms), 1),
                "complete": bool(result.complete),
                "top": [[name, round(float(value), 2)] for name, value in order[:3]],
                "turns_left": state.turns_left,
                "focus": state.focus,
                "stance": list(state.stance),
                "played_total": self._played_total,
            }
            if self.augment:
                meta["cg_aug"] = [self._aug_applied, self._aug_ignored]
            if self._episode_meta:
                meta["exam"] = dict(self._episode_meta)
            return Decision(action, meta)
        except Exception as exc:  # noqa: BLE001 - 搜索异常如实记录，退回合法牌，不偷换规则
            action = ("play", play_indices[0])
            self._played_total += 1
            return Decision(action, {"why": "搜索异常，退回第一张合法牌",
                                     "error": f"{type(exc).__name__}: {exc}"})
