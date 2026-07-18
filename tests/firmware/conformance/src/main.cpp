// SPDX-License-Identifier: GPL-2.0-only

#include <Arduino.h>
#include <Preferences.h>
#include <Wire.h>
#include <driver/spi_master.h>

namespace {

constexpr uint32_t kHeartbeatIntervalMs = 500;
Preferences preferences;
uint32_t heartbeatSequence = 0;
uint32_t lastHeartbeatAt = 0;
String inputBuffer;
volatile bool keyboardInterruptPending = false;

constexpr uint8_t kTca8418Address = 0x34;
constexpr uint8_t kTca8418InterruptPin = 11;
constexpr uint8_t kTca8418ConfigRegister = 0x01;
constexpr uint8_t kTca8418InterruptStatusRegister = 0x02;
constexpr uint8_t kTca8418EventCountRegister = 0x03;
constexpr uint8_t kTca8418EventRegister = 0x04;

constexpr spi_host_device_t kDisplaySpiHost = SPI3_HOST;
constexpr gpio_num_t kDisplayClockPin = GPIO_NUM_36;
constexpr gpio_num_t kDisplayMosiPin = GPIO_NUM_35;
constexpr gpio_num_t kDisplayChipSelectPin = GPIO_NUM_37;
constexpr uint8_t kDisplayDataCommandPin = 34;
constexpr uint8_t kDisplayResetPin = 33;
constexpr uint16_t kDisplayWidth = 240;
constexpr uint16_t kDisplayHeight = 135;
constexpr uint16_t kDisplayColumnOffset = 40;
constexpr uint16_t kDisplayRowOffset = 53;
spi_device_handle_t displayDevice = nullptr;

void IRAM_ATTR handleTca8418Interrupt() {
  keyboardInterruptPending = true;
}

bool writeTca8418Register(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(kTca8418Address);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool readTca8418Register(uint8_t reg, uint8_t &value) {
  Wire.beginTransmission(kTca8418Address);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }
  if (Wire.requestFrom(kTca8418Address, static_cast<uint8_t>(1)) != 1) {
    return false;
  }
  value = Wire.read();
  return true;
}

void configureTca8418() {
  Wire.begin(8, 9, 400000);
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
  if (!writeDisplayCommand(0x29)) {
    return false;
  }
  Serial.printf("SIM:DISPLAY controller=st7789 width=%u height=%u pattern=red-blue\n",
                kDisplayWidth, kDisplayHeight);
  return true;
}

void printBootContract() {
  preferences.begin("simulator", false);
  const uint32_t bootCount = preferences.getUInt("boot_count", 0) + 1;
  preferences.putUInt("boot_count", bootCount);

  Serial.println("SIM:BOOT version=1 profile=esp32s3-base");
  Serial.printf("SIM:FLASH bytes=%u\n", ESP.getFlashChipSize());
  Serial.printf("SIM:HEAP bytes=%u\n", ESP.getFreeHeap());
  Serial.printf("SIM:NVS boot_count=%u\n", bootCount);
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
  configureTca8418();
  if (!configureDisplay()) {
    Serial.println("SIM:DISPLAY unavailable");
  }
  printBootContract();
  lastHeartbeatAt = millis();
}

void loop() {
  readCommands();
  readTca8418Events();
  const uint32_t now = millis();
  if (now - lastHeartbeatAt >= kHeartbeatIntervalMs) {
    lastHeartbeatAt = now;
    heartbeatSequence += 1;
    Serial.printf("SIM:HEARTBEAT sequence=%u millis=%u\n", heartbeatSequence, now);
  }
  delay(1);
}
