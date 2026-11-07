# OnlineExam 性能测试

> 被测系统 `OnlineExam`（不改一行代码）。
> 关联测试：功能 `onlineexam-fun-test`、接口 `onlineexam-api-autotest`、UI `onlineexam-ui-autotest`。

## 目录

```
docs/                                  文档（不在核心工程内，纯阅读用）
  00-历史基线-模块11性能测试报告.md   上一轮（2026-10-27，20 并发、runserver）的报告存档
  01-性能测试方案.md                  选型（Locust vs JMeter）+ 8 阶段流程
  02-测试计划与环境搭建.md             环境口径、数据准备、阈值、用例矩阵、续跑命令
  03-场景与脚本设计.md                 三场景建模、断言、指标采集、踩过的坑
  04-执行记录.md                      每轮原始数据与异常记录
  05-性能测试报告.md                  结论 / 曲线 / 瓶颈 / 建议

onlineexam_performance_testing/        核心工程：代码 + 运行产物，命令行都在这里执行
  .run/                                PyCharm 运行配置（刷新数据 / 起服务 / 三场景压测 / WebUI）
  requirements.txt                     依赖清单（复用被测项目 venv，版本按实测组合固定）
  perf_settings.py                    压测用 Django 配置（DEBUG=False、CONN_MAX_AGE 可调）
  locustfile.py                       三场景压测脚本（派生态）
  scripts/
    serve.py                          起服务（runserver / waitress / 是否复用连接）
    run_with_server.py                起服务 → 跑一轮 → 关服务（推荐入口）
    seed.py                           准备数据（班级关系、次数上限、时间窗、重签 token）
    make_grade_sample.py              造「一个班 50 份待批卷」并冻结判分名单
    run_case.py                       跑单个用例（Locust + 资源采样 + 结果落盘）
    run_suite.py                      跑一轮（支持 --resume / --only / --label-suffix）
    progress.py                       看进度（done / pending / skip）
    summarize.py                      把 results.csv 汇总成 Markdown
  report/                             原始产物：*_stats.csv / *_stats_history.csv / *_failures.csv / *.html
```

`scripts/` 里所有脚本的工程根是「自身所在目录的上一级」，所以**从任何工作目录执行都能跑**，
不依赖 `cd` 到哪个位置。下面示例统一在核心工程目录下执行。

## 一句话结论（详见 05 报告）

- runserver 与 waitress 表现几乎一样，**换 WSGI 服务器不是瓶颈所在**；
- 真正的瓶颈是 **每个请求都重开数据库连接**（MySQL 建连 52-69 ms vs 复用查询 0.1 ms），
  导致 50 并发卡在 ~12.8 RPS；
- 开启 `CONN_MAX_AGE=60` 后 50 并发 **45.2 RPS / P95 840 ms**，达到验收线。

## 中断后怎么继续

```bash
cd /d/onlineexam-performance-testing/onlineexam_performance_testing

# 1) 看跑到哪了
OnlineExam/.venv/Scripts/python.exe scripts/progress.py

# 2) 刷新数据状态：考试时间窗 + 重签 access token（simplejwt 只有 60 分钟）
OnlineExam/.venv/Scripts/python.exe scripts/seed.py --refresh-only

# 3) 续跑（自动跳过已完成的用例；起停服务一条命令搞定）
OnlineExam/.venv/Scripts/python.exe scripts/run_with_server.py \
    --mode waitress --threads 8 --conn-max-age 60 \
    --suite waitress-conn60 --resume
```

## 状态

| 轮次 | 状态 |
|---|---|
| runserver 轮（9 用例） | 完成 |
| waitress 轮（9 用例） | 完成 |
| 调优轮（连接复用，阶梯 + 4 场景 + 基线） | 完成 |
| 稳定性 soak（50 并发 15 分钟） | 完成：35178 请求 0 失败，P95 717→695 ms，RSS +1.2% |
| 报告（05） | 完成 |

待办（不影响本次结论）：JMeter 交叉验证一个接口；Linux + gunicorn 多进程容量；真实 AI 批改耗时。
