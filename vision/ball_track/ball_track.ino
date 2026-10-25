#include <Arduino.h>
#include "esp_camera.h"
#include "board_config.h"

static const int kMinPixels = 80;

// Pale orange
static const int h_min = 5;
static const int h_max = 25;
static const int s_min = 40;
static const int s_max = 255;
static const int v_min = 60;
static const int v_max = 255;

static int center_x = 160;
static int center_y = 120;

// Check if the pixel is in the color range
static bool ball_color(int r, int g, int b) {
  int maxv = r;
  if (g > maxv) maxv = g;
  if (b > maxv) maxv = b;
  int minv = r;
  if (g < minv) minv = g;
  if (b < minv) minv = b;

  int v = maxv;
  int diff = maxv - minv;
  int s = maxv == 0 ? 0 : diff * 255 / maxv;
  int h = 0;
  if (diff > 0) {
    if (maxv == r) {
      h = (g - b) * 30 / diff;
      if (h < 0) h += 180;
    } else if (maxv == g) {
      h = 60 + (b - r) * 30 / diff;
    } else {
      h = 120 + (r - g) * 30 / diff;
    }
  }

  return h >= h_min && h <= h_max && s >= s_min && s <= s_max && v >= v_min && v <= v_max;
}

// Store the pixel in the RGB565 format
static void store_pixel(const uint8_t *p, int *r, int *g, int *b) {
  uint16_t pix = ((uint16_t)p[0] << 8) | p[1];
  *r = ((pix >> 11) & 0x1F) << 3;
  *g = ((pix >> 5) & 0x3F) << 2;
  *b = (pix & 0x1F) << 3;
}

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
  config.pixel_format = PIXFORMAT_RGB565;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.fb_count = 1;

  if (!psramFound() || esp_camera_init(&config) != ESP_OK) {
    return false;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  sensor->set_framesize(sensor, FRAMESIZE_QVGA);
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

void setup() {
  Serial.begin(115200);
  if (!start_camera()) {
    while (true) {
      delay(1000);
    }
  }
}

void loop() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (fb == nullptr) {
    return;
  }

  int32_t sum_x = 0;
  int32_t sum_y = 0;
  int count_pixels = 0;

  const uint8_t *pix = fb->buf;
  for (int y = 0; y < fb->height; y++) {
    for (int x = 0; x < fb->width; x++) {
      int r, g, b;
      store_pixel(pix, &r, &g, &b);
      if (ball_color(r, g, b)) {
        sum_x += x;
        sum_y += y;
        count_pixels++;
      }
      pix += 2;
    }
  }

  if (count_pixels >= kMinPixels) {
    center_x = (int)(sum_x / count_pixels);
    center_y = (int)(sum_y / count_pixels);
  }

  Serial.printf("%d %d %d\n", center_x, center_y, count_pixels);
  esp_camera_fb_return(fb);
}
