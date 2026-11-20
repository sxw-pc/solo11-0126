# 规划地块异议期限台

为规划公示承办员与地块权利人提供离线合成公开来源的时效和证据核验。核心结果：判定异议是否针对有效地块版本且在法定窗口内。公开文本经来源身份和版本采信后，分别驱动业务案件与履约核验；这三个子系统有独立业务实体、状态和 CLI 入口。

## 运行

```powershell
python -m pip install . --no-deps --no-build-isolation
python -m parcelcase demo
python -m pytest -q
```

手动运行：`python -m parcelcase adopt --db state.db --input fixtures/plan_normal.json`，`python -m parcelcase assess --db state.db --input fixtures/parcel_normal.json`，`python -m parcelcase settle --db state.db --input fixtures/objection_normal.json`，`python -m parcelcase report --db state.db --out report.json`。

## 状态与证据

`python -m parcelcase map-import --db state.db --input fixtures/map_sheets_normal.json` 可导入离线测绘卷。每卷记录控制点相对位移区间、对应图幅和复测成本；重复导入同原文幂等，同来源同版本异文拒绝并保留原卷。`report` 的 `auxiliary.map_source` 与 `auxiliary.map_sheet` 展示采集证据。单卷格式核验之外，多卷是否共同可解由复测审查判定（见下节）；两者都不据此发布地图，也不改变地块异议资格判断。

- 公示采信：确认公示起止时刻和取代链的有效版本，留存原文摘要、修订、冲突和取消；同来源同版本异文不能覆盖旧证据。
- 地块影响：判断公示变更是否实质影响指定地块权益，案件绑定来源修订，公共信息变更会把旧案件标为失效。
- 异议处置：依据地块资格、版本和窗口判定受理或退回，回执逐项验版本、目标和时点；部分履约与逾期保留为独立结论。

正常和失败输入位于 `fixtures`。SQLite 使用事务保存新修订、业务评估与回执；`report` 从库中重建来源摘要、案件和履约状态。模拟来源不代表真实法律、医疗或安全结论；生产接入需要对外部来源真实性和凭据管理另行评估。

## 复测审查与签发工单

`map-review` 固定本轮纳入的来源版本（整卷），检验是否存在一套控制点坐标同时解释所有测量页；`map-plans` 回读某次审查保存的矛盾证据与全部最低成本方案；`map-issue` 就其中一个方案签发复测工单。

```powershell
python -m parcelcase map-import --db state.db --input fixtures/map_roll_jia.json   # 甲乙丙丁戊五卷同理
python -m parcelcase map-review --db state.db --source roll-jia:1 --source roll-yi:1 --source roll-bing:1 --source roll-ding:1 --source roll-wu:1
python -m parcelcase map-plans --db state.db --review 1
python -m parcelcase map-issue --db state.db --review 1 --plan 0
```

- 每张测量页给出终点减起点的毫米区间 `[low,high]`，坐标原点任取；审查按差约束求解，闭合环合成区间不含零即为矛盾。
- 复测按整卷发工单：每卷成本为其测量页复测成本合计，不能从卷中删去单张不合意的页；一次审查最多八卷、十二张页。
- 审查找出所有按整卷计的最小矛盾卷组（去掉任一卷即可一致），每组附可复核证据：闭合环经过的测量页、方向、合成位移区间及排除零的一侧。
- 方案为足以打断全部矛盾卷组且总成本最低的整卷集合；同价方案全部保留并列索引，由现场负责人选择其一签发，不取第一条矛盾环、不按卷号删除。
- 没有矛盾时 `map-issue` 以 `no_contradictions` 拒绝签发；工单记录所用卷版本、选定集合、现场测段、费用与需暂停公示的图幅（选定卷的图幅），同一方案重复签发返回原工单。
- 审查与工单按原文摘要存档：同一组来源版本重跑返回原审查（`existing`），新测量只能以新来源或新版本采入，旧审查与旧工单不被改写；`report` 的 `map_reviews`、`map_orders` 从库中重建全部证据。
- 剩余卷即使可求得一致坐标，在现场复测完成前只标记为 `unverified_pending_field_remeasure`，不称为地图已核真。

小样（`fixtures/map_roll_jia.json` 等五卷）：甲卷 A→B、D→E 位移为零，乙卷 B→C 为零，丙卷 A→C 为一百，丁卷 E→F 为零，戊卷 D→F 为一百。甲乙丙与甲丁戊各自成环矛盾，单看任一条环都会漏掉另一条；最低成本方案为甲卷单独复测（成本二，暂停 tile-1、tile-2）或丙戊两卷一起复测（成本二，暂停 tile-4、tile-6），两方案同价并存。

## 权属主张与邮戳证据

`title-claim` 独立登记地块权属主张，第二个竞争主张会生成 `title_dispute` 并把双方状态转为 disputed；`title-resolve` 记录裁定依据并恢复一个主张。此变化使原地块影响与异议资格失效，必须重评估。合成邮政来源提供 `postmark_at`、`postmark_ref` 时，晚到收件可按可信投递时点核销；缺证明仍逾期。正常、争议与恢复输入见 `fixtures/title_normal.json`、`fixtures/title_conflict.json`、`fixtures/objection_postmark.json`。真实投递证明的签名验证未接入。

