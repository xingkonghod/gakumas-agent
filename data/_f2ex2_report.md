# f2-ex2 两版跑分汇总

## hif（模板核心题 × 前 2 保密种子，托管）
- A gkagent-expectimax（GKMS PIMC eval, worlds=6）: n=240 均分 531,280
- B gkagent-ex-seed（自锁种子+全知GNRPA/tail）: n=240 均分 967,348
- 配对 240 局：A 531,280 / B 967,348，B−A 平均 +436,068，B 胜 204/240（85%）

## hajime（模板核心题 × 前 2 保密种子，托管）
- A gkagent-expectimax（GKMS PIMC eval, worlds=6）: n=96 均分 32,377
- B gkagent-ex-seed（自锁种子+全知GNRPA/tail）: n=96 均分 106,418
- 配对 96 局：A 32,377 / B 106,418，B−A 平均 +74,042，B 胜 30/96（31%）

## B seed-lock 统计（stderr 每局一行）
- b_hif: 230/243 局锁定，锁定回合分布 {1: 16, 2: 107, 3: 90, 4: 10, 5: 6, 6: 1}，扫描耗时中位 3.24s
- b_hajime: 76/102 局锁定，锁定回合分布 {1: 3, 2: 15, 3: 19, 4: 21, 5: 13, 6: 5}，扫描耗时中位 8.55s

## 错误 / 超时（服务器 episode 记录）
- a_hif: n=240 均分 531,280 错误 0 超时步 492 未走完 0 最大步 0ms
- a_hajime: n=96 均分 32,377 错误 0 超时步 72 未走完 0 最大步 0ms
- b_hif: n=240 均分 967,348 错误 0 超时步 172 未走完 0 最大步 0ms
- b_hajime: n=96 均分 106,418 错误 0 超时步 137 未走完 0 最大步 0ms

## 榜单上下文（/api/runs，同集合最近运行）
- hajime | best-known | n=1536 | mean=143,144 | run=20261114-021017-hajime-template-best-known
- hajime | gkagent-ei-r13 | n=96 | mean=3,902 | run=template-hajime-gkagent-ei-r13-xingkonghod-1bf9543d4462
- hajime | gkagent-ei-r13-norm-rescale | n=96 | mean=5,801 | run=template-hajime-gkagent-ei-r13-norm-rescale-xingkonghod-49cf44da8f2c
- hajime | gkagent-ei-r13-norm-rescalebuffs | n=96 | mean=5,483 | run=template-hajime-gkagent-ei-r13-norm-rescalebuffs-xingkonghod-5ddee58aa8f5
- hajime | gkagent-ex-seed | n=96 | mean=106,418 | run=template-hajime-gkagent-ex-seed-xingkonghod-3f42c9f53ad0
- hajime | gkagent-expectimax | n=96 | mean=32,377 | run=template-hajime-gkagent-expectimax-xingkonghod-459d0e97ad0b
- hajime | gkagent-seedlock | n=96 | mean=110,613 | run=template-hajime-gkagent-seedlock-xingkonghod-e7a49cbc91d1
- hajime | lite-pimc8-cem1-s4 | n=192 | mean=20,221 | run=template-hajime-lite-pimc8-cem1-s4-jayalbertzhao-32876b60bc4a
- hajime | lite-pimc8-v2-s4 | n=192 | mean=31,779 | run=template-hajime-lite-pimc8-v2-s4-jayalbertzhao-830d6ecd6daf
- hajime | lite-pimc8-v2-s8 | n=384 | mean=22,875 | run=template-hajime-lite-pimc8-v2-s8-jayalbertzhao-57766826e9d4
- hif | UIHorizon-v2.0Preview-Freiheitsmasik | n=960 | mean=636,109 | run=template-hif-UIHorizon-v2.0Preview-Freiheitsmasik-yuzeis-adee9e583366
- hif | UIHorizon-v2.1Preview-Kummertranen | n=960 | mean=631,129 | run=template-hif-2.1Preview-yuzeis-5d9aac417fb8
- hif | UIHorizon-v2.2Preview-Gratwanderung | n=960 | mean=571,828 | run=template-hif-UIHorizon-v2.2Preview-Gratwanderung-yuzeis-0aa802875cc0
- hif | UIHorizon-v2.2bPreview-Gratwanderung | n=95 | mean=297,998 | run=template-hif-UIHorizon-v2.2bPreview-Gratwanderung-yuzeis-8a3f650b07b8
- hif | best-known | n=800 | mean=2,134,509 | run=20261114-130117-hif-template-best-known
- hif | exam-sim-pimc-smoke | n=3 | mean=291,700 | run=template-hif-exam-sim-pimc-smoke-huochai67-f90d77beef03
- hif | gkagent-ei-r13 | n=240 | mean=81,523 | run=template-hif-gkagent-ei-r13-xingkonghod-7b0da3c354fd
- hif | gkagent-ei-r13-cgaug | n=240 | mean=86,988 | run=template-hif-gkagent-ei-r13-cgaug-xingkonghod-d20fda5881ec
- hif | gkagent-ei-r13-norm-both | n=240 | mean=98,550 | run=template-hif-gkagent-ei-r13-norm-both-xingkonghod-fc9839dbb824
- hif | gkagent-ei-r13-norm-clip2 | n=240 | mean=95,217 | run=template-hif-gkagent-ei-r13-norm-clip2-xingkonghod-a4d68f4fe5fc
- hif | gkagent-ei-r13-norm-clip3 | n=240 | mean=96,853 | run=template-hif-gkagent-ei-r13-norm-clip3-xingkonghod-41258b594697
- hif | gkagent-ei-r13-norm-clip4 | n=240 | mean=94,792 | run=template-hif-gkagent-ei-r13-norm-clip4-xingkonghod-9b25b4f66cfa
- hif | gkagent-ei-r13-norm-off | n=240 | mean=86,988 | run=template-hif-gkagent-ei-r13-norm-off-xingkonghod-28500a5be2bc
- hif | gkagent-ei-r13-norm-rescale | n=239 | mean=98,943 | run=template-hif-gkagent-ei-r13-norm-rescale-xingkonghod-c1b8a2b7ac52
- hif | gkagent-ei-r13-norm-rescalebuffs | n=239 | mean=103,959 | run=template-hif-gkagent-ei-r13-norm-rescalebuffs-xingkonghod-376ccb367b1c
- hif | gkagent-ex-seed | n=240 | mean=967,348 | run=template-hif-gkagent-ex-seed-xingkonghod-57b6dc8db59f
- hif | gkagent-expectimax | n=240 | mean=531,280 | run=template-hif-gkagent-expectimax-xingkonghod-3671171720ab
- hif | gkagent-seedlock | n=240 | mean=944,850 | run=template-hif-gkagent-seedlock-xingkonghod-c060df94acad
- hif | pimc-vote-16w-2s | n=160 | mean=221,926 | run=20261111-002127-hif-live-template-pimc-vote-16w-2s-matto