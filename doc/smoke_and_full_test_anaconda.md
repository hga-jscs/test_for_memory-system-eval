# Smoke Test 与全量测试（Anaconda 命令）

> 目标系统：`lightrag`、`hipporag`、`raptor`、`memgpt`
>
> 本文档已针对 **Conda/Anaconda 常见问题**（依赖缺失、外部服务未启动、路径不完整）做了可操作修正。

---

## 1) 创建与激活 Conda 环境

```bash
conda create -n mem-eval python=3.10 -y
conda activate mem-eval
python -m pip install -U pip setuptools wheel
```

---

## 2) 安装通用依赖（先保证四个 smoke test 可运行）

```bash
# 这些是当前仓库 smoke test 最小必需依赖
pip install requests pyyaml openai numpy scipy scikit-learn umap-learn faiss-cpu tiktoken
```

如果你在企业内网，请改为你们自己的镜像源。

---

## 3) （可选）配置外部服务地址

如果你要跑“真实后端”而不是本地 fallback，请先启动服务并配置地址：

```bash
# LightRAG 服务
export LIGHTRAG_URL=http://127.0.0.1:9621

# Letta / MemGPT 服务
export LETTA_BASE_URL=http://127.0.0.1:8283
```

---

## 4) 一键执行四个 smoke test（推荐）

仓库根目录提供了增强脚本（会自动分系统打日志，便于可视化排查）：

```bash
# 标准模式：优先使用真实服务，服务不可用会自动降级到本地 fallback
bash run_smoke_four_anaconda.sh

# 强制本地 fallback（无外部服务时建议）
FORCE_LOCAL=1 bash run_smoke_four_anaconda.sh
```

日志会写入：`logs/smoke_时间戳/*.log`

---

## 5) 单独执行四个 smoke test

```bash
python smoke_test_lightrag.py
python smoke_test_hipporag.py
python smoke_test_raptor.py
python smoke_test_memgpt.py
```

---

## 6) 全量评测命令（R1/R2/R3）

```bash
# LightRAG 全量（memory_probe + structmemeval + amemgym）
python bench_r123.py --system lightrag --bench all

# HippoRAG 全量
python bench_r123.py --system hipporag --bench all

# RAPTOR 全量
python bench_r123.py --system raptor --bench all

# MemGPT 全量
python bench_r123.py --system memgpt --bench all
```

---

## 7) 可视化/调试输出建议（重点）

```bash
# 1) 保留完整 stdout/stderr
python smoke_test_raptor.py 2>&1 | tee /tmp/smoke_raptor.log

# 2) 单项全量评测日志
python bench_r123.py --system hipporag --bench structmemeval 2>&1 | tee /tmp/full_hipporag_structmemeval.log

# 3) 按关键字观察“是否走了 fallback”
rg "fallback|ERROR|FAIL|traceback|RESULT" logs/smoke_*/ -n
```

---

## 8) 常见问题排查

### Q1: `No module named yaml` / `No module named requests`

先执行第 2 节依赖安装。

### Q2: 服务端口没起来（`Connection refused`）

- LightRAG / Letta 未启动时，会自动降级到本地 fallback，smoke test 仍可跑通。
- 若要测试真实服务，请先启动对应服务，再重跑。

### Q3: 找不到 `hipporag` / `raptor` 外部仓库

- 当前版本会自动降级到本地 fallback。
- 若要真实评测效果，请补齐外部 repo 路径并安装其依赖。
