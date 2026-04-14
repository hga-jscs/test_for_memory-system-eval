# LightRAG / HippoRAG / RAPTOR 全量测试操作指南（顺序版）

> 你说“还是一个一个跑”，下面给的是**完整可执行手册**（含可视化调试输出）。

---

## 0. 目标与范围

- 系统：`lightrag`、`hipporag`、`raptor`
- benchmark：`memory_probe`、`structmemeval`、`amemgym`
- 推理模式：`r1,r2,r3`
- 执行方式：**顺序执行（一个系统跑完再跑下一个）**

---

## 1. 一条命令顺序跑完（推荐）

```bash
bash run_full_benchmarks_step_by_step.sh
```

默认配置：
- `BENCH=all`
- `R_MODES=r1,r2,r3`
- 日志目录自动生成：`logs/full_step_by_step_<时间戳>/`

可视化调试输出特性：
- 终端实时输出为 `[时间][系统] 日志内容`，便于观察卡在哪一步
- 每个系统都有独立日志文件：
  - `logs/full_step_by_step_<ts>/lightrag.log`
  - `logs/full_step_by_step_<ts>/hipporag.log`
  - `logs/full_step_by_step_<ts>/raptor.log`

---

## 2. 手动一个一个跑（最透明）

> 如果你希望“我明确控制每个阶段”，用下面 3 组命令。

### 2.1 跑 LightRAG

```bash
PYTHONUNBUFFERED=1 python3 bench_r123.py --system lightrag --bench all --r r1,r2,r3 2>&1 | tee logs/manual_lightrag_full.log
```

### 2.2 跑 HippoRAG

```bash
PYTHONUNBUFFERED=1 python3 bench_r123.py --system hipporag --bench all --r r1,r2,r3 2>&1 | tee logs/manual_hipporag_full.log
```

### 2.3 跑 RAPTOR

```bash
PYTHONUNBUFFERED=1 python3 bench_r123.py --system raptor --bench all --r r1,r2,r3 2>&1 | tee logs/manual_raptor_full.log
```

---

## 3. 常用变体

### 3.1 只跑某个 benchmark

例如只跑 StructMemEval：

```bash
BENCH=structmemeval bash run_full_benchmarks_step_by_step.sh
```

### 3.2 只跑部分 R 模式

```bash
R_MODES=r1,r2 bash run_full_benchmarks_step_by_step.sh
```

### 3.3 指定日志目录

```bash
LOG_DIR=logs/debug_run_20260414 bash run_full_benchmarks_step_by_step.sh
```

---

## 4. 失败排查顺序（建议按这个来）

1. 先看当前系统独立日志末尾（`tail -n 100 logs/.../<system>.log`）
2. 确认 `bench_r123.py` 能单独跑一个最小任务（比如 `--bench structmemeval --r r1`）
3. 再恢复到 `--bench all --r r1,r2,r3`

---

## 5. MemGPT 说明（补充）

本仓库中 `memgpt_bench_src.py` 已增强兼容，但当前这份全量顺序脚本只覆盖你指定的 3 个系统（lightrag/hipporag/raptor）。
如果要单测 MemGPT，请单独运行：

```bash
python3 smoke_test_memgpt.py --top-k 5
```

如报连接错误，优先检查：
- `LETTA_BASE_URL`
- `LETTA_API_KEY`
- Letta 服务是否已启动并暴露 `/v1/agents` 接口
