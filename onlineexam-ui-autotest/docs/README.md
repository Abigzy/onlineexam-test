# OnlineExam UI 自动化测试 · 工作区

> 被测系统：`D:/OnlineExam`（基于 Django 的 AI 在线考试与学情分析系统，服务端渲染页面层）
> 自动化工程：`D:/onlineexam-ui-autotest/onlineexam_ui_autotest`（**第 5 步之前不动**）
> 流程：需求分析与可行性评估 → 测试计划与策略 → 用例设计与数据准备 → 环境搭建与元素定位 → 框架设计与脚本开发 → 执行与监控 → 结果分析与报告
> 技术栈：pytest + Selenium 4.38 + Chrome 156（headless=new）+ **PO 模式** + **Allure 报告**（入口 `report/allure-report/uireport.html`）

---

## 一、进度看板（中断后从这里续做）

| # | 阶段 | 状态 | 交付物 | 断点说明 |
|---|---|---|---|---|
| 1 | 需求分析与自动化可行性评估 | ✅ 已完成（11-03） | `docs/01-需求分析与自动化可行性评估.md`、`docs/assets/step1_probe.py` | 结论：可行；范围 26/35 路由、约 140 条用例；8 个待确认问题（Q-01~Q-08）已按默认值预填 |
| 2 | 测试计划与策略 | ✅ 已完成（11-03） | `docs/02-测试计划与策略.md` | 定稿：150 条（P0 28/P1 74/P2 48）、L0/L1/L2 三层、11 条准出、Q-01~Q-08 全部关闭 |
| 3 | 用例设计与数据准备 | ✅ 已完成（11-03） | `docs/03-测试用例.md`、**`docs/OnlineExam UI测试思维导图.xmind`**、`OnlineExam UI测试思维导图-大纲.md`、造数清单（03 §4） | 定稿 150 条（P0 28/P1 74/P2 48；L0 15/L1 87/L2 48），13/13 主链路；单一数据源 `assets/cases_data.py`，改完跑 `assets/build_cases.py` 重生成三件产物 |
| 4 | 环境搭建与元素定位策略 | ✅ 已完成（11-04） | `docs/04-环境搭建与元素定位.md`、`tools/`（chromedriver 156、allure-2.30.0、check_env.py、probe_locators.py、locators.yaml、locator_report.json） | 环境 16/16、定位器 **307/307**（35 页）；两大坑已固化：代理劫持进程内清、驱动 156 显式指定 |
| 5 | 框架设计与脚本开发 | ✅ 已完成（11-05，**150/150 全部实现**，含补齐 `UI-SEC-07`） | `docs/05-框架设计与脚本开发.md`、`onlineexam_ui_autotest/`（config + common + `pages/` PO 页面类 + `scripts/`）、`report/allure-report/`、`docs/缺陷管理.md`、`tools/`（verify_bug01~04、cleanup_env） | **全量 151 passed / 3 skipped / 0 failed**（1071.35s ≈ 17m51s，退出码 0），收集 154 项，Allure 154 用例；四组新批次均连跑两轮一致（认证 14：75.8/75.8s、学情练习 13：87.8/88.9s、班级 6：49.7/50.1s、权限 8：49.2s、考试含粘贴 24：153.4s）；**BUG-01/02/03/04 全部关闭**；观察项 OBS-11/12/13 待产品确认。**断点：阶段 5 已收口，阶段 6/7 已完成** |
| 6 | 测试执行与监控 | ✅ 已完成（11-05） | `docs/06-执行记录.md`、`report/allure-report/`、`log/` | 三档跑通（冒烟 15 条 85.1s / 回归 135 项 / 全量 154 项 17m51s）；同范围连跑两轮通过数一致（151/3/0）；6 项监控指标有基线有红线；5 轮红（8 条）+ 2 次中断全部归因为脚本或环境，产品缺陷 0 |
| 7 | 结果分析与测试报告 | ✅ 已完成（11-05） | `docs/07-测试报告.md`、`report/allure-report/uireport.html` | **结论：可上线**（150 用例 100% 通过、4 缺陷全关闭）；3 个前提（OBS-11 下版修、仅 Chrome、无 CI）+ 6 项遗留风险 |

---

## 二、目录约定

```
D:/onlineexam-ui-autotest/
├── docs/
│   ├── README.md                          ← 本文件（进度看板）
│   ├── 01-需求分析与自动化可行性评估.md
│   ├── 02-测试计划与策略.md               （步骤 2）
│   ├── 03-测试用例.md                     （步骤 3）
│   ├── OnlineExam UI测试思维导图.xmind      （步骤 3）
│   ├── OnlineExam UI测试思维导图-大纲.md    （步骤 3，同源大纲，便于评审）
│   ├── 04-环境搭建与元素定位.md            （步骤 4）
│   ├── 05-框架设计与脚本开发.md            （步骤 5）
│   ├── 缺陷管理.md                         （4 缺陷 + 3 观察项，全程维护）
│   ├── 06-执行记录.md                      （步骤 6）
│   ├── 07-测试报告.md                      （步骤 7）
│   └── assets/                             ← 事实来源与脚本
│       ├── step1_probe.py                  步骤 1 可行性探针（一次性）
│       ├── cases_data.py                   **用例单一数据源（150 条）**
│       └── build_cases.py                  生成 03-测试用例.md + xmind + 大纲
├── tools/                                  ← 环境与定位（步骤 4 交付）
│   ├── chromedriver.exe                     Chrome 156 驱动（随工程入库）
│   ├── allure-2.30.0/                       Allure CLI（免联网生成报告）
│   ├── check_env.py                         环境自检 16 项
│   ├── probe_locators.py                    定位器实测（35 页 / 307 条）
│   ├── locators.yaml                        **定位器唯一事实来源**
│   ├── locator_report.json                  最近一次实测明细
│   ├── gen_report.sh                        **生成 Allure 报告并把入口命名为 uireport.html（bash）**
│   ├── gen_report.py                        同上，Python 版（PyCharm 里可直接右键 Run）
│   └── serve_report.sh                      **本地起静态服务看报告（file:// 会停在 Loading）**
└── onlineexam_ui_autotest/                 ← 步骤 5 起解冻
    ├── requirements.txt  Python 依赖（pytest / selenium / allure-pytest / requests / openpyxl）
    ├── pytest.ini      标记与 allure 输出目录（--clean-alluredir）
    ├── common/        配置、驱动工厂、等待封装、日志、数据、断言、报告生成（report_builder）
    ├── pages/         PO：每个页面一个类，定位器集中常量区
    ├── scripts/       用例目录（按业务域分文件）
    ├── data/          账号池、造数夹具、导入 excel
    ├── report/        Allure 原始结果 + 静态报告
    └── log/
```

---

## 三、纪律（本项目约定）

1. **被测项目只读**：不改 `D:/OnlineExam` 任何代码；元素无法定位时改定位策略，不要求开发加 id（除确有必要，走"待确认"）。
2. **不重复覆盖**：接口断言归接口自动化，页面扫荡归 `UI走查清单`，本套只守"交互后的状态变化"。
3. **数据带前缀**：所有造数 `UIAT_` 前缀，用后精确清理，不污染演示库（收工时实测：用户 183、活跃题 2423、班级 82，其中 `UIAT_` 用户/班级/未归档考试均为 0）。
4. **断言用事实**：断言可见 DOM 状态与文案，不断言像素、不断言接口报文、不赌具体秒数。
5. **不臆造需求**：需求与实现冲突记"待确认"，用例写双预期。
6. **单一数据源**：用例只改 `assets/cases_data.py`，跑 `build_cases.py` 重生成 md/xmind/大纲；生成器会断言条数与分布，不符直接报错。
7. **每阶段收尾更新本看板**，保证断点可续。
8. **跑全量前先归档旧结果**：`pytest.ini` 带 `--clean-alluredir`，Allure 插件启动会 `rmtree(report/allure-results)`；目录文件数超过 100 会触发运行环境的批量删除保护，表现为 `INTERNALERROR ... SystemExit: 1`（后台启动尤其容易撞上）。先 `mv report/allure-results report/allure-results_<轮次>` 再 `mkdir report/allure-results`，旧结果按轮次留档。
9. **改 PO 方法（新增/改名/删旧类）后必须 grep 全仓调用点**：第 4 批删重复类时漏了 L0 还在用的 `GradingPage.select_exam_by_index()`，直到全量才暴露 `AttributeError`。PO 是公共 API，改完至少跑一次 L0 冒烟 `pytest scripts/test_l0_smoke.py -q`。
10. **同一份数据的两个视图，必须等两者一致再断言**：组卷页 `#metaCount`（卷头统计）与 `#sheetBody .paper-q`（卷面卡片）由 `applyHead()` / `renderSheet()` 先后写入，只等其中一个就会出现「统计 3 题、卷面 0 题」的中间态（§4 第 39 条）。凡是「计数 ↔ 列表」「标题 ↔ 明细」这类双视图，等待条件写**两者相等**，不写「任意一个非空」。
11. **每次跑完用例都必须重新生成报告，这是必做动作不是可选项**：`pytest.ini` 带 `--clean-alluredir`，pytest 一启动就把 `report/allure-results` 清空（连 `environment.properties` 一起），所以跑完不生成，`report/allure-report/` 里躺的就是**上一轮的旧报告**——不报错、能打开，但结论是旧的，这种"看起来有报告"最危险。固定两条命令，二选一：`bash tools/gen_report.sh` 或 `D:/python/python.exe tools/gen_report.py`（等价，后者给 PyCharm/无声环境）。脚本一步做完 generate + 入口改名 `uireport.html` + 写环境信息 + 打印用例数；别手工 `allure generate`，会漏掉改名，出现"文档写 uireport、目录里只有 index"。

    **它已经默认替你做完了**：`config.AUTO_REPORT` 默认开启，会话收尾（`pytest_unconfigure`）自动生成，输出末尾多一行 `[auto-report] 154 条 / 6.3s -> …`。也就是说 `pytest` 一条命令就够，无需再记 `gen_report`。只在两种情况关掉（`OE_AUTO_REPORT=0`）：反复调单条用例不想每轮多等 5~15s；或 results 交给 CI 统一出报告。自动模式**永不改变退出码**——生成失败只打一行警告，用例通过就是通过。
