# IMA Sync Root Cause Fix

**Date:** 2026-05-31 23:35  
**Objective:** Fix recurring IMA sync failures

## Root Cause
1. `set -e` in both `ima_sync.sh` and `daily_ima_sync.sh` kills scripts on any non-zero return
2. All CRON_MD files used `2>/dev/null` or no stderr redirect → errors silently swallowed
3. No centralized error logging

## Changes

### `scripts/ima_sync.sh` (v2.1)
- Removed `set -e`
- Added `log_error()` / `log_info()` → writes to `/tmp/ima-errors.log`
- All failure points now log errors

### `scripts/daily_ima_sync.sh`
- `set -e` → `set +e`

### 9 CRON_MD files
- Changed all `2>/dev/null` → `2>>/tmp/ima-errors.log`
- Added `2>>/tmp/ima-errors.log` to calls that had no redirect

### Verification
```bash
tail -50 /tmp/ima-errors.log  # check all IMA errors
```