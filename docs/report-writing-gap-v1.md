# Report 与 Nature Physics Perspective / Loom_Science 的差距

## 已读参照

- `data/report/style_samples/10_1038_s41567-020-0834-8.pdf`（Nature Physics Perspective）
- `loom_science/style/macro_prompt_en.md`（L1 宪法）
- `loom_science/style/L2_narrative_syntax_en.md`（L2 叙事语法）
- `loom_science/style/L3_yanjiang_aesthetic_en.md`（L3 审美）
- `loom_science/insights/better_prose.md`
- `loom_science/insights/prose_regulation_report.md`
- `loom_science/insights/on_peer_review.md`
- `loom_science/docs/prompt_system_map_v1.md`

## 关键差距

| 维度 | Nature / Loom_Science | 早期 Report |
|---|---|---|
| 开篇 | 领域问题 + 为什么旧解释不够 | 直接抛中心论点/摘要 |
| 路线 | 先告诉读者认知顺序 | 无路线图 |
| 段落 | 一段一个认知任务，2–5 句 | 证据、限定、判断混在一段 |
| 概念 | 直觉层 → 技术层 → 意义层 | 术语直接进入论证 |
| 类比 | 降低门槛，且有边界 | 很少 |
| 标题 | 短、有动作/张力 | 长问句 |
| 收尾 | 回答开篇 + 可检验下一步 | 反复“证据不足” |
| 审稿 | 先优点，再问题，再修法 | 只挑错 |

## Report 更难的原因

Report 不是单篇论文改写，而是多来源综合：

```text
问题
→ 来源群
→ claim 图
→ 证据层级
→ 争议地图
→ 论点
→ 分节写作
→ 读者模型/路线图
→ 审稿
```

单篇论文有现成叙事；Report 必须自己构造叙事，同时保留来源冲突。
因此 Report 需要额外的：

1. claim graph：哪些 claim 互相支持/冲突；
2. source hierarchy：理论/数值/单一实验/独立复现；
3. uncertainty map：哪些判断依赖样品、应变、解理条件；
4. reader model：读者先要知道什么，才能理解争议。

## 已落地

- `prompts/report_perspective_zh.md`
- `loomsci_report/style.py`：可选加载 Loom_Science L1/L2
- `pipeline`：`reader_model`、`roadmap`、`section.question`、段落规则、标题约束
- `review.py`：strengths / fix / extra_query
- `format.py`：人类可读证据与核验，不输出 JSON
- `export.py`：MD / PDF / EPUB

## 仍未完成

- OpenAlex/Crossref 主检索，arXiv 仅补充；
- 全文 claim 核查与 L1/L2/L3；
- 两轮编辑：认知负荷编辑 + 语言编辑；
- OA 图表；
- 人工盲评。
