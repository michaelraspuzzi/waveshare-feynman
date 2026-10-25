idf_component_register(SRCS "main.c" "player.c" "lecture.c" "ask.c" "net.c"
                       INCLUDE_DIRS "."
                       REQUIRES esp_wifi esp_event esp_netif nvs_flash esp_driver_gpio esp_driver_i2s json
                                esp_partition esp_http_client esp-tls mbedtls esp_rom)
