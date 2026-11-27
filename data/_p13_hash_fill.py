import io, sys

for p in ("docs/HANDOVER.md", "docs/HANDOVER_NEXT.md"):
    s = open(p, encoding="utf-8").read()
    n = s.count("<HASH>")
    s = s.replace("<HASH>", "81fcdc6")
    open(p, "w", encoding="utf-8", newline="").write(s)
    print(p, "replaced", n)

p = r"docs/HANDOVER.md"
lines = open(p, encoding="utf-8").read().splitlines(keepends=True)
idx = None
for i, l in enumerate(lines):
    if l.startswith("## 七、最近提交记录"):
        idx = i
        break
assert idx is not None
j = idx + 1
fence = "`" * 3
while not lines[j].strip().startswith(fence):
    j += 1
nl = "\r\n" if lines[j].endswith("\r\n") else "\n"
rec = """（2026-11-24 P1-3 哈希记录：feat 81fcdc6；下一会话 P1-4（ExamBuffConsumptionAdd buff-cost 卡，证据不足保持 no-op 如实记），用户已确认 A 顺序，见 HANDOVER_NEXT §8.0）
（2026-11-24 P1-3（阶段1 第三批，用户确认 A 顺序；纯离线规则，BSD-3 有据）：⑥ hold 保留区建模（CardManager hold/enforceHoldLimit/holdThisCard/holdSelectedByTarget/moveHeldCardsToHand :959-1102 + useCard thisCardHeld :639 + TurnManager.endTurn 只弃手牌）：新 sim/hold.py（HOLD_LIMIT=2 + 13 族卡逐卡证据表 HOLD_SOURCES，主数据 ExamCardMove values 恒空→skill_cards.csv 行号交叉 card_meta 别名核对：冲刺/积累 holdThis 温存中、潜在能力/互动的基础 holdSelected[hand]、切磋琢磨/觉悟/新的舞台/努力了，哦/那一天，在这里（base1/+2张）/对战请多指教！/让群星散落吧 holdSelected[deck|grave]、爱意彩虹 holdSelected[deck]、一点一滴的进步 moveHeldCardsToHand；表外潮流领袖/展翅高飞/发挥本领/决不停歇保留旧+1抽牌近似不猜）；上限2超限最旧进弃牌堆/跨回合保留/holdThis不进弃牌除外/holdSelected同步known_draw（牌堆首张相等=known_draw末张相等）与discard_order/回手LIFO（P1-1钩子对齐pop()）/选牌白值分降序稳定排序（参考HeuristicStrategy全力预览分排序等价）/再演不翻倍hold（按卡索引幂等）；lockStanceTurns（constants EOT_DECREMENT_FIELDS+FULL_POWER_EFFECTS lockStanceTurns==0门+setStance :262+Executor freshBuffs :271-279）：切磋琢磨 StanceLock turn=1↔DSL 424/425，stance_change_allowed/end_turn locked守卫（纯增量），回合末-1+fresh保护（获得当回合末不扣→锁下一回合，卡面确定语义；一般buff fresh缺口仍留真机），全力门被锁全力值不消耗，全力解除不受守卫，再演翻倍；B10遗留trigger_unknown 3件/6段清零：hold区张数条件（_ZONE_MAP hold→held+PassiveState.held+_zone_count_matches；实现的觉悟/± pitem_03-3-078 魅力刚刚好p_card-03-act-1_038↔ジャストアピールcsv380 使用后+countCards[held]>=1↔叶える覚悟pIdol74 csv212/213→温存变更/温存阶段变更+全力值+2/+4，target:held成长段no-op如实记）+hotfix（咲季营养餐・改pitem_02-3-309-0 period810_hotfix三源证实非限定标记：masterTrans描述表无此目标+中文触发句无卡限定+参考csv404咲季の完全食・改turnCardsUsed%2==1无过滤→白名单；每回合第2张好印象+2/好印象强化+25% limit1）；preservation2直给（温存阶段变更value1=2↔setStance(preservation2)：叶える覚悟+/はつぼしフィギュア/まあるい春色/夢見る星交叉，classify/FLAG_TARGETS/delta.stances+_apply_direct_stances双镜过固定守卫，7段重标注）；落地：hold.py新+stance.py+lesson/expectimax（_apply_hold(_state)/_enforce_hold_limit/lock+fresh双镜+canonical+快照往返+叶子LIFO+_passive_state held）+p_items（PassiveState.held/zone_count held/preservation2）+build_p_items（hold→held/period810白名单）+sim_produce（MODELED 34→35 StanceLock、CardRow 41元组、ExamCardMove证据表分支）+play_choice同口径+leaf_data LIFO+p_items.json重建（仅9条记录变化逐条diff校验：3件trigger_known/params/condition+7段preservation2）；implemented保持1056/1849（机制本就支持），trigger_unknown 3→0件，zone_count 27→29件；large评测牌组组成变化（冲刺/积累draw近似移除→抽牌签名槽改选决不停歇，保真度修正旧近似高估；small14张不变；新hold规则在eval_expectimax牌组零触达）→sim_engine_ab重标定改前（stash）/改后64局逐位相同（差异=0，seed9000/9100各16局rules/expectimax budget800ms；冲刺/积累未被这64局奖励采到，sim_engine_ab用14张基础牌组+奖励池动态采牌与eval_expectimax固定large不同口径；expectimax仍显著强于rules Δ+372.2/+219.1，15/0/1与11/0/5，C+100%，0blocked/0error）；旧B11数据/模型旧规则口径全保留不覆盖（阶段2重采新批再对比，参照臂须新规则重评）；46条新单测（test_p13_hold_zone.py）+既有断言随规则更新（MODELED35/41元组/trigger_unknown0/preservation2/large牌组），pytest 1435/1（1436收集/92文件，230.80s），基线①③④⑤复跑不变；重标定产物out/_p13_ab_{before,after}_{9000,9100}.json+一次性脚本data/_p13_ab_compare.py/_p13_pitems_head.json不提交）
81fcdc6 feat(p1): P1-3 hold 保留区建模 + lockStanceTurns 指針固定——BSD-3 参考引擎有据；CardManager hold/enforceHoldLimit/holdThisCard/holdSelected/moveHeldCardsToHand（上限2/跨回合保留/holdThis不进弃牌除外/known_draw・discard_order同步/回手LIFO）+ 13族卡逐卡证据表（ExamCardMove values恒空→skill_cards.csv交叉；表外保留旧+1抽牌近似不猜）+ lockStanceTurns（切磋琢磨 StanceLock turn=1，EOT+fresh锁下一回合+setStance守卫+全力进入门）；B10遗留trigger_unknown 3件清零（hold区张数条件 实现的觉悟↔叶える覚悟 + hotfix 咲季营养餐・改 period810三源证实非限定）+ preservation2直给7段；双镜+canonical+叶子对齐；MODELED 34→35、41元组、implemented保持1056/1849；large评测牌组组成变化（冲刺/积累draw近似移除，保真度修正；small不变）→重标定64局逐位相同；46测试，pytest 1435/1（1436收集/92文件）
"""
lines.insert(j + 1, rec.replace("\n", nl))
open(p, "w", encoding="utf-8", newline="").write("".join(lines))
print("commit record added")
