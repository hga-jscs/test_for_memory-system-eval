# LightRAG / HippoRAG / RAPTOR / MemGPT 分系统评测操作指南

> 目标：把 4 个系统在 3 个 benchmark（`memory_probe` / `structmemeval` / `amemgym`）上的评测脚本**分开管理**，并提供统一、可视化、可恢复的执行方式。

---

## 1. 新增脚本总览（已分开）

- `run_lightrag_full.sh`
- `run_hipporag_full.sh`
- `run_raptor_full.sh`
- `run_memgpt_full.sh`

每个脚本都会按固定顺序依次执行：
1. `memory_probe`
2. `structmemeval`
3. `amemgym`

并在运行时自动输出：
- `[START]/[DONE]` 阶段标记
- `[HH:MM:SS][system/bench]` 的逐行可视化调试日志
- 每个 benchmark 单独日志文件（便于定位问题）

---

## 2. 快速开始

### 2.1 LightRAG 全量

```bash
bash run_lightrag_full.sh
```

### 2.2 HippoRAG 全量

```bash
bash run_hipporag_full.sh
```

### 2.3 RAPTOR 全量

```bash
bash run_raptor_full.sh
```

### 2.4 MemGPT 全量

```bash
bash run_memgpt_full.sh
```

---

## 3. 调试与可视化输出（重点）

每个脚本默认日志目录格式如下：
- `logs/lightrag_full_<时间戳>/`
- `logs/hipporag_full_<时间戳>/`
- `logs/raptor_full_<时间戳>/`
- `logs/memgpt_full_<时间戳>/`

目录里固定会生成：
- `memory_probe.log`
- `structmemeval.log`
- `amemgym.log`

建议调试时开两个终端：

```bash
# 终端 A：启动跑分
bash run_memgpt_full.sh

# 终端 B：实时看 AMemGym 阶段
TAIL_DIR=$(ls -dt logs/memgpt_full_* | head -n 1)
tail -f "$TAIL_DIR/amemgym.log"
```

---

## 4. 环境变量参数

4 个脚本支持一致参数：

- `R_MODES`：默认 `r1,r2,r3`
- `LOG_DIR`：自定义日志目录
- `START`：AMemGym 起始用户索引（默认 `0`）
- `END`：AMemGym 结束用户索引（默认空，表示到末尾）

示例：只跑 `r1,r2` 并指定日志目录。

```bash
R_MODES=r1,r2 LOG_DIR=logs/debug_memgpt_r12 bash run_memgpt_full.sh
```

示例：只跑 AMemGym 子区间（前 20 用户中的 [10,20)）。

```bash
START=10 END=20 bash run_hipporag_full.sh
```

---

## 5. 建议执行顺序

如果你的目标是稳定定位问题，建议按以下顺序逐个系统跑：

1. `bash run_lightrag_full.sh`
2. `bash run_hipporag_full.sh`
3. `bash run_raptor_full.sh`
4. `bash run_memgpt_full.sh`

这样可以把故障范围限定在“系统差异”而不是“并发干扰”。

---

## 6. 常见问题

### Q1: 如何确认卡在哪个 benchmark？
看终端中的 `[START] system=... bench=...` 和 `[DONE] ... bench=...` 标记；
也可以直接查看该系统日志目录下对应 `*.log` 文件末尾。

### Q2: 结果文件在哪里？
由 `bench_r123.py` 统一输出在仓库根目录，例如：
- `results_memory_probe_<system>_r1.json`
- `results_structmemeval_<system>_r2.json`
- `results_amemgym_<system>_r3.json`

### Q3: 中断后如何恢复？
直接重跑同一个脚本。`bench_r123.py` 在多个 benchmark 中都支持阶段性保存与续跑（按结果文件自动 resume）。

---

## 7. 最小正确性检查（跑前建议）

```bash
python3 bench_r123.py --system lightrag --bench memory_probe --r r1
python3 bench_r123.py --system hipporag --bench structmemeval --r r1
python3 bench_r123.py --system raptor --bench amemgym --r r1 --start 0 --end 1
python3 bench_r123.py --system memgpt --bench memory_probe --r r1
```

如果以上都能通，再执行对应的 `run_*_full.sh` 做完整评测。
