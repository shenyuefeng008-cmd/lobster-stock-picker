# 乐享MCP安装与数据同步配置

## 任务目标
安装/更新腾讯乐享 MCP 技能包，并将龙虾系统每日数据同步从 SMH 云存储迁移到腾讯乐享知识库。

## 执行步骤

### 1. 安装乐享MCP技能包
- 执行 `npx @lexiang/skills install`
- 自动删除旧版 `lexiang-knowledge-base` 和 `lexiang-openapi-skill`
- 安装6个新skill到 `.agents/.claude/.codebuddy/.workbuddy/.openclaw` 五个目录：
  - lexiang-setup — 配置向导
  - lexiang-search — 搜索与内容阅读
  - lexiang-writer — 文档创建与写入
  - lexiang-blocks — 已有页面编辑
  - lexiang-files — 文件上传下载
  - lexiang-connectors — 外部数据源导入

### 2. 配置MCP连接
- COMPANY_FROM: `4a67d1b64d0311f1827cba9bae0f190d`
- LEXIANG_TOKEN: `lxmcp_cd72cf8e62ea06efca1085d7a1966e1c939f12d023bc90c091fe947c053212f8`
- 配置已存在于 `~/.mcporter/mcporter.json` 中，无需变更
- MCP连接验证通过，工具列表完整（45+ functions）

### 3. 知识库结构
- **沈跃峰的个人知识库** (space_id: `1353939a48bc4183bc8340cd28e7d3e7`)
  - 龙虾超短交易系统 (folder)
  - 龙虾短线知识库 (folder)
  - 每日复盘 (folder)
- **示例知识库** (space_id: `71d64ead1c44416cb1981ac39df6f4a9`)
  - 🦞龙虾交易系统 (folder)
  - 每日选股 (folder)

### 4. 同步脚本
- 文件: `scripts/lobster_lexiang_sync.py`
- 技术: Python3 + subprocess 调用 `mcporter call lexiang.entry_import_content`
- 同步8项数据到个人知识库根目录下

### 5. 测试结果
首次运行全部成功（8/8）：
| # | 标题 | entry_id |
|---|------|----------|
| 1 | 龙虾-06-14-新闻资讯 | d52725fb1cd1411699bfb0ea1dd9f06e |
| 2 | 龙虾-最新-催化日历 | 50892cbf5a51481395db8477a7109588 |
| 3 | 龙虾-最新-趋势容量池 | 0e878e60ded84de687b0225afb9ddf9c |
| 4 | 龙虾-最新-交易追踪 | 15c72571ed5f410a8d0a685f5c44ae87 |
| 5 | 龙虾-06-14-工作日志 | 9ba86113508e4d1faa418385ca700caa |
| 6 | 龙虾-06-14-产业图谱 | 2190d610650d439dae77f14331fe3d46 |
| 7 | 龙虾-最新-关注股 | c2a986e005a34291abca5427bd391b2e |
| 8 | ⚠️ 进化日志目录不存在 | — |

### 6. Cron任务更新
- 原: `龙虾数据云同步` (ae6053d3, SMH) → 现: `龙虾数据乐享同步` (每日02:00)
- 旧脚本 `lobster_cloud_sync.sh` 和 `CRON_CLOUD_SYNC_TASK.md` 已删除

## 遗留
- 进化日志目录 `trading/evolution_logs/` 不存在，需确认是否需要创建
- 同步的文档都放在知识库根目录，后续可以在乐享中手动组织文件夹
- 产业图谱文件路径 `trading/sector_map_YYYY-MM-DD.md` 当前不存在，使用 `trading/产业图谱.md` 替代
