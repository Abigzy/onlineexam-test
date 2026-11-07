# OnlineExam 接口自动化测试 · 工作区

> 被测系统：`OnlineExam`（基于 Django 的 AI 在线考试与学情分析系统）
> 自动化工程：`onlineexam-api-autotest/onlineexam_api_autotest`（第 5 步起已解冻，骨架与 L0 冒烟已就绪）
> 流程：需求分析 → API 文档分析与评审 → 测试计划 → 用例设计与评审 → 环境搭建 → 执行用例 → 缺陷管理 → 测试报告

---

## 一、进度看板（中断后从这里续做）

| # | 阶段 | 状态 | 交付物 | 断点说明 |
|---|---|---|---|---|
| 0 | 准备：代码与文档通读、接口全集盘点 | ✅ 已完成 | `docs/assets/接口操作清单-124.txt`、`docs/assets/openapi.yaml` | 已生成 OpenAPI（25 warning / 125 error，接口仍可用） |
| 1 | 需求分析 | ✅ 已完成 | `docs/01-需求分析.md` | 范围、角色权限、10 条主链路、24 条可测点、13 项风险、10 个待确认问题 |
| 2 | API 文档分析与评审 | ✅ 已完成（V2 复核 11-03） | `docs/02-接口文档分析与评审.md` | V1 提 6 项问题，开发已修 5 项、1 项不彻底；残留 D-03R / D-01R / D-02R 见 §10 |
| 3 | 测试计划编写 | ✅ 已完成（11-03） | `docs/03-测试计划.md` | 5 层策略、约 215 条用例、13 人日、进入/准出标准、10 项风险、3 个默认假设 |
| 4 | 用例设计与评审 | ✅ 已完成（11-03） | `docs/04-测试用例.md`、`docs/04-用例评审记录.md`、`OnlineExam接口测试思维导图.xmind` | 264 条（正向 129 / 反向 135），P0 158；105 操作直接覆盖 + 19 同源合并 = 124/124；12 项评审问题已修订 |
| 5 | 环境搭建 | ✅ 已完成（11-03，标准结构对齐） | `docs/05-环境搭建.md`、`onlineexam_api_autotest/` 工程骨架 | 服务 8777 + MySQL 可用；**33 passed / 7.62s**、`report/report.html` 已生成；目录按标准分层（config.py + common + encap_api + scripts + data JSON） |
| 6 | 执行用例 | ✅ 已完成（11-03，含 3 轮修复回归） | `docs/06-执行记录.md`、`report/report.html`、`log/` | 全量 **229 passed / 0 failed / 0 xfail / 49.2s**（连跑两轮一致）；限流专项 2 条单独跑（`-m slow`）；总自动化 **229 条**；修复验证见 §11–§12 |
| 7 | 缺陷管理 | ✅ 已完成（11-03） | `docs/07-缺陷管理.md` | 缺陷 3 条（2 严重 + 1 一般）**全部关闭**：BUG-01 可见性口径、BUG-02 批量暂存 500、BUG-03 单题超时结算；观察项 10 条已收敛 |
| 8 | 测试报告 | ✅ 已完成（11-03） | `docs/08-测试报告.md` | 结论：**可以上线**（3 条缺陷全关闭、无 xfail 残留）；含覆盖分析、风险评估、放行建议、改进建议 |

**当前状态**：8 个阶段全部完成（11-03）。后续可选动作：

1. 回归：`pytest`（229 条 / 约 50 秒）。套件内已无 xfail，全部为普通用例；
2. 换环境复跑：先 `scripts/seed_env.py` 造数，再 `pytest`；
3. 新增用例：放进 `scripts/test_b*.py`，唯一约束字段务必带 `RUN_TAG`（见 `06-执行记录.md` §10.4）。

---

## 二、目录约定

```
onlineexam-api-autotest/
├── docs/
│   ├── README.md                     ← 本文件（进度看板）
│   ├── 01-需求分析.md
│   ├── 02-接口文档分析与评审.md
│   ├── 03-测试计划.md                （第 3 步产出）
│   ├── 04-测试用例.md                （第 4 步产出）
│   ├── 04-用例评审记录.md            （第 4 步产出）
│   ├── 05-环境搭建.md                （第 5 步产出）
│   ├── 06-执行记录.md                （第 6 步产出）
│   ├── 07-缺陷管理.md                （第 7 步产出）
│   ├── 08-测试报告.md                （第 8 步产出）
│   ├── 08-测试报告.md                （第 8 步产出）
│   ├── OnlineExam接口测试思维导图.xmind （第 4 步产出，正向 + 反向）
│   ├── OnlineExam接口测试思维导图-大纲.md （同源大纲，便于评审/检索）
│   └── assets/
│       ├── openapi.yaml              ← 由 `manage.py spectacular` 生成（接口事实来源）
│       ├── 接口操作清单-124.txt      ← 方法 + 路径全量清单
│       └── build_xmind.py            ← 由用例文档生成 xmind 的脚本
└── onlineexam_api_autotest/                ← 第 5 步起已解冻（目录按标准分层）
    ├── config.py                    常量入口
    ├── conftest.py                  角色客户端 + 常用 ID
    ├── common/                      配置/客户端/鉴权/断言/日志/数据/DB
    ├── encap_api/                   接口封装（7 个业务域模块）
    ├── data/                        账号池 + login_data.json
    ├── scripts/                     用例目录（check_env + test_l0_smoke + test_auth_login）
    ├── log/                         onlineexam.log（按天切分）
    └── report/                      report.html（pytest-html）
```

## 三、事实基线（后续所有文档引用这一份）

| 项 | 值 |
|---|---|
| 接口操作总数 | **124**（含 `/api/health/`），GET 61 / POST 42 / PUT 7 / PATCH 7 / DELETE 7 |
| 业务分组 | 14 组：auth、users、ai、knowledge-points、questions、papers、exams、attempts、grading、analytics、recommend、proctoring、classrooms、system（+ health） |
| 技术栈 | Django 4.2.30 / DRF 3.16.1 / SimpleJWT / MySQL 5.6（`.env` 当前 `DB_ENGINE=mysql`） |
| 鉴权 | JWT，`Authorization: Bearer <access>`；access 2h、refresh 7d 且轮换 |
| 统一响应体 | `{code, message, data}`；成功判定 **只看 `code == 0`** |
| 演示账号 | `admin` / `teacher` / `student` / `os_teacher` / `net_teacher` / `arch_teacher`，密码统一 `Exam@123456` |
| 已有功能测试资产 | `onlineexam-fun-test`（功能 246 条全通过、7 缺陷闭环；接口契约矩阵 124 操作 × 4 身份、661 断言 + 学生视角敏感字段黑名单；含性能报告） |
| 已有自动化基线 | 单测 1172 passed（2 skipped）、端到端冒烟 196 项、内联 JS 26 块 |
| 接口文档生成 | `python manage.py spectacular --file openapi.yaml`（25 warning / 125 error，不影响调用） |

## 四、纪律

1. **不臆造需求**：需求与实现冲突时，先记为"待确认问题"，用例中同时标注"实际行为"与"应然行为"。
2. **证据先行**：任何缺陷结论必须附"请求报文 + 响应报文 + 复现步骤 + 复现率"。
3. **数据可回收**：所有自动化造数带统一前缀（如 `at_<时间戳>`），执行后可识别清理，不污染演示数据。
4. **阶段冻结**：第 5 步之前不改 `onlineexam_api_autotest`；被测项目 `OnlineExam` 只读，除经确认的测试数据外不改代码。
