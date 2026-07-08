/*
 * ESP32-S3 Watchdog Module for Raspberry Pi 3 Power Management
 *
 * Purpose: Independent hardware guardian that monitors Pi health and cuts power if frozen
 *
 * Architecture:
 *   ESP32-S3 UART ← Heartbeat Signal from Pi
 *        ↓ (every 10 seconds expected)
 *   If no heartbeat for 30 seconds: Cut 5V power to Pi
 *   After 5 seconds: Restore power (force reboot)
 *
 * Blind Spot Fixed: "Offline Identity"
 *   Problem: Firebase SDK spam errors when offline → Pi CPU 100% → process freeze
 *   Solution: ESP32 watchdog detects unresponsiveness, force-resets Pi
 *
 * Hardware Connections:
 *   Pi GPIO 17 → ESP32 GPIO4 (RX serial, heartbeat signal)
 *   ESP32 GPIO5 → MOSFET gate (controls 5V relay for Pi power)
 *   5V relay → Pi power switch
 *
 * Watchdog States:
 *   INIT → WAITING → ARMED → [ONLINE/OFFLINE] → RECOVERY
 */

#include <Arduino.h>
#include <esp_system.h>
#include <EEPROM.h>
#include <time.h>

// ============ Configuration ============

#define SERIAL_BAUD 115200
#define HEARTBEAT_RX_PIN 4        // UART RX from Pi
#define POWER_CONTROL_PIN 5       // GPIO to control Pi power relay
#define LED_STATUS_PIN 2          // Status LED (optional)

#define HEARTBEAT_TIMEOUT_MS 30000  // Expect heartbeat every 10s, timeout at 30s
#define RECOVERY_WAIT_MS 5000       // Wait 5 seconds before power-on during recovery
#define HEARTBEAT_WATCHDOG_MS 3000  // Internal ESP32 watchdog (detect code hangs)

// EEPROM layout
#define EEPROM_SIZE 512
#define EEPROM_WATCHDOG_COUNT_ADDR 0    // uint32_t: number of watchdog resets
#define EEPROM_LAST_RESET_TIME_ADDR 4   // uint32_t: timestamp of last reset
#define EEPROM_FAILURE_REASON_ADDR 8    // uint8_t: reason code

// Watchdog Failure Reasons
enum WatchdogReason : uint8_t {
  REASON_NONE = 0,
  REASON_HEARTBEAT_TIMEOUT = 1,
  REASON_SERIAL_ERROR = 2,
  REASON_POWER_SURGE = 3,
  REASON_TEMPERATURE = 4,
  REASON_MANUAL_RESET = 5
};

// ============ Global State ============

enum WatchdogState {
  STATE_INIT = 0,
  STATE_WAITING = 1,      // Waiting for first heartbeat
  STATE_ARMED = 2,        // Monitoring active
  STATE_ONLINE = 3,       // Pi responding
  STATE_OFFLINE = 4,      // Pi not responding
  STATE_RECOVERY = 5      // Pi power being cycled
};

struct WatchdogStatus {
  WatchdogState state;
  uint32_t last_heartbeat_ms;
  uint32_t watchdog_resets;
  WatchdogReason last_reason;
  uint32_t uptime_ms;
  float esp32_temp_c;
};

WatchdogStatus g_status = {
  .state = STATE_INIT,
  .last_heartbeat_ms = 0,
  .watchdog_resets = 0,
  .last_reason = REASON_NONE,
  .uptime_ms = 0,
  .esp32_temp_c = 0.0
};

// ============ Logging & Status ============

void log_event(const char* level, const char* message) {
  /**
   * Log to serial with timestamp
   * Example: [00:00:15] [INFO] Heartbeat received
   */
  uint32_t ms = millis();
  uint32_t sec = ms / 1000;
  uint32_t hour = sec / 3600;
  uint32_t min = (sec % 3600) / 60;
  uint32_t secs = sec % 60;

  Serial.printf("[%02d:%02d:%02d.%03d] [%s] %s\n",
    (int)hour, (int)min, (int)secs, (int)(ms % 1000),
    level, message);
}

void update_led_status() {
  /**
   * Visual status indicator
   * INIT: off
   * WAITING: slow blink (0.5Hz)
   * ARMED/ONLINE: fast blink (2Hz)
   * OFFLINE: solid on
   * RECOVERY: flashing (0.1s on, 1s off)
   */
  static uint32_t last_blink = 0;
  uint32_t now = millis();

  if (now - last_blink < 100) return;
  last_blink = now;

  static bool led_state = false;

  switch (g_status.state) {
    case STATE_INIT:
      digitalWrite(LED_STATUS_PIN, LOW);
      break;

    case STATE_WAITING:
      if ((now / 1000) % 2 == 0) {
        digitalWrite(LED_STATUS_PIN, HIGH);
      } else {
        digitalWrite(LED_STATUS_PIN, LOW);
      }
      break;

    case STATE_ARMED:
    case STATE_ONLINE:
      if ((now / 500) % 2 == 0) {
        digitalWrite(LED_STATUS_PIN, HIGH);
      } else {
        digitalWrite(LED_STATUS_PIN, LOW);
      }
      break;

    case STATE_OFFLINE:
      digitalWrite(LED_STATUS_PIN, HIGH);
      break;

    case STATE_RECOVERY:
      if ((now / 100) % 12 < 1) {  // 0.1s on, 1s off
        digitalWrite(LED_STATUS_PIN, HIGH);
      } else {
        digitalWrite(LED_STATUS_PIN, LOW);
      }
      break;
  }
}

// ============ Power Control ============

void cut_pi_power() {
  /**
   * Cut 5V power to Raspberry Pi via MOSFET relay
   */
  digitalWrite(POWER_CONTROL_PIN, LOW);
  log_event("WARN", "Pi power CUT (watchdog timeout)");
}

void restore_pi_power() {
  /**
   * Restore 5V power to Raspberry Pi
   */
  digitalWrite(POWER_CONTROL_PIN, HIGH);
  log_event("INFO", "Pi power RESTORED");
}

void cycle_pi_power() {
  /**
   * Force Pi reboot: cut power, wait, restore
   */
  log_event("CRIT", "Initiating Pi power cycle (watchdog recovery)");
  g_status.state = STATE_RECOVERY;

  cut_pi_power();
  delay(RECOVERY_WAIT_MS);
  restore_pi_power();

  g_status.state = STATE_WAITING;
  g_status.last_heartbeat_ms = millis();
}

// ============ EEPROM Logging ============

void save_watchdog_event(WatchdogReason reason) {
  /**
   * Persist watchdog events to EEPROM for post-analysis
   * Survives power cycles
   */
  uint32_t resets = EEPROM.readUInt32(EEPROM_WATCHDOG_COUNT_ADDR);
  resets++;

  EEPROM.writeUInt32(EEPROM_WATCHDOG_COUNT_ADDR, resets);
  EEPROM.writeUInt32(EEPROM_LAST_RESET_TIME_ADDR, (uint32_t)time(NULL));
  EEPROM.writeByte(EEPROM_FAILURE_REASON_ADDR, (uint8_t)reason);
  EEPROM.commit();

  char msg[100];
  snprintf(msg, sizeof(msg), "Watchdog event #%u: reason=%d (saved to EEPROM)",
    resets, (int)reason);
  log_event("INFO", msg);
}

void print_watchdog_stats() {
  /**
   * Print accumulated statistics from EEPROM
   */
  uint32_t resets = EEPROM.readUInt32(EEPROM_WATCHDOG_COUNT_ADDR);
  uint32_t last_reset = EEPROM.readUInt32(EEPROM_LAST_RESET_TIME_ADDR);
  uint8_t last_reason = EEPROM.readByte(EEPROM_FAILURE_REASON_ADDR);

  char msg[150];
  snprintf(msg, sizeof(msg),
    "Watchdog Stats: resets=%u, last_reset=%u, reason=%u",
    resets, last_reset, last_reason);
  log_event("INFO", msg);
}

// ============ Monitoring ============

void check_esp32_temperature() {
  /**
   * Monitor ESP32 internal temperature
   * If >80°C, potential power issue
   */
  float temp = (float)esp_ts_get_cpu_temp() / 100.0;  // Internal sensor
  g_status.esp32_temp_c = temp;

  if (temp > 80.0) {
    char msg[80];
    snprintf(msg, sizeof(msg), "ESP32 temperature HIGH: %.1f°C", temp);
    log_event("WARN", msg);
  }
}

void check_heartbeat() {
  /**
   * Main watchdog logic: check if Pi is still alive
   * Expected: Pi sends 'H' every ~10 seconds
   * Timeout: 30 seconds without heartbeat → power cycle
   */
  uint32_t now = millis();
  uint32_t time_since_heartbeat = now - g_status.last_heartbeat_ms;

  if (g_status.state == STATE_WAITING) {
    // Initial boot, waiting for first heartbeat
    if (time_since_heartbeat > 60000) {
      log_event("WARN", "No heartbeat after 60s, forcing power cycle");
      g_status.last_reason = REASON_HEARTBEAT_TIMEOUT;
      save_watchdog_event(REASON_HEARTBEAT_TIMEOUT);
      cycle_pi_power();
    }
  }

  else if (g_status.state == STATE_ARMED || g_status.state == STATE_ONLINE) {
    // Monitor mode
    if (time_since_heartbeat > HEARTBEAT_TIMEOUT_MS) {
      log_event("CRIT", "Heartbeat TIMEOUT → Pi unresponsive");
      g_status.state = STATE_OFFLINE;
      g_status.last_reason = REASON_HEARTBEAT_TIMEOUT;
      save_watchdog_event(REASON_HEARTBEAT_TIMEOUT);

      // Wait 5 more seconds before cycling (give Pi chance to recover)
      delay(5000);
      cycle_pi_power();
    }
    else if (time_since_heartbeat < 15000 && g_status.state == STATE_WAITING) {
      g_status.state = STATE_ARMED;
      log_event("INFO", "Watchdog ARMED (first heartbeat received)");
    }
  }

  else if (g_status.state == STATE_RECOVERY) {
    // Wait for Pi to boot up after power cycle
    if (time_since_heartbeat < 5000) {
      log_event("INFO", "Recovery in progress, waiting for Pi to boot");
    } else if (time_since_heartbeat > 120000) {
      log_event("CRIT", "Recovery FAILED: Pi not responding after power cycle");
      // Keep trying (loop back to WAITING state)
      g_status.state = STATE_WAITING;
    }
  }
}

// ============ Serial Communication ============

void serial_event_handler() {
  /**
   * Handler for incoming serial data from Pi
   * Expected format: 'H' (heartbeat character)
   * Or commands: 'S' (get status), 'R' (reset stats)
   */
  if (!Serial.available()) return;

  int c = Serial.read();

  switch (c) {
    case 'H':  // Heartbeat
      g_status.last_heartbeat_ms = millis();
      if (g_status.state == STATE_WAITING) {
        g_status.state = STATE_ARMED;
        log_event("INFO", "First heartbeat received → ARMED");
      }
      if (g_status.state != STATE_ONLINE && g_status.state != STATE_ARMED) {
        g_status.state = STATE_ONLINE;
      }
      // Silent, don't spam logs
      break;

    case 'S':  // Status request
      Serial.println("\n=== Watchdog Status ===");
      Serial.printf("State: %d\n", g_status.state);
      Serial.printf("Uptime: %lu ms\n", g_status.uptime_ms);
      Serial.printf("Last Heartbeat: %lu ms ago\n",
        millis() - g_status.last_heartbeat_ms);
      Serial.printf("Temperature: %.1f°C\n", g_status.esp32_temp_c);
      print_watchdog_stats();
      break;

    case 'R':  // Reset stats
      EEPROM.writeUInt32(EEPROM_WATCHDOG_COUNT_ADDR, 0);
      EEPROM.commit();
      log_event("INFO", "Watchdog stats RESET");
      break;

    case '?':  // Help
      Serial.println("\n=== ESP32 Watchdog Commands ===");
      Serial.println("H - Heartbeat (sent by Pi every 10s)");
      Serial.println("S - Print status");
      Serial.println("R - Reset statistics");
      break;

    default:
      char msg[60];
      snprintf(msg, sizeof(msg), "Unknown command: 0x%02X", c);
      log_event("WARN", msg);
  }
}

// ============ Initialization ============

void setup() {
  // Serial communication
  Serial.begin(SERIAL_BAUD);
  delay(500);  // Wait for serial to stabilize

  // GPIO setup
  pinMode(LED_STATUS_PIN, OUTPUT);
  pinMode(POWER_CONTROL_PIN, OUTPUT);
  digitalWrite(LED_STATUS_PIN, LOW);
  digitalWrite(POWER_CONTROL_PIN, HIGH);  // Pi ON by default

  // EEPROM
  EEPROM.begin(EEPROM_SIZE);

  // Initial state
  g_status.state = STATE_INIT;
  g_status.last_heartbeat_ms = millis();

  log_event("INFO", "=== ESP32-S3 Watchdog Initialized ===");
  print_watchdog_stats();
  log_event("INFO", "Waiting for Pi heartbeat...");

  // Feed the internal watchdog to prevent early reboot
  esp_task_wdt_reset();
}

// ============ Main Loop ============

void loop() {
  uint32_t loop_start = millis();

  // 1. Check for incoming serial (Pi heartbeat or commands)
  serial_event_handler();

  // 2. Update watchdog logic
  check_heartbeat();
  check_esp32_temperature();

  // 3. Update visual status
  update_led_status();

  // 4. Update uptime
  g_status.uptime_ms = millis();

  // 5. Feed internal watchdog to prevent brown-out reset
  esp_task_wdt_reset();

  // 6. Yield to other tasks
  delay(100);  // Check heartbeat ~10 times per second

  // Sanity check: loop should complete within 500ms
  uint32_t loop_duration = millis() - loop_start;
  if (loop_duration > 500) {
    char msg[80];
    snprintf(msg, sizeof(msg), "WARN: Loop delay %.0f ms (system under stress)",
      (float)loop_duration);
    log_event("WARN", msg);
  }
}

/*
 * ============ Integration with Pi ============
 *
 * On Raspberry Pi 3, add this cron job to send heartbeat every 10 seconds:
 *
 * #!/bin/bash
 * # /usr/local/bin/send_watchdog_heartbeat.sh
 * while true; do
 *   echo -n "H" > /dev/ttyUSB0  # UART to ESP32
 *   sleep 10
 * done
 *
 * Add to crontab:
 * @reboot /usr/local/bin/send_watchdog_heartbeat.sh &
 *
 * Alternative: Python script
 * import serial
 * import time
 *
 * ser = serial.Serial('/dev/ttyUSB0', 115200)
 * while True:
 *     ser.write(b'H')
 *     time.sleep(10)
 */
