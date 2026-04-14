# 全量测试操作指南（标准 Anaconda + 完全分开执行）

> 按你的要求：
> 1) 使用标准 Anaconda 指令；
> 2) 三个系统完全分开跑，不并行、不串联。

---

## 1. 标准 Anaconda 准备

```bash
# 初始化（首次）
conda create -n mem-eval python=3.10 -y

# 每次新终端先激活
conda activate mem-eval
```

> 如果你在 shell 中还不能直接 `conda activate`，先执行：

```bash
source ~/anaconda3/etc/profile.d/conda.sh
conda activate mem-eval
```

---

## 2. 完全分开的三条执行路径

### A) 只跑 LightRAG（独立）

```bash
bash run_lightrag_full_anaconda.sh
```

### B) 只跑 HippoRAG（独立）

```bash
bash run_hipporag_full_anaconda.sh
```

### C) 只跑 RAPTOR（独立）

```bash
bash run_raptor_full_anaconda.sh
```

> 这三条命令互不依赖。你想跑哪个就只跑哪个。

---

## 3. 每个独立脚本的默认行为

- 默认 benchmark：`all`
- 默认 R 模式：`r1,r2,r3`
- 默认都会实时打印可视化前缀日志：`[HH:MM:SS][system] ...`
- 默认都会写入系统独立日志文件（`logs/<system>_full_<ts>/<system>.log`）

---

## 4. 常用参数覆盖（单系统）

以 HippoRAG 为例：

```bash
# 只跑 StructMemEval
BENCH=structmemeval bash run_hipporag_full_anaconda.sh

# 只跑 r1,r2
R_MODES=r1,r2 bash run_hipporag_full_anaconda.sh

# 指定环境名
CONDA_ENV=my-mem-env bash run_hipporag_full_anaconda.sh

# 指定日志目录
LOG_DIR=logs/hipporag_debug_20260414 bash run_hipporag_full_anaconda.sh
```

---

## 5. 故障排查（单系统内）

1. 先看对应日志末尾：
   ```bash
   tail -n 120 logs/hipporag_full_*/hipporag.log
   ```
2. 缩小范围：先改成 `BENCH=structmemeval R_MODES=r1`
3. 确认单系统跑通后，再跑完整 `all + r1,r2,r3`

---

## 6. 兼容说明

旧的总控脚本 `run_parallel_full_benchmarks.sh` 和 `run_full_benchmarks_step_by_step.sh` 已废弃，只保留提示信息，防止误用“串起来”的旧流程。
