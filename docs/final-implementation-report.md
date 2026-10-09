# HeatOps v2 — 最终实现报告

## A. 已实现功能与范围

已完成多队伍 CP-SAT 调度、可选行程约束、独立可行性检查、可配置合成场景、四策略 benchmark、天气接口、Streamlit 多队伍界面、CLI、CSV/JSON 导出及文档。原始 Phoenix 演示与温度快照保留。
多队伍使用 job/worker/start 决策变量和每个 job/worker 的可选区间；每个队伍独立 NoOverlap。行程采用 Circuit，只约束相邻任务与起点到首任务。延迟预算采用优先级加权分钟。所有比较使用同一组约束。
本次未操作部署设置；本地 Streamlit AppTest 与 HTTP 健康检查通过。恢复工作时发现核心 PR #3 已在仓库侧合并，现以独立补充 PR 提交评估结果与文档。合并后的公开部署状态未独立确认。Phase 9 的 FastAPI、数据库和 Docker 持久化未做，属于原计划可选范围。

## B. 改动文件

| 路径 | 用途 |
|---|---|
| `src/heatops/optimization/multi_crew.py` | 多队伍指派、求解状态/界限/耗时、延迟预算、行程顺序 |
| `src/heatops/optimization/travel.py` | Haversine 距离、行程估计和有向时间矩阵 |
| `src/heatops/optimization/scheduler.py` | 旧接口保留，并支持新增不可用时段 |
| `src/heatops/domain/models.py`, `loaders.py` | 队伍不可用时段、兼容读取 |
| `src/heatops/evaluation/fleet.py` | 独立检查、配对比较、利用率/行程指标 |
| `src/heatops/benchmark/` | 场景、可行性见证、并行评估、统计与图表 |
| `src/heatops/integrations/open_meteo.py`, `weather_provider.py` | 来源标注、时区转换、缓存、明确回退 |
| `app.py`, `src/heatops/ui/fleet.py`, `src/heatops/cli.py` | 多队伍界面、上传、导出与命令行 |
| `scripts/generate_scenarios.py`, `run_benchmarks.py`, `profile_scheduler.py` | 可复现实验入口 |
| `tests/test_multi_crew.py`, `test_scenario_generator.py`, `test_benchmark_runner.py`, `test_open_meteo.py`, `test_fleet_ui_cli.py` | 算法、数据、集成与界面测试 |
| `benchmarks/final.json`, `reports/` | 固定清单、原始证据、图表、环境信息 |
| `README.md`, `docs/`, `.github/workflows/ci.yml`, `pyproject.toml`, `.gitignore`, `.gitattributes` | 使用说明、架构、CI、依赖和归档规则 |

## C. 验证

- 原有 113 个测试通过；最终共 162 个测试通过。Python 3.12 的并行测试出现两条 fork 弃用警告，没有测试失败；未来可切换 spawn。
- `python -m ruff check .`、`python -m ruff format --check .`、`python -m compileall -q src app.py scripts tests` 均通过。
- `python -m pytest -q`，旧 CLI 与新 CLI smoke test 通过。GitHub Actions run 37857898141 的 Python 3.11/3.12 两项均成功。
- 原 Phoenix：40.382715625 → 39.182749375，改善 2.971484784%；原始任务延迟 4.5 → 10.25 小时。快照 SHA-256：`e6080bde546f89b238b43a85826e51d11dc6f03bd3694835e4281dc0f134eab2`。
- Open-Meteo 真实历史请求返回 25 个小时记录；测试中的 HTTP 故障、缺失值、时区、缓存、DST 重复小时和回退使用 mock。未使用未授权的 FortyGuard 凭据。

## D. 实测 benchmark

固定清单共 **165 个场景、660 个策略记录**。有效排程 **654/660**。全部返回的可行/最优排程独立检查均为零违规。状态：`{'OPTIMAL': 582, 'FEASIBLE': 72, 'UNKNOWN': 5, 'NOT_RUN': 1}`。UNKNOWN 表示时限内无 incumbent，不代表已证明无解；NOT_RUN 表示缺少预算基准导致策略未运行。
主实验：10 jobs / 2 crews，五种温度族各 30 个固定种子。扩展：5/1、25/5、50/5、100/10 各 3 个种子。行程：5 jobs / 2 crews、3 个种子。主实验每策略 5 秒，扩展与行程 30 秒。四场景并行，各求解器单线程。

| 主实验策略 | 有定义的改善样本数 / 150 | 平均改善 | 中位改善 | 状态 |
|---|---:|---:|---:|---|
| heat_first | 117/150 | 8.4687% | 3.6722% | {'OPTIMAL': 136, 'FEASIBLE': 14} |
| balanced | 116/150 | 3.6999% | 0.2850% | {'OPTIMAL': 141, 'FEASIBLE': 8, 'UNKNOWN': 1} |
| delay_budget | 115/150 | 4.3766% | 1.5961% | {'OPTIMAL': 134, 'FEASIBLE': 13, 'UNKNOWN': 2, 'NOT_RUN': 1} |

上述平均值只包含基准与该策略均成功且基准 Heat Load > 0 的配对。零值基准、超时、未运行均在 CSV/summary 中保留，没有当成 0% 或删除失败。分组 SD、bootstrap 95% CI、最差值、p95 耗时见 `benchmark_summary.json`。

| Jobs / crews | 策略记录数 | 有效排程数 | 全部尝试的中位耗时 (s) | 状态 |
|---|---:|---:|---:|---|
| 5/1 | 12 | 12 | 0.035 | {'OPTIMAL': 12} |
| 25/5 | 12 | 12 | 30.065 | {'FEASIBLE': 12} |
| 50/5 | 12 | 12 | 30.131 | {'FEASIBLE': 12} |
| 100/10 | 12 | 11 | 30.329 | {'FEASIBLE': 11, 'UNKNOWN': 1} |

100-job 已返回解的端到端中位耗时为 30.340 秒，均不能当作已证明最优；界限/相对 gap 见每行原始结果。模型构建和求解计时分开记录，30 秒限制不包含模型构建。

### 延迟与行程代价
- heat_first：可比较排程额外优先级加权延迟平均 3.488 小时，最大 13.750 小时。
- balanced：可比较排程额外优先级加权延迟平均 0.120 小时，最大 2.000 小时。
- delay_budget：可比较排程额外优先级加权延迟平均 0.522 小时，最大 1.000 小时。
- 行程实验有效排程 12/12；估计距离范围 13.371–23.894 km。不是测得的道路距离，也不包含返回起点。

开发集的五组配对构建时间试验：不缓存中位 0.679558 秒，缓存后 0.510717 秒，下降 24.85%。只可描述为模型构建改善，不能描述为端到端求解提速。

### 来源与恢复记录
全部新 benchmark 温度均为 synthetic，与原 FortyGuard 快照分开。最初串行试跑的已完成记录保留在 `reports/serial-partial/`，未并入最终统计。最终四进程运行在会话暂停时保留 161 个场景，随后以相同源码 hash、Python、OR-Tools 和 NumPy 恢复最后 4 个场景；恢复环境单独存档。机器/共享负载与时间截断会影响耗时和未证明最优的 incumbent。
证据：`reports/benchmark_environment.json`、`benchmark_resume_environment.json`、`benchmark_results.csv`、`benchmark_summary.json`、`benchmark_details.jsonl.gz`。

```bash
python scripts/run_benchmarks.py --manifest benchmarks/final.json
python scripts/run_benchmarks.py --manifest benchmarks/final.json --resume
python scripts/profile_scheduler.py
```

## E. GitHub

核心分支：`feature/heatops-v2`，PR https://github.com/MichelleHan7/HeatOps/pull/3 已于 2026-10-09 01:57 UTC 在仓库侧合并，合并提交 `9a229675478fd4177db36c0c1d823b5beb3ced90`。恢复后已确认 main 的文件树与已测试核心实现一致。

补充交付分支：`feature/heatops-v2-results`。草稿 PR：https://github.com/MichelleHan7/HeatOps/pull/4 。结果与文档提交：`b4f7e48972db75b74d729f9b279f9548d242d9ee`。本次只创建补充 PR，不直接写入 main。

实现提交：
- 6bbddba docs: audit legacy scheduler and preserve Phoenix baseline
- 092bbaf feat: add multi-crew CP-SAT scheduling and travel validation
- f51184e feat: add reproducible synthetic scenarios and registered benchmark suite
- 9f29f25 feat: add provenance-aware weather providers and offline fallback
- 9ea6e9c feat: integrate fleet dashboard, custom inputs, exports and CLI
- 5f47a30 feat: expose generator settings and tighten availability and CLI validation
- 908bc63 perf: run fixed benchmark instances concurrently with archived serial evidence

最终文档和结果另附一个提交；最新 SHA 见该 PR。

## F. 简历建议

1. Built a Python/OR-Tools multi-crew scheduler supporting 100-job, 10-crew synthetic workloads under skill, shift and deadline constraints, with independently validated outputs and a separate travel-aware mode.
2. Evaluated four scheduling policies across 165 seeded synthetic scenarios; achieved 8.47% mean modeled Heat Load reduction on 117 valid, nonzero-baseline heat-first pairs, with explicit timeout and delay reporting.
3. Integrated provenance-aware weather providers, offline fallback, Streamlit/CLI workflows and CSV/JSON exports, backed by 162 automated tests and Python 3.11/3.12 CI.

完整证据与措辞限制见 `docs/resume-metrics.md`。不把 synthetic 改善写成生产环境收益。

## G. 已知限制与后续

- 部分时限运行无解或仅有可行 incumbent；大实例的最优性 gap 仍大。下一步应改进 lower bound、候选压缩与搜索策略，再在同一清单上比较。
- 行程模式默认最多 25 jobs；路径是地理近似，未优化行驶距离、未要求返回 depot。
- 仅确定性的同一天排程；无跨午夜、天气不确定性、安全休息政策、健康效果或生产认证/数据库。
- Open-Meteo 历史数据为再分析模型；免费服务用途与配额需遵循提供方条款。
- 本次未操作 Streamlit Community Cloud；核心合并后的线上状态未独立验证。补充结果分支等待审查。
- 可选 backend 阶段延期，不影响当前调度、评估和展示路径。
