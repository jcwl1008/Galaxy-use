# GalaxyMCP+ESP32S3

**讓 OpenCode 看懂 Android 畫面，再經 ESP32-S3 藍牙滑鼠操作手機。**  
Android observations through MCP. Physical BLE mouse input through ESP32-S3.

![GalaxyMCP+ESP32S3 architecture: screenshots travel from Android to OpenCode through read-only ADB; mouse commands travel from the PC through ESP32-S3 to the phone over Bluetooth.](docs/images/how-it-works.png)

**Beta · Windows 10/11 · Android · ESP32-S3 · OpenCode · OpenRouter or a compatible local model**

## 可以做甚麼？

- 讀取手機截圖，交由你選用的 AI 模型理解畫面。
- 經 USB 串口向 ESP32-S3 發出指令，由 BLE HID 滑鼠移動、點擊及捲動。
- 預設 ADB **只讀**；Python 程式只允許裝置列表、截圖及必要的顯示尺寸／方向查詢。
- 截圖預設長邊 1280、JPEG quality 65；重用觀察，減少重複擷取與模型來回。
- 回報 `capture_ms`、`total_ms`、`returned_bytes`，協助量度擷取及壓縮時間。
- 另附需要明確授權的 Accessibility App／ADB 輸入模式，供私人或已獲管理員批准的環境使用。

**目前可行的核心流程：** 觀察截圖 → AI 判斷 → ESP32 相對移動／點擊 → 新觀察確認。
這不是手機畫面串流或即時視覺模型，也不保證每個 App 都能自動操作。

## 你需要

| 項目 | 要求 |
|---|---|
| 電腦 | Windows、Python 3.10+、OpenCode、Android platform-tools |
| 手機 | Android，解鎖並授權 USB 偵錯 |
| 控制板 | ESP32-S3；目前韌體以 DNESP32S3B N16R8 測試 |
| 連接 | 手機 USB → PC；ESP32 UART USB → PC；手機與 ESP32 BLE 配對 |
| 模型 | 工具呼叫及圖片輸入；OpenRouter 的模型能力需自行確認 |

模型可改用支援圖片及工具的本機服務，MCP 本身不儲存模型 API Key。本機效能取決於硬件。

## 快速開始

### 1. 下載及設定電腦

1. 在 GitHub 按 **Code → Download ZIP**，全部解壓到固定資料夾。
2. 先安裝 Python、OpenCode 及 Android platform-tools。
3. 雙擊 `SETUP.cmd`；程式自動尋找 adb.exe，找不到時會要求完整路徑。
4. 接好手機與 ESP32。手機 USB 偵錯需手動授權。
5. 關閉 Arduino Serial Monitor，避免佔用串口。預設串口是 COM4，可在本地 `bridge.json` 改成自己的串口。
6. 雙擊 `START_OpenCode.cmd`，或以 OpenCode Desktop 開啟這個資料夾。

設定程式建立 `.venv`、私人 `bridge.json` 及專案 `opencode.json`。已有的 OpenCode 設定會先備份並保留其他 provider/MCP 欄位。不要將私人設定提交到 Git。

### 2. 準備 ESP32

韌體在 [`firmware/GalaxyMouse/GalaxyMouse.ino`](firmware/GalaxyMouse/GalaxyMouse.ino)，完整步驟見 [ESP32 設定](docs/FIRMWARE.md)。
如果你的板已運行 **Jimmy Phone Mouse v2** 並正常連接，毋須再刷寫。否則先備份原廠韌體，再以指定 Arduino core 編譯。手機藍牙手動配對後，用 `esp32_status` 確認 `ready=true`。

### 3. 將這段貼入 OpenCode

> 使用 galaxy_phone MCP。先讀 connection_info，確認 adb_read_only=true，再讀 esp32_status。以 phone_screenshot(max_side=1280, quality=65) 描述目前手機畫面，回報 capture_ms、total_ms、returned_bytes。暫時不要點擊。之後只用 ESP32 BLE 操作；不要執行安裝、配對、UI dump 或 ADB 輸入。操作後有需要才重新擷取畫面驗證。

先測試單次移動，再測試點擊。相對滑鼠位置可能無法從截圖看見；不要猜測指標座標或宣稱點擊一定成功。

## 主要工具

| 工具 | 預設模式 |
|---|---|
| `connection_info` | 列出串口、手機及 bridge_version=3.1 |
| `esp32_status` | 查看 BLE、加密、訂閱及準備狀態 |
| `esp32_mouse` | `left/right/up/down/click/scrollup/scrolldown` |
| `phone_screenshot` | 壓縮 JPEG；`full_resolution=true` 可取原尺寸 PNG |
| `phone_ui`、`phone_click_*` | 預設停用；需要授權的非唯讀環境 |
| `adb_tap/swipe/key/type_ascii` | 預設停用 |
| `phone_app_status` | 唯讀模式只回報 App 通道不可用 |

`adb_read_only=true` 會在執行 ADB 前檢查命令，並優先於 `adb_actions`。這是本橋接的限制，不代表改變或取代公司端點管理政策。公司環境只使用已批准的命令和 BLE 控制。

## 速度及已知限制

- 壓縮減少交予模型的圖片大小；手機仍需產生原始 PNG，沒有省去這部分時間。
- OpenRouter／模型排隊與推理仍可能佔主要等待時間；免費模型的反應時間會變動。
- 一次滑鼠移動為 **40 HID units，不是 40 螢幕像素**；Android 指標加速會影響距離。
- ESP32 是相對滑鼠，不是座標點擊器；截圖可能不包含游標。
- 需要細字時才取高解像度，避免每次操作前後都重複截圖。
- 沒有提供 BLE 鍵盤、中文輸入、scrcpy 串流或 OCR。
- Accessibility 可讀到的節點取決於 App／系統；遊戲、自繪畫面及受保護內容未必有可用結構。
- APK 已編譯及驗證開發簽章；尚未在每個 One UI 版本做實機驗證。

## 可選：Accessibility 輔助 App

預設唯讀流程**不需要安裝 APK、不需要配對 App 或開啟無障礙權限**。

附帶的 [`GalaxyPhoneBridge.apk`](GalaxyPhoneBridge.apk) 及 [完整源碼](android/) 僅供已獲批准的非唯讀環境。它經 ADB forward 通訊，配對亦需寫入 App 私有資料；**手動安裝 APK 不等於已完成配對**。

若公司只批准 ADB 讀取，請維持預設模式。不要用其他安裝或通訊方式規避限制。由管理員確認需要的權限後，再按 [Accessibility 安裝與配對](README_TC.md) 操作。

## Privacy / 私隱

手機截圖和可選 UI 文字會透過 OpenCode 交予你選用的模型供應商。App 本身沒有 Internet 權限。觀察資料不會由橋接自動寫成歷史檔案，但模型客戶端／供應商的記錄政策需另行確認。

不要提交 `bridge.json`、`opencode.json`、配對 token、API Key、裝置序號、截圖或私人備份。遇到密碼、PIN 及生物辨識提示，交由裝置持有人處理。發送訊息、購買、刪除等操作需有明確授權。

## 開發與驗證

```powershell
.venv\Scripts\python.exe -m unittest discover -p "test_*.py"
```

測試涵蓋 MCP stdio、截圖壓縮、座標轉換、串口狀態、可選 App 通訊、配對流程，以及唯讀命令限制。硬件模擬測試不能代替實機測速。

[韌體說明](docs/FIRMWARE.md) · [完整 App 指引](README_TC.md) · [安全及資料處理](SECURITY.md) · [MIT License](LICENSE)

## English overview

GalaxyMCP+ESP32S3 is a local MCP bridge for OpenCode. Android screenshots are observed over authorized read-only ADB; input travels over USB serial to an ESP32-S3 BLE HID mouse. The model may run through OpenRouter or a compatible local provider. The default configuration blocks ADB writes, UI dumps, installation, pairing and ADB input. An optional Android Accessibility companion is included for expressly authorized environments. It is a beta integration, not a real-time vision stream, absolute-position BLE controller or enterprise-policy workaround.
