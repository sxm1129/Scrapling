# Antigravity 线上价格监测与控价闭环（Monitoring & Enforcement）DRD v2
> **文档类型**：Design Requirements Document（DRD）  
> **版本**：v2.0  
> **日期**：2026-03-11  
> **范围**：7×24 多平台低价监测、券后价取证、发货城市&店铺归因、白名单、责任人绑定、工单闭环  
> **v2新增**：接口级API设计、事件模型（Pub/Sub）、可执行测试用例集（验收清单）

---

## 0. 变更记录
| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-03-11 | 初版：模块拆分、需求、数据模型、调度与闭环 |
| v2.0 | 2026-03-11 | 补齐：API设计、事件模型、测试用例集、错误码与幂等策略 |

---

## 1. 背景与目标

### 1.1 背景
业务需要对线上渠道低价进行持续治理：从“周级人工汇总与催办”升级为“分钟/小时级自动发现与闭环处置”。低价场景覆盖：传统电商、内容电商、即时零售O2O、前置仓、社区团购等；价格受平台券、店铺券、跨店满减、补贴、会员、新客等规则影响，且存在“同链接不同人不同价”“同SKU不同城市/门店不同价”“多仓发货导致价差”等复杂性。

### 1.2 总目标（必须交付）
建立一套 **7×24** 的多平台价格监测系统，实现：
- **发现**：多平台低价自动发现（全天候、可扩展、可配置）
- **取证**：输出券类型、可核验券后价/到手价，并生成**截图证据链**
- **归因**：抽取发货城市&店铺信息，关联经销商；未知经销商支持“按发货城市兜底派单”
- **治理**：白名单过滤（审批通过的低价不作为违规展示/不触发处罚口径，但保留审计）
- **闭环**：每条低价链接自动绑定责任人，生成工单，SLA、升级、复核、复发统计、周报/月报/处罚台账

### 1.3 约束与原则
- **可审计**：数据、白名单、工单、处罚口径可追溯（含操作者、时间、附件证据）
- **可解释**：每条违规能解释“低在哪里”（券类型/补贴/门店/仓/新客等）
- **可降级**：券细则拿不到时保留“弱证据+低置信度”，避免误伤与噪音
- **幂等**：重复抓取不会重复建单；同一时间桶内只保留最新状态
- **配置驱动**：SKU池、城市池、频率、阈值、白名单、责任映射均可热更新
- **平台隔离**：采集器与截图服务按平台隔离并发与熔断，避免单平台故障拖垮全局

---

## 2. 范围（Scope）

### 2.1 覆盖平台
- 淘宝、天猫、拼多多
- 抖音、小红书
- O2O：淘宝闪购/美团闪购/京东秒送
- 前置仓：朴朴超市/小象超市/叮咚买菜
- 线上社区团购

> **落地建议**：一期（MVP）优先“淘宝/天猫/拼多多 + 重点SKU池”，先把证据链/归因/白名单/工单闭环跑通；二期扩展O2O/前置仓（城市×门店/仓）；三期扩展内容电商与团购广扫。

### 2.2 输出字段（必须）
1. 优惠券类型（标准化分类）
2. 实际折后价/到手价（必须截图证据）
3. 发货城市 & 店铺名称（用于关联经销商）
4. 白名单：审批通过低价不作为违规展示/不触发告警（但留痕审计）
5. 每条低价链接关联责任人（可配置规则自动分派）

### 2.3 监测频次
- 7×24运行
- 重点SKU/重点城市/重点店铺支持分钟级/十分钟级
- 广度扫描支持小时级/日级
- 活动期间支持事件触发加密（例如活动开始前后/爆量预警/竞品降价）

---

## 3. 角色与职责（RACI）
| 角色 | 职责 |
|---|---|
| 业务Owner（控价中台） | 定义口径、阈值、白名单审批、处罚规则、验收指标 |
| 大区/渠道负责人 | 处理派单、推进整改、回填结果、确认归因 |
| 电商运营对接 | 平台侧下架/改价/申诉/沟通 |
| 第三方（可选） | 补充未知经销商处理、平台投诉举证支持 |
| 研发（采集/后端/数据） | 采集器、证据链、规则引擎、工单系统、报表与监控 |
| 测试 | 功能/回归/性能/稳定性/安全测试 |
| 安全合规 | 账号/隐私/日志/审计与风险评估 |

---

## 4. 总体架构（High-level）

### 4.1 模块分层
1. **Scheduler（调度）**：生成监测任务（Job）
2. **Collector（采集器）**：抓取页面/接口，解析原始字段（RawOffer）
3. **Normalizer（标准化）**：统一schema输出（OfferSnapshot）
4. **Pricing Engine（价格引擎）**：计算券后价/到手价 + 置信度
5. **Evidence Service（证据链）**：截图、加水印、hash、存储
6. **Attribution Engine（归因）**：店铺/发货地→经销商/大区/责任人 + 置信度
7. **Policy Engine（规则&白名单）**：违规判定、等级、是否建单
8. **Workflow（工单&闭环）**：派单、SLA、升级、复核
9. **Reporting（报表&处罚台账）**
10. **Observability（监控告警）**

### 4.2 事件流（建议）
JobCreated → OfferCaptured → EvidenceReady → ViolationEvaluated → WorkOrderCreated/Updated → RecheckTriggered → ReportingAggregated

---

## 5. 核心概念与口径

### 5.1 价格口径
- **raw_price**：页面标价/常规价格
- **final_price**：根据可见规则计算出的券后/到手价
- **confidence（置信度）**
  - HIGH：券面额/门槛/适用条件可见，可复核
  - MED：部分可见，部分缺失（需标注缺失项）
  - LOW：仅展示到手价但券细则不可见（保留证据，告警降级）

### 5.2 券类型标准化（Coupon Taxonomy）
- PLATFORM_NO_THRESHOLD（平台无门槛券）
- PLATFORM_THRESHOLD（平台满减券）
- SHOP_NO_THRESHOLD（店铺无门槛券）
- SHOP_THRESHOLD（店铺满减券）
- CROSS_STORE_DISCOUNT（跨店满减/津贴）
- MEMBER_DISCOUNT（会员价/会员券）
- NEW_CUSTOMER_ONLY（新客专享）
- SUBSIDY（百亿补贴/平台/品牌补贴）
- FLASH_SALE（限时秒杀/限时直降）

### 5.3 违规口径（可配置）
- baseline_price：控价基准（MAP/建议零售价/项目价/供价等）
- 触发：final_price < baseline_price*(1-gap_percent) 或 baseline_price-final_price > gap_abs
- severity：P0/P1/P2（结合confidence与价差调整）

---

## 6. 功能需求（Functional Requirements）

### 6.1 监测覆盖
- FR-001 平台可配置与可扩展
- FR-002 目标类型：SKU池/店铺池/关键词池/链接池/门店仓池/团点位池
- FR-003 城市点位（O2O/前置仓）可配置
- FR-004 7×24调度自动循环

### 6.2 数据采集与解析
- FR-101 输出：标价、券入口、店铺信息、发货信息、可购买状态
- FR-102 支持跳转追踪并归一 canonical_url
- FR-103 接口优先，页面兜底
- FR-104 失败原因落库并纳入监控

### 6.3 价格计算
- FR-201 输出 final_price/discount_breakdown/confidence
- FR-202 输出 coupon_list（标准化券类型/面额/门槛/来源）
- FR-203 不可核验时降级不阻塞落库

### 6.4 证据链（截图）
- FR-301 三类截图：主页面/券弹窗/店铺&发货
- FR-302 水印：时间/平台/url短码/城市点位/任务id
- FR-303 integrity_hash 防篡改
- FR-304 截图失败重试≤2次，仍可PARTIAL落库

### 6.5 归因（经销商/责任人）
- FR-401 抽取 shop_id/shop_name/ship_from_city（O2O门店/仓）
- FR-402 归因优先级：shop_id→店名模糊→城市兜底→人工回流
- FR-403 输出confidence与reason_codes
- FR-404 dealer未知但发货城市已知：按城市→大区兜底派单
- FR-405 工单人工确认写回知识库（审计）

### 6.6 白名单
- FR-501 类型：项目/店铺/SKU/规则
- FR-502 命中：不作为违规展示/不触发告警/不入处罚口径（留痕）
- FR-503 必须包含审批人/有效期/范围/附件证据
- FR-504 到期自动失效、支持撤销

### 6.7 违规判定与工单
- FR-601 规则引擎输出 violation（含severity）
- FR-602 severity≥P1且未白名单：建工单
- FR-603 SLA + 超时升级
- FR-604 关闭触发复核；复核失败回滚并计复发
- FR-605 每条低价链接必须绑定责任人或兜底池

### 6.8 报表与处罚
- FR-701 周报/月报自动汇总
- FR-702 处罚台账导出
- FR-703 白名单命中趋势审计

---

## 7. 非功能需求（NFR）
- NFR-001 模块可独立扩缩容
- NFR-002 重点SKU端到端延迟目标≤15分钟（可配置）
- NFR-003 截图成功率≥95%（平台稳定期）
- NFR-101 反爬触发熔断与退避
- NFR-201 KMS托管凭据、RBAC、审计日志、日志脱敏

---

## 8. 数据模型（建议落库）

### 8.1 OfferSnapshot（报价快照）
字段：
- offer_id (uuid)
- platform (enum)
- url / canonical_url
- captured_at
- target_type / target
- city_context (json：city/store/warehouse/point)
- shop_id / shop_name
- ship_from_city
- raw_price
- coupon_list (json array)
- final_price
- confidence (HIGH/MED/LOW)
- discount_breakdown (json)
- evidence_id (fk)
- parse_status (OK/PARTIAL/FAIL) / fail_reason
- offer_hash

### 8.2 Evidence（证据链）
字段：
- evidence_id
- canonical_url / captured_at / city_context
- screenshot_main_key
- screenshot_coupon_keys (array)
- screenshot_shop_ship_key
- watermark_meta
- integrity_hash

### 8.3 Attribution（归因）
字段：
- offer_id
- dealer_id / region_id / owner_user_id
- confidence (0~1)
- reason_codes (array)
- created_at

### 8.4 WhitelistRule（白名单）
字段：
- rule_id / rule_type (PROJECT/SHOP/SKU/RULE)
- scope (platform/city/shop/sku)
- condition_json
- approved_by/approved_at/expires_at
- attachment_evidence_id
- status

### 8.5 Violation（违规判定）
字段：
- violation_id / offer_id / product_id
- baseline_price / gap_value / gap_percent
- severity (P0/P1/P2)
- is_whitelisted / policy_hit
- created_at

### 8.6 WorkOrder（工单）
字段：
- wo_id / violation_id / owner_user_id
- status (OPEN/IN_PROGRESS/WAITING_INFO/RESOLVED/REJECTED)
- sla_due_at / escalation_level
- action_log (json array)
- resolved_at / resolution_note
- recheck_offer_id / reoccur_count

---

## 9. 调度（Scheduler）细化

### 9.1 Job Schema（示例）
```json
{
  "job_id":"uuid",
  "platform":"TB",
  "task_type":"HOT_LOOP",
  "target_type":"SKU",
  "target":"product_id=123",
  "city_context":{"city":"上海"},
  "priority":"P0",
  "created_at":"...",
  "deadline_at":"...",
  "min_interval_sec":600,
  "retry_policy":{"max_retry":2,"backoff":"exp"}
}
```

### 9.2 频率策略（默认建议）
- 重点SKU：10分钟（活动期可1~5分钟）
- 次重点SKU：30分钟
- 广扫：2~6小时
- O2O/前置仓：重点城市全量门店/仓，非重点抽样

### 9.3 幂等
- offer_hash = hash(platform + canonical_url + city_context + time_bucket)
- time_bucket默认5分钟

---

## 10. 工单状态机与SLA

### 10.1 状态机
OPEN → IN_PROGRESS → RESOLVED  
OPEN/IN_PROGRESS → WAITING_INFO  
OPEN/IN_PROGRESS → REJECTED  

### 10.2 SLA（可配置建议）
- P0：2h响应 / 24h关闭
- P1：8h响应 / 48h关闭

### 10.3 升级
- 超时未响应：升级给上级（escalation_level+1）
- 超时未关闭：升级 + 标记处罚候选

### 10.4 复核
- RESOLVED 自动触发 RECHECK
- 复核仍低价：回滚 IN_PROGRESS，reoccur_count+1

---

# 11. API 设计（接口级）
> **风格**：REST（JSON）示例。也可等价转换为 gRPC/proto。  
> **鉴权**：OAuth2/JWT（内部）+ RBAC。  
> **幂等**：写接口支持 `Idempotency-Key` 头；服务端保存最近N小时key→response映射。  
> **分页**：list接口统一 `page_size`（默认50，最大500）+ `page_token`。

## 11.1 通用约定
### 11.1.1 Headers
- `Authorization: Bearer <token>`
- `X-Request-Id: <uuid>`（可选，链路追踪）
- `Idempotency-Key: <uuid>`（POST/PUT/patch推荐）

### 11.1.2 通用错误码（HTTP + 业务码）
| HTTP | code | 含义 | 处理建议 |
|---|---|---|---|
| 400 | INVALID_ARGUMENT | 参数非法/缺字段 | 客户端修正 |
| 401 | UNAUTHENTICATED | 未鉴权/过期 | 刷新token |
| 403 | PERMISSION_DENIED | 无权限 | 申请权限 |
| 404 | NOT_FOUND | 资源不存在 | 检查id |
| 409 | CONFLICT | 幂等冲突/状态冲突 | 读取最新状态后重试 |
| 412 | PRECONDITION_FAILED | 版本不匹配（乐观锁） | 携带最新etag重试 |
| 429 | RESOURCE_EXHAUSTED | 限流 | 退避重试 |
| 500 | INTERNAL | 服务内部错误 | 走重试/降级 |
| 503 | UNAVAILABLE | 依赖不可用 | 退避重试 |

错误响应示例：
```json
{
  "code":"INVALID_ARGUMENT",
  "message":"page_size must be <= 500",
  "details":{"field":"page_size","limit":500}
}
```

### 11.1.3 枚举（核心）
- platform：TB/TM/PDD/DY/XHS/O2O_MT/O2O_JD/O2O_TB/FZC_PP/FZC_DD/FZC_XS/COMMUNITY
- confidence：HIGH/MED/LOW
- severity：P0/P1/P2
- work_order_status：OPEN/IN_PROGRESS/WAITING_INFO/RESOLVED/REJECTED
- whitelist_type：PROJECT/SHOP/SKU/RULE

---

## 11.2 Offers API
### 11.2.1 查询报价快照列表
`GET /v1/offers?page_size=50&page_token=...&platform=TB&captured_after=...&captured_before=...&shop_id=...&product_id=...&severity=P1`

返回：
```json
{
  "offers":[
    {
      "offer_id":"...",
      "platform":"TB",
      "canonical_url":"...",
      "captured_at":"2026-03-11T10:00:00Z",
      "city_context":{"city":"上海"},
      "shop":{"shop_id":"123","shop_name":"XX旗舰店"},
      "shipping":{"ship_from_city":"杭州"},
      "price":{"raw_price":199.0,"final_price":169.0,"confidence":"HIGH"},
      "coupons":[{"type":"PLATFORM_THRESHOLD","amount":30,"threshold":199,"verifiable":true}],
      "evidence_id":"..."
    }
  ],
  "next_page_token":"..."
}
```

### 11.2.2 获取单条报价快照
`GET /v1/offers/{offer_id}`

### 11.2.3 触发一次手动抓取（可选：给运营/测试）
`POST /v1/offers:collect`
```json
{
  "platform":"TB",
  "target_type":"URL",
  "target":"https://....",
  "city_context":{"city":"上海"},
  "priority":"P0"
}
```
返回：
```json
{"job_id":"...","status":"QUEUED"}
```

---

## 11.3 Evidence API
### 11.3.1 获取证据链元信息
`GET /v1/evidence/{evidence_id}`

返回：
```json
{
  "evidence_id":"...",
  "captured_at":"...",
  "platform":"TB",
  "canonical_url":"...",
  "city_context":{"city":"上海"},
  "screenshots":{
    "main_url":"https://signed-url/main.png",
    "coupon_urls":["https://signed-url/coupon1.png"],
    "shop_shipping_url":"https://signed-url/ship.png"
  },
  "integrity_hash":"sha256:..."
}
```
> **说明**：图片访问使用短期签名URL；访问需要权限（RBAC）并记录审计。

---

## 11.4 Violations API
### 11.4.1 查询违规列表
`GET /v1/violations?severity=P1&is_whitelisted=false&created_after=...&region_id=...`

返回：
```json
{
  "violations":[
    {
      "violation_id":"...",
      "offer_id":"...",
      "product_id":"...",
      "baseline_price":199.0,
      "final_price":169.0,
      "gap_percent":0.151,
      "severity":"P1",
      "is_whitelisted":false,
      "policy_hit":"rule-123",
      "created_at":"..."
    }
  ],
  "next_page_token":"..."
}
```

### 11.4.2 获取单条违规详情（含归因/工单引用）
`GET /v1/violations/{violation_id}`

---

## 11.5 WorkOrders API
### 11.5.1 查询工单列表
`GET /v1/workorders?status=OPEN&severity=P0&owner_user_id=...&sla_due_before=...`

返回：
```json
{
  "workorders":[
    {
      "wo_id":"...",
      "violation_id":"...",
      "status":"OPEN",
      "owner_user_id":"u-123",
      "sla_due_at":"...",
      "escalation_level":0,
      "reoccur_count":2
    }
  ],
  "next_page_token":"..."
}
```

### 11.5.2 获取工单详情
`GET /v1/workorders/{wo_id}`

### 11.5.3 更新工单状态（带乐观锁）
`PATCH /v1/workorders/{wo_id}`
Headers: `If-Match: "<etag>"`

Body（示例：开始处理）：
```json
{
  "status":"IN_PROGRESS",
  "note":"已联系平台运营，下架处理中"
}
```

### 11.5.4 追加工单动作（推荐：可审计）
`POST /v1/workorders/{wo_id}:actions`
```json
{
  "action_type":"LINK_TAKEDOWN",
  "note":"店铺已下架该链接",
  "attachment_evidence_id":"evi-xxx"
}
```

### 11.5.5 人工确认归因（回写知识库）
`POST /v1/workorders/{wo_id}:confirmAttribution`
```json
{
  "dealer_id":"d-789",
  "shop_id":"123",
  "shop_name":"XX旗舰店",
  "platform":"TB",
  "valid_to":"2027-03-11T00:00:00Z",
  "note":"经销商确认来自历史OA名单",
  "attachment_evidence_id":"evi-yyy"
}
```

### 11.5.6 关闭工单并触发复核
`POST /v1/workorders/{wo_id}:resolve`
```json
{
  "resolution_note":"已改价恢复到199元",
  "resolution_type":"PRICE_FIXED"
}
```
返回：
```json
{"status":"RESOLVED","recheck_job_id":"..."}
```

---

## 11.6 Whitelists API
### 11.6.1 创建白名单规则（需审批权限）
`POST /v1/whitelists`
```json
{
  "rule_type":"PROJECT",
  "scope":{
    "platforms":["TB","TM"],
    "product_ids":["p-123","p-456"],
    "cities":["上海","杭州"]
  },
  "condition":{
    "price_type":"PROJECT_PRICE",
    "note":"已报备项目价，避免平台比价跟价"
  },
  "expires_at":"2026-06-30T00:00:00Z",
  "attachment_evidence_id":"evi-approve-001"
}
```

返回：
```json
{"rule_id":"wl-001","status":"ACTIVE"}
```

### 11.6.2 查询白名单规则
`GET /v1/whitelists?status=ACTIVE&rule_type=PROJECT`

### 11.6.3 撤销白名单
`POST /v1/whitelists/{rule_id}:revoke`
```json
{"reason":"项目结束，白名单到期前撤销"}
```

---

## 11.7 Reporting API（可选）
### 11.7.1 生成周报
`POST /v1/reports:generateWeekly`
```json
{"week_start":"2026-03-02","week_end":"2026-03-08"}
```

### 11.7.2 获取报表下载链接
`GET /v1/reports/{report_id}`

---

# 12. 事件模型（Pub/Sub / Kafka）
> **目的**：解耦采集、截图、判定、建单、通知、报表。  
> **要求**：事件必须可重放；消费者幂等（以event_id去重）。

## 12.1 通用事件Envelope
```json
{
  "event_id":"uuid",
  "event_type":"OfferCaptured",
  "occurred_at":"2026-03-11T10:00:00Z",
  "producer":"collector-tb",
  "trace_id":"uuid",
  "payload":{...}
}
```

## 12.2 Topic 列表
| Topic | event_type | 生产者 | 消费者 |
|---|---|---|---|
| antigravity.jobs | JobCreated | Scheduler | Collector |
| antigravity.offers | OfferCaptured | Collector/Normalizer | EvidenceSvc / Pricing / Attribution / Policy |
| antigravity.evidence | EvidenceReady | EvidenceSvc | Policy / UI / Audit |
| antigravity.violations | ViolationCreated | Policy | Workflow / Notification / Reporting |
| antigravity.workorders | WorkOrderCreated/Updated | Workflow | Notification / Reporting |
| antigravity.recheck | RecheckTriggered | Workflow | Scheduler/Collector |
| antigravity.reports | ReportReady | Reporting | 邮件/下载服务 |

## 12.3 事件payload定义（关键）
### 12.3.1 OfferCaptured
```json
{
  "offer_id":"...",
  "platform":"TB",
  "canonical_url":"...",
  "captured_at":"...",
  "city_context":{"city":"上海"},
  "shop":{"shop_id":"123","shop_name":"XX旗舰店"},
  "shipping":{"ship_from_city":"杭州"},
  "price":{"raw_price":199.0,"display_final_price":169.0},
  "coupon_raw":[...],
  "parse_status":"OK"
}
```

### 12.3.2 EvidenceReady
```json
{
  "offer_id":"...",
  "evidence_id":"...",
  "screenshots":{
    "main_key":"gs://.../main.png",
    "coupon_keys":["gs://.../c1.png"],
    "shop_shipping_key":"gs://.../ship.png"
  },
  "integrity_hash":"sha256:..."
}
```

### 12.3.3 ViolationCreated
```json
{
  "violation_id":"...",
  "offer_id":"...",
  "product_id":"p-123",
  "baseline_price":199.0,
  "final_price":169.0,
  "gap_percent":0.151,
  "severity":"P1",
  "is_whitelisted":false,
  "policy_hit":"rule-123",
  "attribution":{
    "dealer_id":"d-789",
    "region_id":"r-east",
    "owner_user_id":"u-123",
    "confidence":0.92
  }
}
```

### 12.3.4 WorkOrderCreated
```json
{
  "wo_id":"...",
  "violation_id":"...",
  "owner_user_id":"u-123",
  "status":"OPEN",
  "sla_due_at":"...",
  "escalation_level":0
}
```

### 12.3.5 RecheckTriggered
```json
{
  "wo_id":"...",
  "violation_id":"...",
  "platform":"TB",
  "canonical_url":"...",
  "city_context":{"city":"上海"},
  "priority":"P0",
  "reason":"RESOLVED_RECHECK"
}
```

---

# 13. 测试用例集（Test Cases & Acceptance Checklist）
> **用法**：QA可直接按表执行；每条用例要求“输入/操作/预期输出/证据”。  
> **标记**：P0=必测阻断，P1=核心路径，P2=回归/边界。

## 13.1 采集与解析（平台通用）
| 用例ID | 优先级 | 场景 | 前置条件 | 操作 | 预期结果 |
|---|---|---|---|---|---|
| TC-COL-001 | P0 | 正常采集单链接 | 平台可访问 | 手动触发 collect | OfferSnapshot落库，parse_status=OK |
| TC-COL-002 | P0 | 跳转归一 | 短链/中转链 | collect短链 | canonical_url稳定一致 |
| TC-COL-003 | P0 | 解析失败落库 | 构造DOM变更/404 | collect | parse_status=FAIL，fail_reason有值 |
| TC-COL-004 | P1 | 反爬限流降级 | 模拟429/blocked | 连续高频collect | 触发退避/熔断，系统不雪崩 |
| TC-COL-005 | P1 | 城市点位注入 | O2O/前置仓 | collect不同城市 | city_context正确、价格可区分 |

## 13.2 价格引擎（券类型/到手价）
| 用例ID | 优先级 | 场景 | 输入 | 操作 | 预期结果 |
|---|---|---|---|---|---|
| TC-PRC-001 | P0 | 可核验满减券 | 有面额/门槛 | 运行Pricing | confidence=HIGH，final_price正确 |
| TC-PRC-002 | P0 | 店铺券+平台券叠加 | 多券可见 | Pricing | discount_breakdown包含两项 |
| TC-PRC-003 | P1 | 新客券识别 | 标注新客 | Pricing | coupon.type=NEW_CUSTOMER_ONLY |
| TC-PRC-004 | P1 | 仅展示到手价 | 券细则缺失 | Pricing | confidence=LOW，仍保留final_price |
| TC-PRC-005 | P2 | 多券择优（一期贪心） | 多种组合 | Pricing | 选取最大折扣组合并可解释 |

## 13.3 证据链（截图/水印/防篡改）
| 用例ID | 优先级 | 场景 | 操作 | 预期结果 |
|---|---|---|---|---|
| TC-EVI-001 | P0 | 证据三截图齐 | 抓取触发Evidence | main/coupon/shop_shipping三类截图均生成 |
| TC-EVI-002 | P0 | 水印正确 | 查看截图 | 含时间/平台/url短码/city/job_id |
| TC-EVI-003 | P1 | integrity_hash一致 | 读取evidence | hash字段存在且格式正确 |
| TC-EVI-004 | P1 | 截图失败重试 | 模拟浏览器失败 | 重试≤2次，最终PARTIAL并记录原因 |
| TC-EVI-005 | P2 | 权限控制与审计 | 无权限用户访问图片 | 返回403并记录审计 |

## 13.4 归因（店铺/城市兜底/人工回流）
| 用例ID | 优先级 | 场景 | 前置 | 操作 | 预期结果 |
|---|---|---|---|---|---|
| TC-ATR-001 | P0 | shop_id精确归因 | dealer_shop_map已存在 | 生成Offer | dealer_id命中，confidence≥0.9 |
| TC-ATR-002 | P1 | 店铺名模糊归因 | alias表存在 | 生成Offer | dealer_id命中，reason_codes含NAME_FUZZY |
| TC-ATR-003 | P0 | 城市兜底派单 | dealer未知但ship_from_city已知 | 触发建单 | owner来自region_city_map兜底 |
| TC-ATR-004 | P1 | 兜底池 | shop/城市均未知 | 建单 | owner=兜底池，confidence低 |
| TC-ATR-005 | P0 | 人工确认回流 | 有工单 | confirmAttribution | 知识库写入、后续同店铺命中 |

## 13.5 白名单（审批/命中/到期/撤销）
| 用例ID | 优先级 | 场景 | 操作 | 预期结果 |
|---|---|---|---|---|
| TC-WL-001 | P0 | 创建项目白名单 | POST /whitelists | rule ACTIVE，审计字段齐全 |
| TC-WL-002 | P0 | 命中白名单不建单 | 触发低价 | is_whitelisted=true，且不创建工单（或记录型） |
| TC-WL-003 | P1 | 到期自动失效 | 设置短有效期 | 到期后不再命中 |
| TC-WL-004 | P1 | 撤销立即生效 | revoke | 后续抓取不命中 |
| TC-WL-005 | P2 | 防滥用监控 | 批量创建白名单 | 指标与告警触发 |

## 13.6 违规判定与工单闭环（SLA/升级/复核/复发）
| 用例ID | 优先级 | 场景 | 操作 | 预期结果 |
|---|---|---|---|---|
| TC-WO-001 | P0 | P1违规自动建单 | 触发低价 | workorder=OPEN且owner正确 |
| TC-WO-002 | P0 | SLA倒计时与升级 | 模拟超时 | escalation_level+1并通知 |
| TC-WO-003 | P0 | 关闭触发复核 | resolve | recheck_job创建，复核offer产生 |
| TC-WO-004 | P0 | 复核失败回滚 | 仍低价 | 工单回滚IN_PROGRESS，reoccur_count+1 |
| TC-WO-005 | P1 | REJECTED需记录原因 | reject | 工单状态REJECTED，审计完整 |

## 13.7 报表与处罚台账
| 用例ID | 优先级 | 场景 | 操作 | 预期结果 |
|---|---|---|---|---|
| TC-RPT-001 | P1 | 周报生成 | generateWeekly | 产出平台/大区/经销商/复发汇总 |
| TC-RPT-002 | P1 | 月报处罚导出 | generateMonthly（可选） | 处罚计分符合规则、白名单不计入处罚 |
| TC-RPT-003 | P2 | 权限控制 | 无权限导出 | 403 + 审计记录 |

## 13.8 关键验收门槛（建议）
- 截图成功率 ≥ 95%
- 解析成功率 ≥ 90%（平台稳定期）
- 可派单覆盖率 ≥ 70%（含城市兜底）
- 重点SKU端到端延迟 ≤ 15分钟（可调整）
- P0工单SLA达成率 ≥ 90%（上线后观察期）

---

# 14. 附录

## 14.1 action_log枚举建议
- PRICE_FIXED（改价）
- LINK_TAKEDOWN（下架）
- PLATFORM_COMPLAINT（平台投诉/举证）
- WHITELIST_REQUEST（申请白名单）
- CONFIRM_DEALER（确认经销商归因）
- RECHECK_PASSED / RECHECK_FAILED（复核结果）

## 14.2 幂等策略说明（关键写接口的人会用到）
- 对 `POST /whitelists`、`POST /workorders/{id}:actions`、`POST /workorders/{id}:resolve` 等写接口：
  - 客户端提供 `Idempotency-Key`
  - 服务端按（key + endpoint + user_id）存储最近N小时响应
  - 若重复请求：返回首次响应（HTTP 200/201），避免重复建单/重复写库
- 对事件消费：以 event_id 去重（存offset + event_id短期缓存），确保“至少一次投递”不会造成重复副作用

---

> **说明**：本v2已经具备“接口级DRD+事件模型+测试清单”，工程团队可据此拆分服务、定义proto/表结构并进入实现。  
