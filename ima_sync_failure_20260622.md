# IMA同步失败记录 2026-06-22

## 目标
每交易日16:00收盘后将当日产出同步到IMA知识库「ai自动选股」

## 执行结果
- 时间: 2026-06-22 16:02
- 判定: 交易日，继续执行
- 结果: **全部失败** — 6个文件均因「无法获取IMA凭证」上传失败

## 失败文件清单
| 文件 | 说明 | 备份路径 |
|------|------|----------|
| trading/news/2026-06-22.md | 龙虾新闻 | ~/.qclaw/ima_backup/20260622_160220_2026-06-22.md |
| trading/BUG_LOG.md | BUG日志 | ~/.qclaw/ima_backup/20260622_160220_BUG_LOG.md |
| trading/模拟持仓.json | 模拟持仓 | ~/.qclaw/ima_backup/20260622_160220_模拟持仓.json |
| trading/催化剂数据库.json | 催化剂数据库 | ~/.qclaw/ima_backup/20260622_160220_催化剂数据库.json |
| trading/产业逻辑框架.md | 产业逻辑框架 | ~/.qclaw/ima_backup/20260622_160221_产业逻辑框架.md |
| lobster_knowledge_graph.html | 产业知识图谱 | ~/.qclaw/ima_backup/20260622_160221_lobster_knowledge_graph.html |

## 根因
IMA凭证获取失败，可能原因：登录过期、Cookie失效、网络问题

## 后续
用户需检查IMA登录状态后手动重跑同步脚本
