# PyCharm 运行配置

工程根目录（PyCharm 里打开这个文件夹）：`D:\onlineexam-performance-testing\onlineexam_performance_testing`

`.run/` 下的配置会被 PyCharm 自动识别，右上角下拉框直接选：

| 配置 | 作用 |
|---|---|
| `1 刷新数据（时间窗+token）` | 跑 `seed.py --refresh-only`：刷新考试时间窗 + 重签 access token |
| `2 起服务（waitress:8024）` | 起压测服务（`DEBUG=False`、压测库、连接复用 60s、AI mock） |
| `3 压测·交卷 50 并发（验收线）` | `ExamSubmitUser`，50 并发瞬时起步，90 秒 |
| `4 压测·开考读峰 50 并发` | `ExamStartBurstUser`，50 并发瞬时拉卷，90 秒 |
| `5 压测·教师判分 10 并发` | `ExamGradingUser`，10 并发，60 秒（读冻结的 50 份名单） |
| `6 Locust WebUI（手动调参看曲线）` | 不开 headless，浏览器打开 http://localhost:8089 手动填并发/勾标签 |

## 使用顺序

1. 跑「1 刷新数据」——**每次开工都要跑**：access token 只有 60 分钟，时间窗也会过期。
2. 跑「2 起服务」——**保持它运行**，控制台出现 `[serve] 已监听 8024` 才算好。
3. 跑「3/4/5」中任意一个压测配置。
4. 想看曲线就用「6 WebUI」，在里面填 Number of users、选 user class 再 Start。

## 几点说明

- 配置里用的是**绝对路径**（解释器与工作目录），所以即使你把 `.run` 目录复制到上一级再打开，也能照常运行。
  移动工程目录后需要在 PyCharm 里改一下 Working directory。
- 压测配置指定的是**用户类名**（`ExamSubmitUser` 等），不是 `--tags submit`。
  `--tags` 也能跑，但 Locust 会给被排除的类报 `No tasks defined on ...` 的 ERROR，看着像出错。
- 如果所有请求都失败、延迟还显示成 ~2000ms，先确认「2 起服务」还在跑：Locust 不会提示“连不上”。
- 手动跑只有终端输出，不落 csv。要留档用 `scripts/run_case.py --label xxx ...`。
