// SPDX-License-Identifier: GPL-2.0-only

#include <Arduino.h>
#include <Preferences.h>

namespace {

constexpr uint32_t kHeartbeatIntervalMs = 500;
Preferences preferences;
uint32_t heartbeatSequence = 0;
uint32_t lastHeartbeatAt = 0;
String inputBuffer;

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
  printBootContract();
  lastHeartbeatAt = millis();
}

void loop() {
  readCommands();
  const uint32_t now = millis();
  if (now - lastHeartbeatAt >= kHeartbeatIntervalMs) {
    lastHeartbeatAt = now;
    heartbeatSequence += 1;
    Serial.printf("SIM:HEARTBEAT sequence=%u millis=%u\n", heartbeatSequence, now);
  }
  delay(1);
}
