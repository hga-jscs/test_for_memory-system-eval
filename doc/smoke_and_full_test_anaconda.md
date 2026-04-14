# Smoke Test 与全量测试（Anaconda 命令）

> 目标系统：`lightrag`、`hipporag`、`raptor`、`memgpt`

## 1) 创建与激活 Conda 环境

```bash
conda create -n mem-eval python=3.10 -y
conda activate mem-eval
pip install -U pip setuptools wheel
```

## 2) 安装通用依赖

```bash
# 仅示例：根据你们内部镜像可替换为 conda/pip 镜像源
pip install openai pydantic requests numpy scipy scikit-learn umap-learn faiss-cpu tiktoken
```

## 3) 启动外部服务（按需）

```bash
# LightRAG 服务（示例端口）
export LIGHTRAG_URL=http://127.0.0.1:9621

# Letta / MemGPT 服务（示例端口）
export LETTA_BASE_URL=http://127.0.0.1:8283
```

## 4) Smoke Test 命令

```bash
python smoke_test_lightrag.py
python smoke_test_hipporag.py
python smoke_test_raptor.py
python smoke_test_memgpt.py
```

## 5) 全量评测命令（R1/R2/R3）

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

## 6) 可视化/调试建议

```bash
# 输出完整日志，便于排查
python smoke_test_raptor.py 2>&1 | tee /tmp/smoke_raptor.log
python bench_r123.py --system hipporag --bench structmemeval 2>&1 | tee /tmp/full_hipporag_structmemeval.log
```
