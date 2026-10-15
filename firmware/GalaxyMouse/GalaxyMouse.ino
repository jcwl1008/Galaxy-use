/*
  Jimmy Phone Controller v2
  Target: DNESP32S3B / ESP32-S3, Arduino-ESP32 3.3.12, built-in NimBLE.
  PC -> UART0 (CH343) -> BLE HID mouse -> paired phone.
  Serial: 115200 baud, New Line. No external Arduino libraries required.

  Revision: encrypted report characteristics trigger authentication on subscribe;
  explicit report/boot mouse formats; little-endian PnP ID; subscription/security
  state logging; deferred advertising restart; bounded serial command parser.
  This firmware has no AI API key and performs no automatic clicks or movement.
*/
#include <Arduino.h>
#include <atomic>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEHIDDevice.h>
#include <BLESecurity.h>
#include <BLEDescriptor.h>

#if !defined(CONFIG_NIMBLE_ENABLED)
#error "This revision targets the built-in NimBLE backend of Arduino-ESP32 3.3.12."
#endif
#include <host/ble_gap.h>
#include <host/ble_hs.h>

static const char *DEVICE_NAME = "Jimmy Phone Mouse v2";
static BLEHIDDevice *hid = nullptr;
static BLECharacteristic *mouseInput = nullptr;
static BLECharacteristic *bootInput = nullptr;
static std::atomic<bool> linked{false};
static std::atomic<bool> encrypted{false};
static std::atomic<bool> bonded{false};
static std::atomic<bool> reportSubscribed{false};
static std::atomic<bool> bootSubscribed{false};
static std::atomic<bool> advertiseAgain{false};
static std::atomic<uint16_t> connectionHandle{BLE_HS_CONN_HANDLE_NONE};
static struct ble_gap_event_listener diagnosticListener;

// Report ID 1. GATT payload excludes the Report ID: buttons, X, Y, wheel.
static uint8_t mouseMap[] = {
  0x05,0x01, 0x09,0x02, 0xA1,0x01, 0x85,0x01,
  0x09,0x01, 0xA1,0x00,
  0x05,0x09, 0x19,0x01, 0x29,0x03,
  0x15,0x00, 0x25,0x01, 0x95,0x03, 0x75,0x01, 0x81,0x02,
  0x95,0x01, 0x75,0x05, 0x81,0x03,
  0x05,0x01, 0x09,0x30, 0x09,0x31, 0x09,0x38,
  0x15,0x81, 0x25,0x7F, 0x75,0x08, 0x95,0x03, 0x81,0x06,
  0xC0,0xC0
};

static bool usesBootProtocol() {
  String mode = hid->protocolMode()->getValue();
  return mode.length() == 1 && static_cast<uint8_t>(mode[0]) == 0;
}

static bool readyForInput() {
  return linked.load() && encrypted.load() &&
         (usesBootProtocol() ? bootSubscribed.load() : reportSubscribed.load());
}

static void printStatus() {
  Serial.printf("[STATE] linked=%u encrypted=%u bonded=%u reportSub=%u bootSub=%u protocol=%s ready=%u\n",
    linked.load(), encrypted.load(), bonded.load(),
    reportSubscribed.load(), bootSubscribed.load(),
    usesBootProtocol() ? "boot" : "report", readyForInput());
}

class ConnectionEvents : public BLEServerCallbacks {
  void onConnect(BLEServer *, ble_gap_conn_desc *desc) override {
    connectionHandle.store(desc->conn_handle);
    linked.store(true);
    encrypted.store(desc->sec_state.encrypted);
    bonded.store(desc->sec_state.bonded);
    advertiseAgain.store(false);
    Serial.println("[LINK] CONNECTED; waiting for HID subscription and encryption");
  }
  void onDisconnect(BLEServer *) override {
    linked.store(false);
    encrypted.store(false);
    bonded.store(false);
    reportSubscribed.store(false);
    bootSubscribed.store(false);
    connectionHandle.store(BLE_HS_CONN_HANDLE_NONE);
    // Let BLEServer finish resetting security before restarting advertising.
    advertiseAgain.store(true);
    Serial.println("[LINK] DISCONNECTED");
  }
};

class ReportEvents : public BLECharacteristicCallbacks {
  void onSubscribe(BLECharacteristic *characteristic,
                   ble_gap_conn_desc *, uint16_t value) override {
    bool enabled = (value & 1) != 0;
    if (characteristic == mouseInput) reportSubscribed.store(enabled);
    if (characteristic == bootInput) bootSubscribed.store(enabled);
    Serial.printf("[HID] %s subscribed=%u\n",
      characteristic == mouseInput ? "report" : "boot", enabled);
  }
};

class PairingEvents : public BLESecurityCallbacks {
  bool onSecurityRequest() override { return true; }
  void onAuthenticationComplete(ble_gap_conn_desc *desc, int status) override {
    encrypted.store(status == 0 && desc->sec_state.encrypted);
    bonded.store(desc->sec_state.bonded);
    Serial.printf("[AUTH] status=%d encrypted=%u bonded=%u\n",
      status, encrypted.load(), bonded.load());
  }
};

// Use a separate GAP listener to capture failures as well as successes.
static int logBleEvent(struct ble_gap_event *event, void *) {
  if (event->type == BLE_GAP_EVENT_ENC_CHANGE) {
    Serial.printf("[DIAG] ENCRYPTION status=%d hex=0x%X\n",
      event->enc_change.status, (unsigned)event->enc_change.status);
  } else if (event->type == BLE_GAP_EVENT_DISCONNECT) {
    Serial.printf("[DIAG] DISCONNECT reason=%d hex=0x%X\n",
      event->disconnect.reason, (unsigned)event->disconnect.reason);
  }
  return 0;
}

static bool sendMouse(uint8_t buttons, int x, int y, int wheel) {
  if (!readyForInput()) {
    Serial.println("[ERROR] HID not ready. Use status; both encryption and subscription are required.");
    printStatus();
    return false;
  }
  uint8_t payload[4] = {buttons, (uint8_t)(int8_t)x,
                       (uint8_t)(int8_t)y, (uint8_t)(int8_t)wheel};
  bool boot = usesBootProtocol();
  if (boot && wheel != 0) {
    Serial.println("[ERROR] Boot mouse protocol has no wheel. Reconnect using report protocol.");
    return false;
  }
  BLECharacteristic *target = boot ? bootInput : mouseInput;
  target->setValue(payload, boot ? 3 : 4);
  target->notify();
  return true;
}

static void runCommand(String command) {
  command.trim(); command.toLowerCase();
  if (!command.length()) return;
  if (command == "status") { printStatus(); return; }
  if (command == "help") {
    Serial.println("status | pair | left | right | up | down | click | scrollup | scrolldown");
    return;
  }
  if (command == "pair") {
    uint16_t handle = connectionHandle.load();
    if (!linked.load() || handle == BLE_HS_CONN_HANDLE_NONE) {
      Serial.println("[ERROR] First select Jimmy Phone Mouse v2 in the phone Bluetooth settings.");
      return;
    }
    int rc = 0;
    bool started = BLESecurity::startSecurity(handle, &rc);
    Serial.printf("[AUTH] requested=%u rc=%d\n", started, rc);
    return;
  }
  bool sent = false;
  if (command == "right") sent = sendMouse(0, 40, 0, 0);
  else if (command == "left") sent = sendMouse(0, -40, 0, 0);
  else if (command == "up") sent = sendMouse(0, 0, -40, 0);
  else if (command == "down") sent = sendMouse(0, 0, 40, 0);
  else if (command == "scrollup") sent = sendMouse(0, 0, 0, 1);
  else if (command == "scrolldown") sent = sendMouse(0, 0, 0, -1);
  else if (command == "click") {
    sent = sendMouse(1, 0, 0, 0);
    if (sent) { delay(40); sent = sendMouse(0, 0, 0, 0); }
  } else {
    Serial.println("[ERROR] Unknown command; type help.");
    return;
  }
  // Submission to the BLE stack is not proof of a visible phone action.
  if (sent) Serial.println("[TX] " + command);
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n[FW] Jimmy Phone Controller v2 / Arduino-ESP32 3.3.12 / NimBLE");
  BLEDevice::init(DEVICE_NAME);
  int rc = ble_gap_event_listener_register(&diagnosticListener, logBleEvent, nullptr);
  Serial.printf("[DIAG] listener=%d\n", rc);
  BLEDevice::setSecurityCallbacks(new PairingEvents());
  BLESecurity *security = new BLESecurity();
  security->setCapability(ESP_IO_CAP_NONE);
  security->setAuthenticationMode(true, false, true);
  security->setInitEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
  security->setRespEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
  // Authenticate on protected report read/subscription, not during discovery.
  security->setForceAuthentication(false);

  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new ConnectionEvents());
  hid = new BLEHIDDevice(server);
  hid->manufacturer()->setValue("Jimmy");
  // Bypass pnp() helper: 16-bit PnP fields are little-endian on the wire.
  const uint8_t pnp[] = {0x01, 0xE5, 0x02, 0x01, 0x00, 0x00, 0x01};
  hid->deviceInfo()->getCharacteristic(BLEUUID((uint16_t)0x2A50))->setValue(pnp, sizeof(pnp));
  hid->hidInfo(0x00, 0x02);
  hid->reportMap(mouseMap, sizeof(mouseMap));

  // In core 3.3.12, inputReport() does not set NimBLE READ_ENC, and
  // setAccessPermissions() has no effect on NimBLE. Build this report explicitly.
  uint32_t reportProperties = BLECharacteristic::PROPERTY_READ |
    BLECharacteristic::PROPERTY_NOTIFY | BLECharacteristic::PROPERTY_READ_ENC;
  mouseInput = hid->hidService()->createCharacteristic(BLEUUID((uint16_t)0x2A4D), reportProperties);
  BLEDescriptor *reference = new BLEDescriptor(BLEUUID((uint16_t)0x2908));
  uint8_t referenceValue[2] = {1, 1}; // Report ID 1, Input report.
  reference->setValue(referenceValue, sizeof(referenceValue));
  mouseInput->addDescriptor(reference);
  mouseInput->setCallbacks(new ReportEvents());
  const uint8_t initial[4] = {0, 0, 0, 0};
  mouseInput->setValue(initial, sizeof(initial));

  // The library exposes Protocol Mode, so also provide the boot mouse input.
  bootInput = hid->hidService()->createCharacteristic(BLEUUID((uint16_t)0x2A33), reportProperties);
  bootInput->setCallbacks(new ReportEvents());
  bootInput->setValue(initial, 3);
  hid->setBatteryLevel(100);
  hid->startServices();

  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->setAppearance(0x03C2);
  advertising->addServiceUUID(hid->hidService()->getUUID());
  advertising->setScanResponse(true);
  advertising->start();
  Serial.printf("[READY] Pair with: %s\n", DEVICE_NAME);
  Serial.println("[READY] Serial 115200, New Line. Type help for commands.");
}

void loop() {
  static uint32_t restartAt = 0;
  static bool restartPending = false;
  if (advertiseAgain.exchange(false)) {
    restartPending = true;
    restartAt = millis() + 300;
  }
  if (restartPending && (int32_t)(millis() - restartAt) >= 0) {
    restartPending = false;
    if (!linked.load()) BLEDevice::startAdvertising();
  }
  static bool wasReady = false;
  bool ready = readyForInput();
  if (ready && !wasReady) { Serial.println("[HID] READY - try right"); printStatus(); }
  wasReady = ready;

  static char line[81];
  static size_t used = 0;
  static bool overflow = false;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      if (overflow) Serial.println("[ERROR] Command exceeds 80 characters.");
      else { line[used] = '\0'; runCommand(String(line)); }
      used = 0; overflow = false;
    } else if (c != '\r') {
      if (used < sizeof(line) - 1 && !overflow) line[used++] = c;
      else overflow = true;
    }
  }
  delay(5);
}
