#!/usr/bin/env node
/**
 * 本地裁判 CLI —— gkumas-tools 的 `gakumas-engine`（BSD-3，竞赛/舞台模拟器）。
 *
 * 用法（必须在 `data/dl/gt/gakumas-tools-master` 下用它的 loader 跑，因为引擎内部
 * 用裸 import "gakumas-data" 和 .csv 导入）：
 *
 *   cd D:\Games\gakumas-agent\data\dl\gt\gakumas-tools-master
 *   node --loader ./scripts/extensionless-loader.mjs D:\Games\gakumas-agent\tools\referee_cli.mjs < in.json
 *
 * 自测（用 gakumas-tools 自带 tests/suite.jsonl 第一条，和记录分数对比）：
 *
 *   node --loader ./scripts/extensionless-loader.mjs D:\Games\gakumas-agent\tools\referee_cli.mjs --self-test
 *
 * stdin（JSON 对象）：
 *   {
 *     "loadout": {                     // gakumas-engine 的 contest 编成
 *       "stageId": 95,                 // gakumas-data/csv/stages.csv 的 id
 *       "params": [1246, 3942, 798, 36],   // Vo/Da/Vi/体力
 *       "pItemIds": [132, 82, 53],
 *       "skillCardIdGroups": [[...6 张], [...]],
 *       "customizationGroups": [[{}, ...], ...],
 *       "supportBonus": 0.04,
 *       "enterPercents": false
 *     },
 *     "seed": 1,
 *     "strategy": "heuristic" | "manual",   // 默认 heuristic
 *     "route": [0, 2, -1, ...]              // manual：手牌下标，-1 = 结束回合；
 *                                           // 选牌请求用 [[0,1], ...]（按顺序消耗）
 *   }
 *
 * stdout（恰好一个 JSON 对象）：
 *   成功：{status:"ok", referee, engine, mode:"contest", stage_id, seed, strategy,
 *          score, finished, turns, decisions, ms, node}
 *   不支持的输入：{status:"unsupported", referee, error, reason}
 *
 * 明确限制（实测结论，不做假换算）：
 *   - `gakumas-engine` 只实现 **contest 舞台**（stages.csv 里 type=contest /
 *     linkContest）。它没有 produce（初/H.I.F/N.I.A）的考试/课程模式，也没有
 *     `gkms.exam_loadout.v1` / `gkms.hif_loadout.v1` 的字段（deck_cards、
 *     parameters 三元组、score_bonus_permils、step_type...）。
 *   - 所以 gkbench 的题不能喂给这个引擎；本 CLI 对 `deck_cards` 类编成返回
 *     unsupported，而不是猜一个映射。
 *   - 自测（`--self-test`）用 gakumas-tools 自带的 tests/suite.jsonl 第一条，
 *     和它记录的分数对比，证明引擎能在本机 Node 下跑完整一局。
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  IdolConfig,
  IdolStageConfig,
  StageConfig,
  StageEngine,
  StagePlayer,
  STRATEGIES,
  resetRand,
} from "gakumas-engine";
import { Stages } from "gakumas-data";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, "..");
const TOOLS_ROOT = resolve(REPO_ROOT, "data", "dl", "gt", "gakumas-tools-master");
const REFEREE = "gakumas-engine (gakumas-tools, BSD-3, contest stage only)";
const ENGINE = "gakumas-engine@1.0.0";
// utils.js 的默认种子；--self-test 用它才能对上 tests/suite.jsonl 记录的分数。
const DEFAULT_SEED = 610397104;

function emit(payload, code = 0) {
  process.stdout.write(JSON.stringify(payload, null, 1) + "\n");
  process.exitCode = code;
}

function unsupported(reason) {
  emit({
    status: "unsupported",
    referee: REFEREE,
    engine: ENGINE,
    mode: "contest",
    error: "unsupported_loadout",
    reason,
    note: "gkumas-tools 的 gakumas-engine 只模拟 contest 舞台；gkbench 的 produce 考试需要 GKMS 引擎。",
  });
}

function isBenchLoadout(loadout) {
  if (!loadout || typeof loadout !== "object") return false;
  if (Array.isArray(loadout.deck_cards)) return true;
  if (typeof loadout.idol_card_id === "string") return true;
  if (typeof loadout.schema === "string" && loadout.schema.startsWith("gkms.")) return true;
  return false;
}

function contestLoadout(input) {
  const lo = input.loadout;
  const stageId = Number(lo.stageId ?? input.stageId);
  if (!Number.isInteger(stageId) || stageId <= 0) {
    throw new Error("loadout.stageId 缺失/非法");
  }
  const params = Array.isArray(lo.params) ? lo.params.map(Number) : null;
  if (!params || params.length !== 4) {
    throw new Error("loadout.params 必须是 [Vo, Da, Vi, 体力] 四个数");
  }
  const groups = lo.skillCardIdGroups;
  if (!Array.isArray(groups) || !groups.length) {
    throw new Error("loadout.skillCardIdGroups 缺失");
  }
  let customizations = lo.customizationGroups;
  if (!Array.isArray(customizations) || customizations.length !== groups.length) {
    customizations = groups.map((g) => g.map(() => ({})));
  }
  return {
    stageId,
    enterPercents: !!lo.enterPercents,
    supportBonus: lo.supportBonus == null ? null : Number(lo.supportBonus),
    params,
    pItemIds: (lo.pItemIds || []).map(Number),
    skillCardIdGroups: groups.map((g) => g.map(Number)),
    customizationGroups: customizations,
  };
}

/** 路线驱动：把 route 里的手牌下标/选牌答案交给 ManualStrategy。 */
function routeStrategy(engine, route) {
  let cursor = 0;
  let decisionCursor = 0;
  const next = () => {
    if (cursor >= route.length) {
      throw new Error(`route 用完了（第 ${cursor} 项）`);
    }
    return route[cursor++];
  };
  const callback = async ({ type, handCards, usableCards, cards, num }) => {
    if (type === "CARD_SELECTION") {
      const action = next();
      if (action === -1) return null;
      if (!Number.isInteger(action) || action < 0 || action >= handCards.length) {
        throw new Error(`route[${cursor - 1}] 不是合法手牌下标：${action}`);
      }
      if (!usableCards.includes(handCards[action])) {
        throw new Error(`route[${cursor - 1}] 指向的牌不可出：${action}`);
      }
      return handCards[action];
    }
    // 选牌请求（hold / move / use-free）：route 里给下标数组
    const answer = next();
    if (!Array.isArray(answer)) {
      throw new Error(`${type} 需要一个下标数组，route[${cursor - 1}] = ${JSON.stringify(answer)}`);
    }
    const picked = answer.slice(0, num ?? answer.length);
    for (const i of picked) {
      if (!Number.isInteger(i) || i < 0 || i >= (cards || []).length) {
        throw new Error(`${type} 下标越界：${i}`);
      }
    }
    return picked;
  };
  const strategy = new STRATEGIES.ManualStrategy(engine, callback);
  return {
    strategy,
    decisions: () => decisionCursor,
    countDecision: () => {
      decisionCursor += 1;
    },
  };
}

async function runContest(input) {
  const loadout = contestLoadout(input);
  const seed = Number.isInteger(input.seed) ? input.seed : DEFAULT_SEED;
  const strategyName = input.strategy || "heuristic";

  const stage = new StageConfig(
    // 从 gakumas-data 的 csv 读，getById 返回的 stage 已解析
    Stages.getById(loadout.stageId),
  );
  const config = new IdolStageConfig(
    new IdolConfig(loadout),
    stage,
    loadout.enterPercents,
  );
  const engine = new StageEngine(config);

  let strategy;
  let decisions = 0;
  if (strategyName === "manual") {
    if (!Array.isArray(input.route)) throw new Error("strategy=manual 需要 route 数组");
    const routed = routeStrategy(engine, input.route);
    strategy = routed.strategy;
    const origEvaluate = strategy.evaluate.bind(strategy);
    strategy.evaluate = async (state) => {
      decisions += 1;
      return origEvaluate(state);
    };
  } else if (strategyName === "heuristic") {
    strategy = new STRATEGIES.HeuristicStrategy(engine);
    const origEvaluate = strategy.evaluate.bind(strategy);
    strategy.evaluate = (state) => {
      decisions += 1;
      return origEvaluate(state);
    };
  } else {
    throw new Error(`未知 strategy：${strategyName}（只支持 heuristic / manual）`);
  }
  engine.strategy = strategy;

  resetRand(seed);
  const started = performance.now();
  const result = await new StagePlayer(engine, strategy).play();
  const turns = Number(stage.turnCount) || decisions;
  return {
    status: "ok",
    referee: REFEREE,
    engine: ENGINE,
    mode: "contest",
    stage_id: loadout.stageId,
    seed,
    strategy: strategyName,
    score: result.score,
    finished: true,
    turns,
    decisions,
    logs: Array.isArray(result.logs) ? result.logs.length : null,
    ms: Math.round((performance.now() - started) * 100) / 100,
    node: process.version,
  };
}

function selfTest() {
  const suitePath = resolve(TOOLS_ROOT, "tests", "suite.jsonl");
  const first = readFileSync(suitePath, "utf8").split(/\r?\n/).find((l) => l.trim());
  const entry = JSON.parse(first);
  const q = new URLSearchParams(entry.query);
  const ids = (s) => (s || "").split("-").map((n) => parseInt(n, 10) || 0);
  const groups = (q.get("cards") || "").split("_").map(ids);
  const cus = (q.get("customizations") || "").split("_").map((g) =>
    g.split("-").map((c) =>
      c
        .split("e")
        .filter(Boolean)
        .reduce((acc, cur) => {
          const [k, v] = cur.split("x");
          acc[k] = parseInt(v, 10);
          return acc;
        }, {}),
    ),
  );
  const loadout = {
    stageId: parseInt(q.get("stage"), 10),
    enterPercents: q.get("enter_percents") === "1",
    supportBonus: parseFloat(q.get("support_bonus")) || null,
    params: ids(q.get("params")),
    pItemIds: ids(q.get("items")),
    skillCardIdGroups: groups,
    customizationGroups: cus.length === groups.length ? cus : groups.map((g) => g.map(() => ({}))),
  };
  return runContest({ loadout, seed: DEFAULT_SEED, strategy: "heuristic" }).then((out) => {
    emit({
      ...out,
      self_test: {
        suite_id: entry.id,
        expected_score: entry.score,
        match: out.score === entry.score,
      },
    });
  });
}

async function main() {
  const argv = process.argv.slice(2);
  if (argv.includes("--self-test")) {
    await selfTest();
    return;
  }
  const raw = readFileSync(0, "utf8").trim();
  if (!raw) throw new Error("stdin 为空：需要 JSON 对象");
  const input = JSON.parse(raw);
  if (isBenchLoadout(input.loadout)) {
    unsupported(
      "输入是 gkms.* 编成（deck_cards/idol_card_id/parameters/score_bonus_permils），不是 contest 编成；" +
        "gakumas-engine 没有 produce 考试模式，无法当这套题的裁判。",
    );
    return;
  }
  if (input.mode === "produce" || input.kind === "produce") {
    unsupported("请求 produce 考试模式；gakumas-engine 只实现 contest 舞台。");
    return;
  }
  emit(await runContest(input));
}

main().catch((error) => {
  emit({
    status: "error",
    referee: REFEREE,
    engine: ENGINE,
    error: "exception",
    reason: String(error && error.stack ? error.stack : error),
  });
});
