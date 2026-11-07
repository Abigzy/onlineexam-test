# OnlineExam 测试仓库

> **被测系统**：[`onlineexam-system`](https://github.com/Abigzy/onlineexam-system) —— 基于 Django 的 AI 在线考试与学情分析系统（11 个模块 / 124 个 REST 接口 / 246 条功能用例）。
>
> 本仓库是它的**配套测试工程**，独立维护四层测试资产：**功能测试、接口自动化、UI 自动化、性能测试**。
> 被测系统与测试工程分仓，是为了避免两边各自演化、口径漂移。

---

## 测试成果总览

四层测试累计发现并推动修复 **14 个缺陷**（功能 7 + 接口 3 + UI 4），其中 **4 个严重**：
学生考中可从作答明细接口取走全部参考答案、成绩可见性存在两套相反的判定、
批量暂存遇重复题目导致整批 500 且已答数据全丢、组卷页知识点筛选静默失效。

| 层次 | 目录 | 技术栈 | 用例规模 | 结果 |
|---|---|---|---|---|
| 功能测试 | `onlineexam-fun-test/` | 手工 + 用例基线（xlsx/xmind/md） | **246 条** | 246 通过 / 0 失败 / 0 阻塞，7 缺陷全修复 |
| 接口自动化 | `onlineexam-api-autotest/` | pytest + requests（标准分层） | **229 条** | 229 passed / 0 failed / 0 xfail（49.2s），3 缺陷全关闭 |
| UI 自动化 | `onlineexam-ui-autotest/` | pytest + Selenium 4.38 + PO + Allure | **150 条**（P0 28 / P1 74 / P2 48） | 154 项（150 用例 + 4 缺陷守卫）→ 151 passed / 3 skipped / 0 failed（17m51s），4 缺陷全关闭 |
| 性能测试 | `onlineexam-performance-testing/` | Locust 2.47.0 | 50 并发验收 + 三组环境对照 | 连接复用后 45.2 RPS / P95 0.84s，四场景达标 |

> 四层测试的详细过程文档、用例基线、执行记录、缺陷单都在各自目录的 `docs/` 与报告文件中，见下文「各模块说明」。

---

## 目录结构

> 只列**仓库里实际存在**的内容。运行期缓存、日志、真实 token、chromedriver、Allure CLI、
> 性能压测的中间轮次/对照组/原始 CSV 等已被 `.gitignore` 排除，不在仓库中；
> 各层**最终版报告**（接口 pytest-html、UI Allure、性能 opt 系列 HTML）已入库，见下文「报告产物入口」。

```
onlineexam-test/
├── README.md / .gitignore / .gitattributes / LICENSE
│
├── onlineexam-fun-test/               功能测试（文档与用例基线）
│   ├── OnlineExam-功能测试用例.xlsx      246 条用例基线（v2.0）
│   ├── 测试用例.md                       用例明细
│   ├── 需求分析与测试点.xmind            测试点导图
│   └── 功能测试报告.md                   上线评估版报告（结论：可上线）
│
├── onlineexam-api-autotest/           接口自动化测试
│   ├── docs/                            8 篇过程文档 + 思维导图 + assets（openapi.yaml）
│   └── onlineexam_api_autotest/         pytest 工程
│       ├── config.py / conftest.py / pytest.ini / requirements.txt
│       ├── common/                      断言器 / 客户端 / 认证 / 数据库 / 日志
│       ├── encap_api/                   按模块封装的接口层（admin/auth/content/exam/grading/insight）
│       ├── scripts/                     20 个测试脚本（L0 冒烟 → B1~B12 分模块）
│       ├── data/                        账号池 / 造数 fixtures / 登录数据
│       └── report/report.html           全量 pytest-html 报告（已入库）
│
├── onlineexam-ui-autotest/            UI 自动化测试
│   ├── docs/                            7 篇过程文档 + 缺陷管理 + 思维导图 + assets
│   ├── onlineexam_ui_autotest/          pytest 工程
│   │   ├── config.py / conftest.py / pytest.ini / requirements.txt
│   │   ├── common/                      驱动工厂 / PO 基类 / 组件 / 数据工厂 / 报告构建
│   │   ├── pages/                       35 个页面的 Page Object（admin/auth/analytics/student/teacher/security）
│   │   ├── scripts/                     13 个测试脚本（L0 冒烟 → L1 分模块 → 回归）
│   │   ├── data/                        导入样例 xlsx 等测试数据
│   │   └── report/allure-report/        Allure 全量报告（已入库）
│   └── tools/                           环境自检 / 定位器探测 / 缺陷复现验证脚本
│
└── onlineexam-performance-testing/    性能测试
    ├── docs/                            6 篇过程文档（方案/计划/场景/执行/报告 + 历史基线）
    └── onlineexam_performance_testing/  Locust 工程
        ├── locustfile.py                三场景用户类（交卷 / 开考读峰 / 判分）
        ├── perf_settings.py             压测专用 Django 配置（DEBUG=False、连接复用）
        ├── scripts/                     造数 / 起服务 / 压测 / 汇总脚本
        ├── requirements.txt / .run/     依赖清单 + PyCharm 运行配置说明
        └── report/opt_*.html            最终版压测报告 9 份（连接复用优化后，已入库）
```

---

## 各模块说明

### 1. 功能测试 `onlineexam-fun-test/`

- **范围**：用户与认证、权限与越权、AI 适配层、题库与知识点、试卷与组卷（含随机组卷）、
  在线考试、判分与成绩、学情分析、个性化推荐、作弊检测、班级管理、管理端。
- **结论**：246 条用例全部执行，**246 通过 / 0 失败 / 0 阻塞**；7 个缺陷全部修复并回归通过。
- **交付物**：用例基线 `OnlineExam-功能测试用例.xlsx`、测试点导图 `需求分析与测试点.xmind`、报告 `功能测试报告.md`。

### 2. 接口自动化 `onlineexam-api-autotest/`

- **技术栈**：pytest + requests，目录按标准分层（`config.py + common + encap_api + scripts + data`）。
- **规模**：229 条（正向 129 / 反向 135 中的可自动化部分，覆盖 124/124 个接口操作）。
- **结论**：全量 **229 passed / 0 failed / 0 xfail**（约 49.2s，连跑两轮一致）；3 个缺陷（2 严重 + 1 一般）全部关闭。
- **运行**：先起被测服务（`python manage.py runserver 127.0.0.1:8777`），再 `cd onlineexam_api_autotest && pytest`。
  详见 `docs/05-环境搭建.md` 与 `docs/README.md`。
- **报告**：全量报告 `onlineexam_api_autotest/report/report.html`（pytest-html，已入库）。

### 3. UI 自动化 `onlineexam-ui-autotest/`

- **技术栈**：pytest + Selenium 4.38 + Chrome 156（headless）+ **PO 模式** + **Allure 报告**。
- **规模**：150 条用例（P0 28 / P1 74 / P2 48；L0 15 / L1 87 / L2 48），另加 **4 条缺陷守卫用例**，共 35 页 / 307 个定位器。
- **结论**：全量收集 **154 项**（150 用例 + 4 守卫）→ **151 passed / 3 skipped / 0 failed**（约 17m51s）；
  3 条 skipped 为「30s 自动暂存」用例（主动排除、已单独验证通过），非跑不过；4 个缺陷全部关闭。
- **运行**：自备 chromedriver（见 `.gitignore` 说明），`cd onlineexam_ui_autotest && pytest`。
- **报告**：Allure 全量报告已入库，本地打开 `onlineexam_ui_autotest/report/allure-report/uireport.html`。

### 4. 性能测试 `onlineexam-performance-testing/`

- **技术栈**：Locust 2.47.0，压测专用 `DEBUG=False` 配置 + 独立压测库 `online_exam_perf`。
- **结论**：系统本身无写坏的代码，慢的根因是**每请求重开一次 MySQL 连接**；
  打开连接复用后，50 并发从 12.8 RPS / P95 3.8s 提升到 **45.2 RPS / P95 0.84s**，
  交卷、开考读峰、判分、混合四场景全部达标。唯一未达标档「50 人同一秒点交卷」
  已定位为线程池排队，加线程 + 前端错峰可解。
- **运行**：`cd onlineexam_performance_testing`，按 `.run/README.md` 或 `docs/02-测试计划与环境搭建.md` 的 6 个场景执行。
- **报告**：最终版压测报告 9 份已入库，本地打开 `report/opt_*.html`（如 `opt_submit50.html` 交卷验收线、`opt_mix50.html` 混合场景）。

---

## 报告产物入口

各层的**最终版可视化报告**已入库（GitHub 网页上 HTML 不渲染，`clone` 后本地双击打开即可看）：

| 层次 | 报告文件 | 内容 |
|---|---|---|
| 接口自动化 | `onlineexam-api-autotest/onlineexam_api_autotest/report/report.html` | 229 条用例的 pytest-html 全量报告 |
| UI 自动化 | `onlineexam-ui-autotest/onlineexam_ui_autotest/report/allure-report/uireport.html` | 154 项用例的 Allure 报告（含步骤/截图/日志） |
| 性能测试 | `onlineexam-performance-testing/onlineexam_performance_testing/report/opt_*.html` | 连接复用优化后 9 个场景的 Locust 报告（RPS/P95 曲线） |

> **打开方式**：Locust 报告为自包含 HTML（内嵌 ECharts，双击即可打开）；Allure 报告是「入口 + data 目录」结构，
> 需起静态服务器后查看：`cd report/allure-report && python -m http.server 8899` 再访问 `http://127.0.0.1:8899/uireport.html`（或 `bash tools/serve_report.sh`、`allure open`）。
> 性能中间轮次、对照组、原始 CSV 未入库，需要完整数据可本地重跑（命令见各模块 `docs/`）。

---

## 快速开始

四层测试的依赖不同，请**分别**进入对应目录查看 `requirements.txt` 与 `docs/README.md`。
被测系统本身按主仓库 README 的「快速开始」启动（推荐先 `seed_*` 初始化演示数据）。

```bash
# 通用：为每层建独立虚拟环境，避免依赖冲突
# 功能测试 —— 纯文档，无运行依赖，直接阅读报告与用例即可

# 接口自动化
cd onlineexam-api-autotest/onlineexam_api_autotest
pip install -r requirements.txt
pytest                                   # 需要被测服务先起在 127.0.0.1:8777

# UI 自动化
cd onlineexam-ui-autotest/onlineexam_ui_autotest
pip install -r requirements.txt
# 自备 chromedriver（tools/chromedriver.exe 不入库），pytest

# 性能测试
cd onlineexam-performance-testing/onlineexam_performance_testing
pip install -r requirements.txt
# 按 .run/README.md：刷新数据 → 起服务 → 三场景压测
```

---

## 环境与端口说明

**被测系统路径**：本仓库所有脚本通过 `OE_PROJECT` 环境变量定位被测系统根目录，默认 `D:/OnlineExam`（即被测系统在本机的目录）。跨机器运行前设置：

```bash
export OE_PROJECT=/path/to/OnlineExam      # Git Bash / Linux / macOS
set OE_PROJECT=D:\path\to\OnlineExam        # Windows cmd
```

> 各层 `docs/` 中的 `OnlineExam`（无盘符）指被测系统根目录，即上面 `OE_PROJECT` 指向的位置。

**端口分工**（与主仓库无冲突，各层互不干扰）：

| 用途 | 端口 | 归属 |
|---|---|---|
| 开发默认（`run_dev.bat`）+ 端到端冒烟（`smoke_test.py`） | 8000 | 主仓库 |
| 功能测试 / 接口自动化 | **8777** | fun / api |
| UI 自动化 | **8931** | ui |
| 性能压测（Locust） | **8024** | performance |

> UI 自动化需用系统 Python 3.11（含 selenium，项目 `.venv` 为 3.13 不含 selenium），详见 `onlineexam-ui-autotest/docs/04-环境搭建与元素定位.md`。

---

## 与主仓库的关系

- 主仓库 [`onlineexam-system`](https://github.com/Abigzy/onlineexam-system) 只含**被测系统**与 1200 条单元测试；
  **测试资产不在主仓库**，全部集中在本仓库。
- 四层测试分工（口径见各 `docs/`）：功能测试覆盖业务与页面交互、接口自动化覆盖 API 契约与权限边界、
  UI 自动化覆盖「点了按钮页面真的会变」、性能测试覆盖并发容量与瓶颈定位。
- 缺陷在四层之间的流转、根因分析、修复回归结论，以各层 `docs/*缺陷管理*.md` 与报告为准。

## License

[MIT](./LICENSE) © 2026 Abigzy
