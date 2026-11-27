# v2 剩余缺口分析 → v3 杠杆（lead，2026-11-25 晚，探针不提交）

数据：data/_f2exv2_compare.json（v2 托管 240 局 vs ex-seed/seedlock 同局配对）。

## v2 vs seedlock（总 +322,742，208 胜 31 负，崩局 0 vs 45）
v2 落后最大 5 局（**全是怪物题**）：
| 题#slot | v2−seedlock | 备注 |
|---|---:|---|
| WDKWQYW5#0 | −3,531,651 | 离线 v2 fp0 +1.31M 赢 base（dev 种子），托管保密种子反输 |
| WNK6ARRZ#0 | −2,744,192 | 离线 v2 4.51M=2.14×上界（dev），托管反输 |
| 3ZT8ZKB6#1 | −1,830,644 | 离线 +219k 赢 base，托管反输 |
| 5KZSXANK#0 | −1,416,115 | **失锁题**（no seed reproduces screen），worlds 兜底 |
| P8ZJTXNA#0 | −307,556 | |

**根因**：怪物题分数对搜索盆地极敏感。v2（2 起点×500k/步）与 seedlock（1 起点×300k/步×更多步累积）
在不同保密种子摸到不同局部最优。离线 dev 种子 v2 赢，托管保密种子 seedlock 摸到更好盆地→反输。
**这不是机制回归，是搜索多样性/起点 luck 在高方差题上的体现**。

## v2 vs ex-seed（总 +300,243，171 胜 50 负，崩局 0 vs 13）
落后最大 5 局（≤651k，量级小）：YSNBNDV4#0 −651k / QQ6J5S39#1 −445k / BZXB28YJ#1 −387k /
N47GNCGH#0 −380k / WPCEABPZ#1 −331k。= GNRPA 起点方差（ex-seed 这些种子 luck 好）。

## v3 杠杆（按收益排序）
1. **怪物题更多起点 / 自适应预算**（最大收益，4 局合计 −9.5M）：starts 2→4（或按回合数/分数方差自适应加起点），
   lock_trans 1M→2M。高方差题多探索盆地。离线 monster 5 配对验证（同 dev 种子 + 多 dev 种子扩样）。
2. **5KZSXANK 失锁修复**（−1.42M + 通用）：牌堆被效果改动后重扫种子 / 扩展抽牌模型跟踪 deck-modify。
   恢复全知搜索（ex-seed/seedlock 同款局限，谁先修谁占优）。
3. **扫描等待窗去墙钟化**（sl3b 锁定等待悬崖）：0.7×budget 墙钟→固定轮询/transition 预算，减锁定回合抖动。
4. **起点方差普适**：更多起点也压 ex-seed 那 50 负局（≤651k 量级）。

## 预期
v2 87.3%（1.267M/1.45M）。怪物题 4 局若夺回一半 ≈ +4.7M/240 ≈ +20k 均分；失锁修复 + 起点方差再抬。
v3 目标均值 1.3M+（90%+），单题继续 upset best-known。注意 best-known 是移动靶（matto farm），推前沿是渐近过程。
