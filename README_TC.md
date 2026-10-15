> 公開版 v3.1 預設為 ADB 唯讀，以下是需要明確授權的可選 App 模式。公司只批准 ADB 讀取時，請使用 README.md 的截圖＋ESP32 流程，不執行下列安裝／配對。管理員批准後才可使用非唯讀設定；本套件不改變公司政策。

# Galaxy Use — USB Accessibility 輔助 App（可選模式）

適用：Windows、OpenCode + OpenRouter、已授權 USB 偵錯的 S26 Ultra。ESP32 韌體及藍牙連線毋須更改。

## 已手動安裝 APK：只配對

1. 將本包覆蓋原 MCP 資料夾；關閉 OpenCode。
2. 手機保持 USB 連接並解鎖，開啟 Galaxy Phone Bridge。
3. 如未執行電腦設定，先跑 SETUP.cmd；然後雙擊 PAIR_PHONE.cmd。
4. 看見 PAIRED 後，確認手機服務已啟用並按「允許電腦連線」。
5. 重啟 OpenCode MCP，先 phone_app_status，再 phone_ui。

PAIR_PHONE.cmd 不安裝／更新 APK，也不發出啟動 App 指令；只透過已授權 ADB 寫入 App 私有配對碼，並更新本地 bridge.json。它不會繞過公司的 ADB 管理政策。如果此寫入亦被封鎖，請交由 IT 授權；不要改安全設定或改用其他通道規避限制。

## 更新：先電腦、再手機

1. 關閉舊 OpenCode 專案／停用舊 galaxy_phone MCP；關閉 Arduino Serial Monitor。
2. 將 ZIP 全部解壓縮，覆蓋原有 Galaxy_Phone_MCP 資料夾。不要在 ZIP 內執行。
3. 雙擊 SETUP.cmd。保留原有 bridge.json 及 OpenCode provider/MCP 設定；opencode.json 會先備份。
4. 將手機直接以 USB 接電腦、解鎖，允許 USB 偵錯；雙擊 INSTALL_PHONE_APP.cmd。
   腳本會核對 APK SHA-256、安裝 APK、開啟手機 App，再透過已授權 ADB 配對。
   多裝置時沿用 bridge.json 的 device_serial；不要同時連接多個未指定的手機。
5. 手機 App「Galaxy Phone Bridge」按「開啟無障礙設定」，在「已安裝的應用程式／已安裝的服務」找到 Galaxy Phone Bridge，閱讀系統提示後手動啟用。One UI 實際名稱可能不同，可在設定搜尋「Galaxy Phone Bridge」或「無障礙」。
6. 返回 Galaxy Phone Bridge，按「允許電腦連線」。App 預設暫停；啟用系統服務後仍須按這個按鈕。
7. 返回想操作的畫面。重新以 OpenCode 開啟原 MCP 資料夾，沿用原有 OpenRouter 模型。

不需重新刷 ESP32、不需更換模型，也不會自動改手機的無障礙或安全設定。
ZIP 不含你的 bridge.json、opencode.json、API Key 或任何配對 token。
若改用新資料夾，先將舊 bridge.json 複製過去（私人保管），再執行 SETUP.cmd、INSTALL_PHONE_APP.cmd。

### 貼到 OpenCode 測試

請用 galaxy_phone MCP，先以 connection_info 確認 bridge_version=3.1，再呼叫 phone_app_status。確認 paired=true、enabled=true、paused=false、locked=false 後，使用 phone_ui(backend="accessibility") 讀取目前介面，回報 route、elapsed_ms、service_ms 和首幾個文字項目。先不要截圖或點擊。

成功後 phone_ui 的 route 應為「USB Accessibility App」。
再測試：讀取目前畫面，若有唯一的「設定」項目，重用 snapshot_id，以 phone_click_text 開啟，再以新的 phone_ui 確認；不要猜測座標。

## 新增功能與路線

| 工具／設定 | 用途 |
|---|---|
| phone_app_status | 查看手機 App 配對、服務、暫停、鎖定及畫面 revision；不讀畫面 |
| phone_ui(backend="auto") | 已配對 App 時優先使用；未配對則沿用原 UI Automator |
| phone_ui(backend="accessibility") | 明確要求手機 Accessibility App，不執行 UI dump |
| phone_ui(backend="legacy") | 明確使用舊 ADB UI Automator dump 作後備 |
| phone_click_text / phone_click_node | 沿用剛才 snapshot 的路線；App 使用 ACTION_CLICK，文字標籤可交由上層可點擊列處理 |
| phone_screenshot | 保留壓縮 JPEG／原尺寸 PNG 後備 |
| esp32_* / adb_* | 保留原有 BLE 滑鼠及 ADB 控制 |

App 常駐於系統無障礙服務，直接讀取當前介面，不再逐次啟動 uiautomator 程序、寫 XML 及讀回刪檔。
App 未連接、暫停或報錯時，已配對的 auto 模式會快速回報錯誤，不會悄悄改行耗時 dump。
可明確要求 legacy 或截圖，避免重複嘗試。

## 點擊新鮮度與輸入

- phone_ui 返回 snapshot_id 和 node_id；觀察有效期 30 秒。
- App 收到畫面變動事件後 revision 增加；舊 snapshot 的點擊會拒絕。
- 點擊前再檢查節點的文字、位置、視窗、套件、可見與可用狀態，並拒絕密碼欄位及其子元素。
- 文字標籤沒有 click handler 時，最多向上找 8 層同視窗、可見、可用的可點擊父元素；不會盲目改成座標點擊。
- 點擊拒絕或失敗時不自動重試，也不自動改成 ADB 點擊；重新觀察再決定。
- App／USB 超時可能令動作結果未知；必須觀察手機後再決定，切勿直接重送點擊。
- 任何橋接輸入後，PC 快照失效；操作後以新的 phone_ui 驗證。
- bridge.json 的 adb_actions=false 同時停用 UI 點擊及 adb_* 輸入，保留觀察與 ESP32 滑鼠。
- ESP32 仍是相對 BLE 滑鼠；Accessibility 點擊並非經 ESP32。
- 本版沒有新增中文輸入工具；adb_type_ascii 仍只處理 ASCII。

## 隱私、啟用與停用

- App 開啟頁先顯示資料用途；你手動啟用無障礙服務及允許電腦連線。
- Android App 沒有 INTERNET 權限，不開放手機 TCP/Wi-Fi 服務；使用 Android abstract local socket，經已授權的 USB ADB forward 連到 PC loopback。
- 每次請求使用隨機 256-bit token 驗證。token 存在 PC bridge.json 及手機 App 私有目錄；不要分享 bridge.json，不要提交到 Git。
- APK 是供你側載使用的開發簽章版本，debuggable 用於已授權 ADB 的 run-as 配對；不是 Play 商店發佈版本。
- App 不存畫面或操作紀錄、不提供任意 shell、任意點擊座標、任意檔案讀取或遠端網絡 API。
- 觀察節點暫存在 App 記憶體供下一次點擊核對；密碼文字只用作內部節點新鮮度核對，不回傳 PC，且不寫入日誌。
- 正常 UI 文字亦可能含個人資料；OpenCode 使用 OpenRouter 時，回傳的 UI 文字／後備圖片仍會交予你所選模型供應商。
- 在手機 Galaxy Phone Bridge 按「暫停電腦連線」可停用 App 讀取及點擊。此按鈕不會停用原有 ADB／ESP32 工具；若要停止整個控制通道，關閉 OpenCode MCP 或拔除 USB，並按需要斷開 BLE。
- 在系統無障礙設定停用服務，或解除安裝 App，即可移除手機端服務。關閉 USB 偵錯也會停止 PC 通道。
- 鎖定畫面時 App 拒絕讀 UI 和點擊，請手動解鎖；它不會繞過 PIN、密碼或生物辨識。

## 速度與畫面限制

- 本版改善 UI 讀取通道，沒有加入 scrcpy、串流截圖或 OCR。
- 舊的 phone_screenshot 仍使用 ADB PNG，再在電腦壓縮；這部分擷取速度不變。
- 自繪畫面、遊戲、部分 WebView、敏感或受保護元素可能仍無可用節點。Accessibility 不是取得所有畫面內容的保證。
- 單次最多遍歷 2,000 個節點、回傳 600 個元素及最多 40 層，約 1.2 秒遍歷預算；超出時 truncated=true。個別 Android API 呼叫仍可能額外阻塞。
- 頻繁動畫／通知更新可能令節點很快過期；先等畫面穩定，再讀取及點擊。
- elapsed_ms 是 PC 端讀取總耗時，service_ms 是手機遍歷時間；不包括 OpenRouter 排隊、網絡和模型推理。沒有實機測試前不宣稱固定倍數提速。

## 故障排查

- 安裝顯示 blocked/restricted：留意手機的 Android／Samsung 安裝提示。只使用你信任的 APK，按手機正常設定及公司政策處理；腳本不會繞過限制或自動關閉安全功能。
- 「受限制的設定」阻止啟用：如系統有提供，可在此 App 的應用程式資訊選單查看「允許受限制的設定」，自行閱讀提示再決定；若由公司政策鎖定，先向管理員確認。
- 安裝顯示 UPDATE_INCOMPATIBLE：已有相同套件名稱但不同簽章版本；不要任意解除安裝其他 App。確認係本 App 舊開發版本後，手動解除安裝本 App，再跑安裝腳本及重新啟用。
- 配對失敗 run-as：確定使用本包 APK 並完成安裝；不是從其他來源取得的不同簽章／正式版本。
- phone_app_status 不通：確認 USB 偵錯、App 服務已啟用；若仍不通，關閉再啟用本 App 的無障礙服務，重新連接 MCP。不要同時開多個手機 MCP。
- paused=true：返回 App 按「允許電腦連線」。locked=true：手動解鎖。
- UI changed / snapshot expired：重新 phone_ui；不要沿用舊 node ID。
- 開啟 App 顯示未配對：重新跑 INSTALL_PHONE_APP.cmd。手機與電腦要同時有相同 token。
- route 仍為 ADB UI hierarchy：檢查更新後資料夾及 bridge_version=3.1，安裝配對後重啟 MCP。
- 不想使用 App：bridge.json 將 ui_backend 設為 legacy；保留原有工具。

## 建置與驗證

包內包含已編譯、簽章並核對的 GalaxyPhoneBridge.apk、SHA-256、完整 Java/Android 資源源碼、MCP 與測試。
Android 以 API 35 編譯、最低 API 26、target 35。源碼在 android/，重建方法見 android/BUILD.md。
Python 測試：.venv\Scripts\python.exe -m unittest discover -p "test_*.py"
測試包括真實 MCP stdio 握手、PC socket 往返、token 傳送、路線選擇、無隱藏 UI dump、點擊無自動重試／無盲目座標後備、密碼遮蓋及原有測試。
沒有連接你的 S26 Ultra 做實機測試；首次使用仍需確認 Android／One UI 啟用狀態、可讀節點、點擊與耗時。

## 官方參考

- AccessibilityService: https://developer.android.com/reference/android/accessibilityservice/AccessibilityService
- AccessibilityNodeInfo: https://developer.android.com/reference/android/view/accessibility/AccessibilityNodeInfo
- ADB forward: https://developer.android.com/tools/adb
- OpenCode MCP: https://opencode.ai/docs/mcp-servers/
