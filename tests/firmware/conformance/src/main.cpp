// SPDX-License-Identifier: GPL-2.0-only

#include <Arduino.h>
#include <Preferences.h>
#include <Wire.h>
#include <driver/spi_master.h>
#include <soc/esp32s3/spiram.h>

namespace {

constexpr uint32_t kHeartbeatIntervalMs = 500;
Preferences preferences;
uint32_t heartbeatSequence = 0;
uint32_t lastHeartbeatAt = 0;
uint32_t bootCount = 0;
size_t nvsWriteBytes = 0;
String inputBuffer;
volatile bool keyboardInterruptPending = false;

#if SIMULATOR_STICKS3
TwoWire &boardWire = Wire;
constexpr uint8_t kButtonAPin = 11;
constexpr uint8_t kButtonBPin = 12;
constexpr uint8_t kBmi270Address = 0x68;
constexpr uint8_t kM5Pm1Address = 0x6E;
constexpr uint8_t kInternalSdaPin = 47;
constexpr uint8_t kInternalSclPin = 48;
int lastButtonA = HIGH;
int lastButtonB = HIGH;
int16_t lastMotion[6] = {};
uint16_t lastBatteryMv = 0;
uint16_t lastVinMv = 0;
uint8_t lastPowerSource = 0xFF;
bool lastCharging = false;
bool stickTelemetryReady = false;
uint32_t lastStickTelemetryAt = 0;
#else
TwoWire boardWire(1);
constexpr uint8_t kBacklightPin = 38;
constexpr uint8_t kBacklightChannel = 7;
#endif

constexpr uint8_t kTca8418Address = 0x34;
constexpr uint8_t kTca8418InterruptPin = 11;
constexpr uint8_t kTca8418ConfigRegister = 0x01;
constexpr uint8_t kTca8418InterruptStatusRegister = 0x02;
constexpr uint8_t kTca8418EventCountRegister = 0x03;
constexpr uint8_t kTca8418EventRegister = 0x04;

constexpr spi_host_device_t kDisplaySpiHost = SPI3_HOST;
#if SIMULATOR_STICKS3
constexpr char kBoardId[] = "sticks3";
constexpr gpio_num_t kDisplayClockPin = GPIO_NUM_40;
constexpr gpio_num_t kDisplayMosiPin = GPIO_NUM_39;
constexpr gpio_num_t kDisplayChipSelectPin = GPIO_NUM_41;
constexpr uint8_t kDisplayDataCommandPin = 45;
constexpr uint8_t kDisplayResetPin = 21;
constexpr uint16_t kDisplayWidth = 135;
constexpr uint16_t kDisplayHeight = 240;
constexpr uint16_t kDisplayColumnOffset = 52;
constexpr uint16_t kDisplayRowOffset = 40;
#else
constexpr char kBoardId[] = "cardputer-adv";
constexpr gpio_num_t kDisplayClockPin = GPIO_NUM_36;
constexpr gpio_num_t kDisplayMosiPin = GPIO_NUM_35;
constexpr gpio_num_t kDisplayChipSelectPin = GPIO_NUM_37;
constexpr uint8_t kDisplayDataCommandPin = 34;
constexpr uint8_t kDisplayResetPin = 33;
constexpr uint16_t kDisplayWidth = 240;
constexpr uint16_t kDisplayHeight = 135;
constexpr uint16_t kDisplayColumnOffset = 40;
constexpr uint16_t kDisplayRowOffset = 53;
#endif
spi_device_handle_t displayDevice = nullptr;

void IRAM_ATTR handleTca8418Interrupt() {
  keyboardInterruptPending = true;
}

bool writeTca8418Register(uint8_t reg, uint8_t value) {
  boardWire.beginTransmission(kTca8418Address);
  boardWire.write(reg);
  boardWire.write(value);
  return boardWire.endTransmission() == 0;
}

bool readTca8418Register(uint8_t reg, uint8_t &value) {
  boardWire.beginTransmission(kTca8418Address);
  boardWire.write(reg);
  if (boardWire.endTransmission(false) != 0) {
    return false;
  }
  if (boardWire.requestFrom(kTca8418Address, static_cast<uint8_t>(1)) != 1) {
    return false;
  }
  value = boardWire.read();
  return true;
}

void configureTca8418() {
  boardWire.begin(8, 9, 400000);
  pinMode(kTca8418InterruptPin, INPUT);
  attachInterrupt(digitalPinToInterrupt(kTca8418InterruptPin),
                  handleTca8418Interrupt, CHANGE);
  const bool configured =
      writeTca8418Register(0x1D, 0x7F) &&
      writeTca8418Register(0x1E, 0xFF) &&
      writeTca8418Register(kTca8418ConfigRegister, 0x01);

  uint8_t config = 0;
  if (!configured || !readTca8418Register(kTca8418ConfigRegister, config)) {
    Serial.println("SIM:TCA8418 unavailable");
    return;
  }
  Serial.printf("SIM:TCA8418 address=0x%02x cfg=0x%02x\n",
                kTca8418Address, config);
  Serial.printf("SIM:TCA8418_IRQ pin=%u mode=change\n", kTca8418InterruptPin);
}

void readTca8418Events() {
  if (!keyboardInterruptPending) {
    return;
  }

  uint8_t count = 0;
  if (!readTca8418Register(kTca8418EventCountRegister, count)) {
    return;
  }
  count &= 0x0F;
  while (count-- > 0) {
    uint8_t event = 0;
    if (!readTca8418Register(kTca8418EventRegister, event)) {
      return;
    }
    Serial.printf("SIM:KEY raw=0x%02x\n", event);
  }
  writeTca8418Register(kTca8418InterruptStatusRegister, 0x01);
  uint8_t interruptStatus = 0;
  if (readTca8418Register(kTca8418InterruptStatusRegister,
                          interruptStatus) &&
      !(interruptStatus & 0x01)) {
    keyboardInterruptPending = false;
  }
}

#if SIMULATOR_STICKS3
bool writeI2cRegister(uint8_t address, uint8_t reg, uint8_t value) {
  boardWire.beginTransmission(address);
  boardWire.write(reg);
  boardWire.write(value);
  return boardWire.endTransmission() == 0;
}

bool readI2cRegisters(uint8_t address, uint8_t reg, uint8_t *values,
                      size_t length) {
  boardWire.beginTransmission(address);
  boardWire.write(reg);
  if (boardWire.endTransmission(false) != 0) {
    return false;
  }
  if (boardWire.requestFrom(address, static_cast<uint8_t>(length)) != length) {
    return false;
  }
  for (size_t index = 0; index < length; index++) {
    values[index] = boardWire.read();
  }
  return true;
}

uint16_t littleEndianWord(const uint8_t *bytes) {
  return static_cast<uint16_t>(bytes[0]) |
         (static_cast<uint16_t>(bytes[1]) << 8);
}

void configureStickPeripherals() {
  boardWire.begin(kInternalSdaPin, kInternalSclPin, 400000);
  pinMode(kButtonAPin, INPUT_PULLUP);
  pinMode(kButtonBPin, INPUT_PULLUP);
  lastButtonA = digitalRead(kButtonAPin);
  lastButtonB = digitalRead(kButtonBPin);
  Serial.printf("SIM:BUTTONS a_gpio=%u b_gpio=%u active=low\n", kButtonAPin,
                kButtonBPin);

  uint8_t chipId = 0;
  const bool bmiReady =
      readI2cRegisters(kBmi270Address, 0x00, &chipId, 1) && chipId == 0x24 &&
      writeI2cRegister(kBmi270Address, 0x41, 0x02) &&
      writeI2cRegister(kBmi270Address, 0x43, 0x00);
  Serial.printf("SIM:BMI270 address=0x%02x chip_id=0x%02x ready=%u\n",
                kBmi270Address, chipId, bmiReady);

  uint8_t pmicId = 0;
  const bool pmicReady =
      readI2cRegisters(kM5Pm1Address, 0x00, &pmicId, 1);
  Serial.printf("SIM:M5PM1 address=0x%02x device_id=0x%02x ready=%u\n",
                kM5Pm1Address, pmicId, pmicReady);
}

void readStickButtons() {
  const int buttonA = digitalRead(kButtonAPin);
  const int buttonB = digitalRead(kButtonBPin);
  if (buttonA != lastButtonA) {
    lastButtonA = buttonA;
    Serial.printf("SIM:BUTTON id=a pressed=%u\n", buttonA == LOW);
  }
  if (buttonB != lastButtonB) {
    lastButtonB = buttonB;
    Serial.printf("SIM:BUTTON id=b pressed=%u\n", buttonB == LOW);
  }
}

void readStickTelemetry() {
  const uint32_t now = millis();
  if (stickTelemetryReady && now - lastStickTelemetryAt < 50) {
    return;
  }
  lastStickTelemetryAt = now;

  uint8_t motionBytes[12];
  int16_t motion[6];
  if (readI2cRegisters(kBmi270Address, 0x0C, motionBytes,
                       sizeof(motionBytes))) {
    for (size_t index = 0; index < 6; index++) {
      motion[index] = static_cast<int16_t>(littleEndianWord(
          motionBytes + index * 2));
    }
    if (!stickTelemetryReady ||
        memcmp(motion, lastMotion, sizeof(motion)) != 0) {
      memcpy(lastMotion, motion, sizeof(motion));
      Serial.printf(
          "SIM:IMU_RAW ax=%d ay=%d az=%d gx=%d gy=%d gz=%d\n",
          motion[0], motion[1], motion[2], motion[3], motion[4], motion[5]);
    }
  }

  uint8_t source = 0;
  uint8_t gpioInput = 0;
  uint8_t voltageBytes[4];
  if (readI2cRegisters(kM5Pm1Address, 0x04, &source, 1) &&
      readI2cRegisters(kM5Pm1Address, 0x12, &gpioInput, 1) &&
      readI2cRegisters(kM5Pm1Address, 0x22, voltageBytes, 4)) {
    const uint16_t batteryMv = littleEndianWord(voltageBytes);
    const uint16_t vinMv = littleEndianWord(voltageBytes + 2);
    const bool charging = !(gpioInput & 0x01);
    if (!stickTelemetryReady || batteryMv != lastBatteryMv ||
        vinMv != lastVinMv || source != lastPowerSource ||
        charging != lastCharging) {
      lastBatteryMv = batteryMv;
      lastVinMv = vinMv;
      lastPowerSource = source;
      lastCharging = charging;
      Serial.printf(
          "SIM:POWER battery_mv=%u vin_mv=%u source=%u charging=%u\n",
          batteryMv, vinMv, source, charging);
    }
  }
  stickTelemetryReady = true;
}
#endif

#if !SIMULATOR_STICKS3
bool configureBacklight() {
  const uint32_t frequency = ledcSetup(kBacklightChannel, 256, 8);
  if (frequency == 0) {
    return false;
  }
  ledcAttachPin(kBacklightPin, kBacklightChannel);
  ledcWrite(kBacklightChannel, 110);
  Serial.printf(
      "SIM:LEDC channel=%u pin=%u frequency=%u duty=110 configured=1\n",
      kBacklightChannel, kBacklightPin, frequency);
  return true;
}
#endif

bool transmitDisplay(const uint8_t *data, size_t length, bool isData) {
  digitalWrite(kDisplayDataCommandPin, isData ? HIGH : LOW);
  spi_transaction_t transaction = {};
  transaction.length = length * 8;
  transaction.tx_buffer = data;
  return spi_device_polling_transmit(displayDevice, &transaction) == ESP_OK;
}

bool writeDisplayCommand(uint8_t command) {
  return transmitDisplay(&command, sizeof(command), false);
}

bool writeDisplayData(const uint8_t *data, size_t length) {
  return transmitDisplay(data, length, true);
}

bool setDisplayWindow(uint16_t xStart, uint16_t yStart, uint16_t xEnd,
                      uint16_t yEnd) {
  const uint8_t columns[] = {
      static_cast<uint8_t>(xStart >> 8), static_cast<uint8_t>(xStart),
      static_cast<uint8_t>(xEnd >> 8), static_cast<uint8_t>(xEnd),
  };
  const uint8_t rows[] = {
      static_cast<uint8_t>(yStart >> 8), static_cast<uint8_t>(yStart),
      static_cast<uint8_t>(yEnd >> 8), static_cast<uint8_t>(yEnd),
  };
  return writeDisplayCommand(0x2A) && writeDisplayData(columns, sizeof(columns)) &&
         writeDisplayCommand(0x2B) && writeDisplayData(rows, sizeof(rows));
}

bool configureDisplay() {
  pinMode(kDisplayDataCommandPin, OUTPUT);
  pinMode(kDisplayResetPin, OUTPUT);
  digitalWrite(kDisplayResetPin, LOW);
  delay(5);
  digitalWrite(kDisplayResetPin, HIGH);
  delay(5);

  const spi_bus_config_t busConfig = {
      .mosi_io_num = kDisplayMosiPin,
      .miso_io_num = GPIO_NUM_NC,
      .sclk_io_num = kDisplayClockPin,
      .quadwp_io_num = GPIO_NUM_NC,
      .quadhd_io_num = GPIO_NUM_NC,
      .max_transfer_sz = 64,
  };
  const spi_device_interface_config_t deviceConfig = {
      .mode = 0,
      .clock_speed_hz = 10000000,
      .spics_io_num = kDisplayChipSelectPin,
      .queue_size = 1,
  };
  if (spi_bus_initialize(kDisplaySpiHost, &busConfig, SPI_DMA_DISABLED) !=
      ESP_OK) {
    return false;
  }
  if (spi_bus_add_device(kDisplaySpiHost, &deviceConfig, &displayDevice) !=
      ESP_OK) {
    return false;
  }

  const uint8_t colorMode = 0x55;
  const uint8_t memoryAccess = 0x00;
  if (!writeDisplayCommand(0x01) || !writeDisplayCommand(0x11) ||
      !writeDisplayCommand(0x3A) || !writeDisplayData(&colorMode, 1) ||
      !writeDisplayCommand(0x36) || !writeDisplayData(&memoryAccess, 1) ||
      !setDisplayWindow(kDisplayColumnOffset, kDisplayRowOffset,
                        kDisplayColumnOffset + kDisplayWidth - 1,
                        kDisplayRowOffset + kDisplayHeight - 1) ||
      !writeDisplayCommand(0x2C)) {
    return false;
  }

  uint8_t pixels[64];
  size_t buffered = 0;
  for (uint16_t y = 0; y < kDisplayHeight; y++) {
    const uint16_t color = y < (kDisplayHeight / 2) ? 0xF800 : 0x001F;
    for (uint16_t x = 0; x < kDisplayWidth; x++) {
      pixels[buffered++] = color >> 8;
      pixels[buffered++] = color;
      if (buffered == sizeof(pixels)) {
        if (!writeDisplayData(pixels, buffered)) {
          return false;
        }
        buffered = 0;
      }
    }
  }
  if (buffered && !writeDisplayData(pixels, buffered)) {
    return false;
  }
  if (!writeDisplayCommand(0x21) || !writeDisplayCommand(0x29)) {
    return false;
  }
  Serial.printf("SIM:DISPLAY controller=st7789 width=%u height=%u pattern=red-blue\n",
                kDisplayWidth, kDisplayHeight);
  return true;
}

bool verifyPsram() {
#if SIMULATOR_STICKS3
  constexpr size_t kTestBytes = 4096;
  const size_t psramBytes = esp_spiram_get_size();
  const size_t heapPsramBytes = ESP.getPsramSize();
  const size_t freePsramBytes = ESP.getFreePsram();
  uint8_t *testMemory = static_cast<uint8_t *>(ps_malloc(kTestBytes));
  if (testMemory == nullptr || psramBytes != 8 * 1024 * 1024) {
    Serial.printf("SIM:PSRAM_DIAG bytes=%u heap_bytes=%u free=%u allocation=%s\n",
                  psramBytes, heapPsramBytes, freePsramBytes,
                  testMemory == nullptr ? "failed" : "ok");
    free(testMemory);
    return false;
  }
  for (size_t index = 0; index < kTestBytes; index++) {
    testMemory[index] = static_cast<uint8_t>((index * 37) ^ (index >> 3));
  }
  for (size_t index = 0; index < kTestBytes; index++) {
    const uint8_t expected = static_cast<uint8_t>((index * 37) ^ (index >> 3));
    if (testMemory[index] != expected) {
      free(testMemory);
      return false;
    }
  }
  free(testMemory);
  Serial.printf("SIM:PSRAM bytes=%u test=pass heap_bytes=%u\n",
                psramBytes, heapPsramBytes);
#endif
  return true;
}

void initializeBootState() {
  preferences.begin("simulator", false);
  bootCount = preferences.getUInt("boot_count", 0) + 1;
  nvsWriteBytes = preferences.putUInt("boot_count", bootCount);
}

void printBootContract() {
  const uint32_t nvsReadback = preferences.getUInt("boot_count", 0);

  Serial.printf("SIM:BOOT version=1 profile=%s\n", kBoardId);
  Serial.printf("SIM:FLASH bytes=%u\n", ESP.getFlashChipSize());
  Serial.printf("SIM:HEAP bytes=%u\n", ESP.getFreeHeap());
  Serial.printf("SIM:NVS boot_count=%u write_bytes=%u readback=%u\n",
                bootCount, nvsWriteBytes, nvsReadback);
  Serial.println("SIM:READY commands=ping,reset,nvs-clear");
}

void handleCommand(const String &command) {
  if (command == "ping") {
    Serial.println("SIM:PONG");
    return;
  }
  if (command == "reset") {
    Serial.println("SIM:RESET requested");
    Serial.flush();
    ESP.restart();
  }
  if (command == "nvs-clear") {
    preferences.clear();
    Serial.println("SIM:NVS cleared");
    return;
  }
  Serial.printf("SIM:ERROR unknown_command=%s\n", command.c_str());
}

void readCommands() {
  while (Serial.available() > 0) {
    const char value = static_cast<char>(Serial.read());
    if (value == '\r') {
      continue;
    }
    if (value == '\n') {
      inputBuffer.trim();
      if (!inputBuffer.isEmpty()) {
        handleCommand(inputBuffer);
      }
      inputBuffer = "";
      continue;
    }
    if (inputBuffer.length() < 64) {
      inputBuffer += value;
    }
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(50);
#if !SIMULATOR_STICKS3
  configureTca8418();
  if (!configureBacklight()) {
    Serial.println("SIM:LEDC unavailable");
  }
#else
  configureStickPeripherals();
#endif
  initializeBootState();
  if (!verifyPsram()) {
    Serial.println("SIM:PSRAM unavailable");
  }
  if (!configureDisplay()) {
    Serial.println("SIM:DISPLAY unavailable");
  }
  printBootContract();
  lastHeartbeatAt = millis();
}

void loop() {
  readCommands();
#if !SIMULATOR_STICKS3
  readTca8418Events();
#else
  readStickButtons();
  readStickTelemetry();
#endif
  const uint32_t now = millis();
  if (now - lastHeartbeatAt >= kHeartbeatIntervalMs) {
    lastHeartbeatAt = now;
    heartbeatSequence += 1;
    Serial.printf("SIM:HEARTBEAT sequence=%u millis=%u\n", heartbeatSequence, now);
  }
  delay(1);
}
