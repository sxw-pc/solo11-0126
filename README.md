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

- 公示采信：确认公示起止时刻和取代链的有效版本，留存原文摘要、修订、冲突和取消；同来源同版本异文不能覆盖旧证据。
- 地块影响：判断公示变更是否实质影响指定地块权益，案件绑定来源修订，公共信息变更会把旧案件标为失效。
- 异议处置：依据地块资格、版本和窗口判定受理或退回，回执逐项验版本、目标和时点；部分履约与逾期保留为独立结论。

正常和失败输入位于 `fixtures`。SQLite 使用事务保存新修订、业务评估与回执；`report` 从库中重建来源摘要、案件和履约状态。模拟来源不代表真实法律、医疗或安全结论；生产接入需要对外部来源真实性和凭据管理另行评估。

## 权属主张与邮戳证据

`title-claim` 独立登记地块权属主张，第二个竞争主张会生成 `title_dispute` 并把双方状态转为 disputed；`title-resolve` 记录裁定依据并恢复一个主张。此变化使原地块影响与异议资格失效，必须重评估。合成邮政来源提供 `postmark_at`、`postmark_ref` 时，晚到收件可按可信投递时点核销；缺证明仍逾期。正常、争议与恢复输入见 `fixtures/title_normal.json`、`fixtures/title_conflict.json`、`fixtures/objection_postmark.json`。真实投递证明的签名验证未接入。

