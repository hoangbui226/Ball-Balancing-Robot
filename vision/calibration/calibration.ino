#include <Arduino.h>
#include "esp_camera.h"
#include "board_config.h"

// Calibration only: camera picture and HSV sliders. The robot sketch is ball_track.ino.
// Close the Serial Monitor, then run:
//   python vision/calibration/view.py --port COM7
// Baud must match kBaud in view.py.
// Lines that start with S set brightness, contrast, saturation, exposure, gain, white balance, auto exposure, light.

static const int kBaud = 1500000;
static const int kJpegQuality = 18;

static bool start_camera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.frame_size = FRAMESIZE_QVGA;
  config.pixel_format = PIXFORMAT_JPEG;
  config.jpeg_quality = kJpegQuality;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.fb_count = 2;

  if (!psramFound() || esp_camera_init(&config) != ESP_OK) {
    return false;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  sensor->set_framesize(sensor, FRAMESIZE_QVGA);
  sensor->set_quality(sensor, kJpegQuality);
  sensor->set_whitebal(sensor, 1);
  sensor->set_awb_gain(sensor, 1);
  sensor->set_wb_mode(sensor, 0);
  sensor->set_exposure_ctrl(sensor, 1);
  sensor->set_aec2(sensor, 1);
  sensor->set_gain_ctrl(sensor, 1);
  sensor->set_brightness(sensor, 0);
  sensor->set_contrast(sensor, 0);
  sensor->set_saturation(sensor, 0);
  return true;
}

static void apply_command(const char *line) {
  int brightness, contrast, saturation, exposure, gain, whitebal, auto_exposure, light;
  if (sscanf(line, "S %d %d %d %d %d %d %d %d", &brightness, &contrast, &saturation, &exposure, &gain, &whitebal, &auto_exposure, &light) != 8) {
    return;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  brightness = constrain(brightness, -2, 2);
  contrast = constrain(contrast, -2, 2);
  saturation = constrain(saturation, -2, 2);
  exposure = constrain(exposure, 0, 1200);
  gain = constrain(gain, 0, 30);
  whitebal = whitebal ? 1 : 0;
  light = constrain(light, 0, 4);

  sensor->set_brightness(sensor, brightness);
  sensor->set_contrast(sensor, contrast);
  sensor->set_saturation(sensor, saturation);
  sensor->set_whitebal(sensor, whitebal);
  sensor->set_awb_gain(sensor, whitebal);
  sensor->set_wb_mode(sensor, light);
  if (auto_exposure) {
    sensor->set_exposure_ctrl(sensor, 1);
    sensor->set_aec2(sensor, 1);
    sensor->set_gain_ctrl(sensor, 1);
  } else {
    sensor->set_exposure_ctrl(sensor, 0);
    sensor->set_aec2(sensor, 0);
    sensor->set_gain_ctrl(sensor, 0);
    sensor->set_aec_value(sensor, exposure);
    sensor->set_agc_gain(sensor, gain);
  }
}

static void read_commands() {
  static char line[48];
  static int length = 0;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (length > 0) {
        line[length] = 0;
        apply_command(line);
        length = 0;
      }
    } else if (length < (int)sizeof(line) - 1) {
      line[length++] = c;
    }
  }
}

static uint32_t checksum(const uint8_t *data, size_t len) {
  uint32_t sum = 0;
  for (size_t i = 0; i < len; i++) {
    sum += data[i];
  }
  return sum;
}

static void send_frame() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (fb == nullptr || fb->format != PIXFORMAT_JPEG) {
    if (fb != nullptr) {
      esp_camera_fb_return(fb);
    }
    return;
  }

  uint32_t sum = checksum(fb->buf, fb->len);
  Serial.printf("##FRAME %u %u\n", (unsigned)fb->len, sum);
  Serial.write(fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

void setup() {
  Serial.setTxBufferSize(4096);
  Serial.begin(kBaud);
  delay(300);
  if (!start_camera()) {
    while (true) {
      Serial.println("camera failed");
      delay(1000);
    }
  }
}

void loop() {
  read_commands();
  send_frame();
}
