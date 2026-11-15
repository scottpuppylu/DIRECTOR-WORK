# CPU 重現（送 TEST REQUEST 之前，第 0 級；2.3.0）

用 CPU、離線、不佔共用 GPU／裝置的方式先重現或排除問題。每一項都要寫出實際跑的指令和結果（`ran_line.py`），沒有跑的寫 `NOT_RUN <原因>`。

## 1. 編譯的是哪些檔（F4）

- 關掉建置工具的預設來源 glob，只列這次要測的檔案。例：SDK 式 C# 專案 `<EnableDefaultCompileItems>false</EnableDefaultCompileItems>`，再用 `<Compile Include="..."/>` 逐一列出；其他建置系統用對應的「不自動收檔」設定。
- 預設 glob 會把資料夾裡其他版本、備份、草稿檔一起編進去，跑出來的不是你以為的程式。
- 跑之前印出實際執行的組件／執行檔路徑和雜湊：

```text
python -I tools/hash_check.py show <組件或執行檔>
ASSEMBLY: <絕對路徑> sha256=<雜湊>
```

## 2. build 是不是最新（F3）

- 建好後記錄來源和輸出的內容雜湊：`hash_check.py stamp --sources <來源> --build <輸出> --out build_stamp.json`。
- 測試前檢查：`hash_check.py fresh --stamp build_stamp.json --build <輸出>`。只看內容，不看檔案時間：checkout、複製、解壓都會改時間。STALE 就重建。

## 3. 雜湊比對（F2）

- `hash_check.py compare --expected <基準> --actual <這次>`。基準裡有、這次沒有的案例是 FAIL，不是略過。
- 這次多出來的案例預設也 FAIL；確定是新增的才加 `--allow-extra`，並在報告寫原因。

## 4. 開關（F6）

- 整數開關用整數解析。值不是整數（`1.0`、`true`、空字串）就停止程式並印出原因，不可默默退回預設值。
- 第一個 frame 對每個開關印一行：`flag <NAME> read = <VALUE>`。
- 檢查：`flag_check.py --flags <TR 的開關 JSON> --log <執行 log> --before "<第二個 frame 的 log 樣式>"`。缺行、型別錯、值錯、太晚讀到，都是 STOP：這次執行不判定。

```python
# Python
raw = os.environ.get("FEATURE_X", "0")
if not re.fullmatch(r"[+-]?\d+", raw):
    sys.exit(f"FEATURE_X={raw!r} is not an integer")
FEATURE_X = int(raw)
print(f"flag FEATURE_X read = {FEATURE_X}", flush=True)   # 第一個 frame
```

```csharp
// C#
if (!int.TryParse(raw, NumberStyles.Integer, CultureInfo.InvariantCulture, out var featureX))
    throw new InvalidOperationException($"FEATURE_X={raw} is not an integer");
Debug.Log($"flag FEATURE_X read = {featureX}");             // 第一個 frame
```

## 5. 模擬和 patch 一致（N3）

- patch 和模擬讀同一個具名設定檔。檢查：`sim_check.py --patch-config <patch 設定> --sim-config <模擬設定> --measured <上次實測> --sim-output <模擬輸出>`。
- 模擬重現不了上次的實測，就先修模擬，TR 等它。

## 6. 依缺陷類別跑 CPU 檢查（N8）

- `pre_tr.py --config <專案的 pre_tr.json> --git-diff <base>`：這次改動碰到的每個缺陷類別，所有檢查都要 PASS；碰到的類別沒有檢查，TR 也擋下。

## 7. 檢查清單

- [ ] 編譯清單是明列的，不是預設 glob；印出組件路徑和雜湊
- [ ] build 的內容雜湊和來源一致（`fresh` PASS）
- [ ] 雜湊比對沒有缺案例（`missing=0`）
- [ ] 每個開關在第一個 frame 有讀取 log，型別和值都對（`flag_check` PASS）
- [ ] 碰撞／接觸類改動：碰撞標籤（哪個物件、哪一側、哪個 frame 接觸）有單元測試，期望值寫在測試裡，不是從這次輸出抄回去。DIRECTOR-WORK 沒有碰撞邏輯，這一項由專案自己寫測試，`pre_tr.json` 的對應類別指向它（F8）
- [ ] 模擬和 patch 一致，且重現上次實測（`sim_check` PASS）
- [ ] `pre_tr.py` PASS
