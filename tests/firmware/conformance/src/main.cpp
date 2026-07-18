// SPDX-License-Identifier: GPL-2.0-only

#include <Arduino.h>
#include <Preferences.h>
#include <Wire.h>

namespace {

constexpr uint32_t kHeartbeatIntervalMs = 500;
constexpr uint32_t kKeyboardPollIntervalMs = 50;
Preferences preferences;
uint32_t heartbeatSequence = 0;
uint32_t lastHeartbeatAt = 0;
uint32_t lastKeyboardPollAt = 0;
String inputBuffer;

constexpr uint8_t kTca8418Address = 0x34;
constexpr uint8_t kTca8418ConfigRegister = 0x01;
constexpr uint8_t kTca8418InterruptStatusRegister = 0x02;
constexpr uint8_t kTca8418EventCountRegister = 0x03;
constexpr uint8_t kTca8418EventRegister = 0x04;

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
}

void readTca8418Events() {
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
  printBootContract();
  lastHeartbeatAt = millis();
  lastKeyboardPollAt = millis();
}

void loop() {
  readCommands();
  const uint32_t now = millis();
  if (now - lastKeyboardPollAt >= kKeyboardPollIntervalMs) {
    lastKeyboardPollAt = now;
    readTca8418Events();
  }
  if (now - lastHeartbeatAt >= kHeartbeatIntervalMs) {
    lastHeartbeatAt = now;
    heartbeatSequence += 1;
    Serial.printf("SIM:HEARTBEAT sequence=%u millis=%u\n", heartbeatSequence, now);
  }
  delay(1);
}
