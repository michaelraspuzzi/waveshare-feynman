/*
 * Wi-Fi: knows several networks (home, phone hotspot...) from secrets.h and joins whichever known
 * one is strongest, retrying in the background. Nothing waits on this: the lecture plays offline,
 * and questions check net_online() first.
 */
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "app.h"
#include "secrets.h"

static const char *TAG = "net";

typedef struct {
    const char *ssid, *pass;
} known_t;

static const known_t known[] = WIFI_NETWORKS;
#define N_KNOWN (sizeof(known) / sizeof(known[0]))

#define GOT_IP BIT0
#define LOST   BIT1

static EventGroupHandle_t ev;
static volatile bool online;
static char current[33];

bool net_online(void) { return online; }
const char *net_name(void) { return online ? current : ""; }

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *e = data;
        if (online) ESP_LOGW(TAG, "lost '%s' (reason %d)", current, e->reason);
        online = false;
        xEventGroupSetBits(ev, LOST);
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *e = data;
        ESP_LOGI(TAG, "on '%s' as " IPSTR, current, IP2STR(&e->ip_info.ip));
        online = true;
        xEventGroupSetBits(ev, GOT_IP);
    }
}

/* Strongest known network in range, or -1. */
static int pick(void)
{
    if (esp_wifi_scan_start(NULL, true) != ESP_OK) return -1;
    uint16_t n = 32;
    wifi_ap_record_t *aps = calloc(n, sizeof(wifi_ap_record_t));
    esp_wifi_scan_get_ap_records(&n, aps);
    int best = -1, best_rssi = -1000;
    for (int i = 0; i < n; i++)
        for (int j = 0; j < (int)N_KNOWN; j++)
            if (!strcmp((char *)aps[i].ssid, known[j].ssid) && aps[i].rssi > best_rssi) {
                best = j;
                best_rssi = aps[i].rssi;
            }
    free(aps);
    if (best >= 0) ESP_LOGI(TAG, "joining '%s' (%d dBm)", known[best].ssid, best_rssi);
    return best;
}

static void net_task(void *arg)
{
    for (;;) {
        int j = pick();
        if (j < 0) {
            ESP_LOGI(TAG, "no known network in range");
            vTaskDelay(pdMS_TO_TICKS(15000));
            continue;
        }
        wifi_config_t wc = {0};
        strlcpy((char *)wc.sta.ssid, known[j].ssid, sizeof(wc.sta.ssid));
        strlcpy((char *)wc.sta.password, known[j].pass, sizeof(wc.sta.password));
        strlcpy(current, known[j].ssid, sizeof(current));
        esp_wifi_set_config(WIFI_IF_STA, &wc);
        xEventGroupClearBits(ev, GOT_IP | LOST);
        esp_wifi_connect();
        EventBits_t b = xEventGroupWaitBits(ev, GOT_IP | LOST, pdTRUE, pdFALSE, pdMS_TO_TICKS(15000));
        if (b & GOT_IP) {
            xEventGroupWaitBits(ev, LOST, pdTRUE, pdFALSE, portMAX_DELAY);   /* stay until we lose it */
        } else {
            esp_wifi_disconnect();
        }
        vTaskDelay(pdMS_TO_TICKS(3000));
    }
}

void net_init(void)
{
    ev = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    esp_event_handler_register(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED, on_event, NULL);
    esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_event, NULL);
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    esp_wifi_set_ps(WIFI_PS_MIN_MODEM);       /* nothing streams anymore: save battery */
    xTaskCreatePinnedToCore(net_task, "net", 4096, NULL, 4, NULL, 0);
}
