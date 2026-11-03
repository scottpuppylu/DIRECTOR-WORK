# CHANGELOG

版本號在 `VERSION`。專案導入時把版本號和 commit 一起記進 `DIRECTOR_OPERATING_RULES.md`（`BOOTSTRAP` 第 1 步），升級時讀這份，照「遷移」做。

- **MAJOR**：已經通過的舊檔案或舊設定會變成不通過，例如工具檢查的格式改了、`director_work.json` 的 `schema_version` 升級。一定附遷移步驟。
- **MINOR**：新增規則、文件、工具或選項，舊檔案照樣通過。
- **PATCH**：修正文字、修 bug，規則不變。

## 0.9.0 — 2026-11-04

第一個版本號，涵蓋到這一版為止的全部內容。還不算定案：`v1.0.0` 要等完整開發循環實測過。

- 新增 `docs/11_claude_desktop.md`：在 Claude Desktop 上開 worker、傳訊息、讀額度和上下文視窗用哪個工具。不列入每輪必讀。
- `BOOTSTRAP` 第 7.5 步：Desktop 上用 `get_usage` 確認上下文視窗。
- `gate_check.py` 加 `--warn`（只警告、exit 0）和 `--since YYYY-MM-DD`（跳過較早的檔案）。不帶這兩個參數時行為不變。
- 固定用詞集中到 `tools/vocabulary.json`；`selftest.py` 檢查 `docs/02` 和範本的寫法跟它一致。
- `selftest.py` 檢查 README 標「每輪必讀」的文件合計不超過 13,428 bytes。
- `director_work.json` 加 `schema_version`（目前 1）。沒有這個欄位的設定檔視為 1；版本不認得時 `setup_project_settings.py` 會拒絕執行。
- 工單規則：worker 不改驗收條件和規格，有問題回報 `BLOCKED`，由總監裁決。
- GitHub Actions 在 Windows 上用 Python 3.9 和 3.12 跑 `selftest.py`。

遷移：不用改任何舊檔案。已建置的專案可以把 `"schema_version": 1` 加進 `director_work.json`，不加也一樣。把 `tools/` 整個重新複製到 `DIRECTOR/tools/`，`vocabulary.json` 要一起帶過去，否則 `gate_check.py` 會無法執行。
