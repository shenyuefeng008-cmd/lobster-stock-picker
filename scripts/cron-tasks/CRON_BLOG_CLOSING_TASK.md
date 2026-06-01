# 龙虾博客收盘文章 — cron 任务指令

> **频率**：每日 16:00（工作日）
> **超时**：120秒
> **核心**：调用 blog_auto_writer.py 生成收盘博客文章，更新 index.html

---

## 步骤1：交易日判断

```bash
python3 -c "
import datetime, sys
HOLIDAYS = {'2026-01-01','2026-01-02','2026-01-03','2026-01-26','2026-01-27','2026-01-28','2026-01-29','2026-01-30','2026-01-31','2026-02-01','2026-02-02','2026-02-03','2026-02-04','2026-04-04','2026-04-05','2026-04-06','2026-05-01','2026-05-02','2026-05-03','2026-05-04','2026-05-05','2026-06-19','2026-06-20','2026-06-21','2026-09-25','2026-09-26','2026-09-27','2026-10-01','2026-10-02','2026-10-03','2026-10-04','2026-10-05','2026-10-06','2026-10-07'}
WORKDAYS = {'2026-01-25','2026-02-08','2026-04-26','2026-09-28','2026-10-10'}
d = datetime.date.today()
s = d.isoformat()
if s in HOLIDAYS or (d.weekday() >= 5 and s not in WORKDAYS):
    print('⚠️ 非交易日，跳过收盘博客')
    sys.exit(0)
else:
    print(f'✅ 交易日 {s}，生成收盘博客')
"
```

## 步骤2：运行博客生成脚本

```bash
cd /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5
python3 scripts/blog_auto_writer.py closing
```

## 步骤3：验证输出

```bash
ls -la /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/blog/ | tail -5
```

## 步骤4：IMA同步（可选）

```bash
bash /Users/yuefengshen/.qclaw/workspace-1gwpiwf3hr163jz5/scripts/ima_sync.sh 2>>/tmp/ima-errors.log || echo "IMA同步跳过(查看: tail /tmp/ima-errors.log)"
```

---

**版本**：v1.1
**更新**：2026-05-28

---

## ⚠️ 强制回复指令（必须执行）

任务完成后，**必须**向用户回复本次执行结果摘要，禁止回复NO_REPLY。
回复内容至少包含：文章标题、生成状态、推送状态。
