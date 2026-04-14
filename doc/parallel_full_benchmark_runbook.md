# 兼容入口说明（冲突已解决）

> 该文件对应历史路径 `doc/parallel_full_benchmark_runbook.md`，保留用于兼容旧分支和旧链接。  
> 当前策略：**不并行、不串联**，始终单系统执行。

## 推荐文档

完整指南请看：

- `doc/full_benchmark_runbook_anaconda.md`

## 兼容脚本用法（单系统）

```bash
# LightRAG
bash run_full_benchmarks_step_by_step.sh --system lightrag

# HippoRAG
bash run_full_benchmarks_step_by_step.sh --system hipporag

# RAPTOR
bash run_full_benchmarks_step_by_step.sh --system raptor
```

## 历史脚本名兼容

```bash
# 历史脚本名仍可用，但会自动转发到单系统入口
bash run_parallel_full_benchmarks.sh --system lightrag
```

## 设计原则

- 一次只跑一个系统，降低互相干扰与资源竞争。
- 保留每系统可视化日志输出（由 `run_*_full_anaconda.sh` 实现）。
