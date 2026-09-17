"""
Symbol database for LPM-10A TX firmware V2.0.7 (APP_LPM-10A_V2.0.7_260610.bin).

Recovered by static analysis of the stock image; there is no vendor source.
Names marked (?) are inferred from behaviour and may be imprecise -- the
address is what matters, the name is a convenience.

All addresses are absolute flash/RAM addresses as seen by the CPU.
"""

# ---------------------------------------------------------------- platform
MCU = "Nations N32G45x, Cortex-M4F @144MHz"
FLASH_BASE = 0x08000000
APP_BASE = 0x0800A000          # application load address (bootloader occupies 0x08000000+)
APP_END = 0x08067C98           # end of stock payload
FILE_PAYLOAD_OFF = 0x1000      # payload offset inside the .bin container
SECTOR = 0x800                 # 2 KB flash erase sector

RAM_BASE = 0x20000000
RAM_ZI_END = 0x2000E888        # end of ZI == initial MSP; nothing above is used by stock
RAM_SAFE_ARENA = 0x2000F000    # SDK scratch RAM (above stack, NOT zero-initialised)
RAM_SAFE_ARENA_END = 0x20010000

HEAP_BASE = 0x20001028
HEAP_SIZE = 0xC000             # 48 KB, FreeRTOS heap_4

# ---------------------------------------------------------------- functions
FUNCS = {
    # --- C runtime / startup -------------------------------------------------
    0x0800A199: "__main",
    0x0800A1A0: "__scatterload",
    0x0800A1D4: "__decompress2",          # Keil RW-data LZ77 decompressor
    0x0800A34C: "Reset_Handler",
    0x080182A4: "SystemInit",
    0x08018120: "SetSysClock",
    0x0801BBAC: "main",

    # --- libc ----------------------------------------------------------------
    0x0800A3B8: "snprintf",
    0x0800A38C: "sprintf",
    0x0800A698: "memcmp",
    0x0800A72E: "memcpy",
    0x0800A7B8: "memcpy2",                # (?) second memcpy variant
    0x0800A82C: "memclr",
    0x0800A870: "memset",

    # --- FreeRTOS kernel -----------------------------------------------------
    0x0800A28C: "SVC_Handler",
    0x0800A2E8: "PendSV_Handler",
    0x08018298: "SysTick_Handler",
    0x0801C5B0: "xTaskGetTickCount",      # returns g_ms_ticks (0x200001A0)
    0x0801C6B4: "vPortEnterCritical",
    0x0801C6D8: "vPortExitCritical",
    0x0801C844: "vTaskSuspendAll",
    0x0801D01C: "xTaskResumeAll",
    0x0801C854: "vTaskSwitchContext",
    0x0801CD84: "xTaskIncrementTick",
    0x0801C75C: "vTaskDelay",
    0x0801C7D4: "vTaskStartScheduler",
    0x0801CD1C: "xTaskCreate",
    0x0801C9B4: "xQueueGenericCreate",
    0x0801CAA0: "xQueueGenericSend",
    0x0801CBB8: "xQueueReceive",
    0x0801C388: "pvPortMalloc",
    0x0801C6F8: "vPortFree",
    0x0801C084: "prvHeapInit",
    0x0801C0F4: "prvIdleTask",

    # --- fault handlers (all bare while(1) in stock) -------------------------
    0x08017DAC: "NMI_Handler",
    0x08016994: "HardFault_Handler",
    0x08017DA8: "MemManage_Handler",
    0x08014C3E: "BusFault_Handler",
    0x08018A02: "UsageFault_Handler",
    0x080154FE: "DebugMon_Handler",
    0x08018370: "TIM2_IRQHandler",        # ~20 kHz; feeds IWDG, drives SCAN tone

    # --- tasks ---------------------------------------------------------------
    0x0800C2C4: "APP_CNT_task",
    0x08012D4C: "APP_LOG_task",
    0x080147F0: "APP_net_task",           # Length / Speed / Flash engine
    0x0800DC5C: "APP_Flash_task",
    0x08013F64: "APP_POE_task",
    0x0800CECC: "APP_COUNT_task",
    0x0800F454: "APP_GUI_task",
    0x0800F8C8: "APP_HOME_task",
    0x08015DE8: "HAL_KEY_task",
    0x080155B0: "Event_key_task",

    # --- task creation helpers ----------------------------------------------
    0x0800BEFC: "APP_CNT_task_init",
    0x08012CF0: "APP_LOG_task_init",
    0x080130E8: "APP_net_Flash_task_init",
    0x08013F20: "APP_POE_task_init",
    0x08015260: "APP_COUNT_task_init",
    0x08015CD4: "APP_GUI_task_init",
    0x08016950: "APP_HOME_task_init",
    0x080169D0: "KEY_tasks_init",

    # --- message senders (queue producers) -----------------------------------
    0x0800E428: "GUI_MSG_SEND",           # (event, payload, len) drop-oldest on full
    0x08010EA8: "HOME_MSG_SEND",
    0x0800BCE8: "CNT_MSG_SEND",
    0x08012FBC: "LENG_MSG_SEND",
    0x08013DCC: "POE_MSG_SEND",
    0x08012C64: "log_queue_ptr",

    # --- system state --------------------------------------------------------
    0x0800F764: "get_sysState",           # (0)->state, (1)->1<<state
    0x0800F75C: "get_sysState_ptr",
    0x0800F77C: "APP_HOME_set_sysState",
    0x0801BC70: "tick_hook_1ms",          # called from SysTick_Handler
    0x0800F968: "home_1s_housekeeping",   # auto-off countdown
    0x0800F9C0: "autooff_timer_reset",    # auto_off_ctr = 0
    0x0800F9CC: "backlight_dim_update",
    0x080116BC: "key_activity_notify",    # runs on every key action
    0x080130A8: "test_in_progress",       # 1 while a measurement is running

    # --- power / battery -----------------------------------------------------
    0x08016604: "power_off",              # (reason) 1=key 2=auto 3=battery
    0x08016768: "power_on_or_charge",
    0x0800DD34: "battery_tick",           # called from tick_hook_1ms (ISR context!)
    0x0800E6B0: "battery_ui_update",      # arms low-battery shutdown
    0x0800E40C: "battery_shutdown_active",
    0x0800E834: "battery_show_warning",
    0x080107B4: "adc_raw_read",
    0x080108F8: "battery_millivolts",     # mV = raw*2*3300>>12
    0x080107C0: "battery_level_percent",
    0x08010918: "charger_state",          # bit0 = CHRG, bit4 = STDBY

    # --- settings / flash storage -------------------------------------------
    0x0800FD44: "APP_Home_Cust_Info_Init",
    0x0800FF74: "APP_Home_Cust_Info_Storage",
    0x0800FA88: "APP_Home_BootFlag_Storage",
    0x0800FC70: "APP_Home_Check_BootFlag",
    0x080155EC: "flash_erase_page",
    0x080156A4: "flash_program",
    0x08015690: "flash_lock",
    0x080156FC: "flash_unlock",

    # --- keys ----------------------------------------------------------------
    0x080149FC: "Action_key_Process",
    0x0800D2B4: "key_action_dispatch",

    # --- measurement: length / speed ----------------------------------------
    0x080119EC: "APP_LENG_Test_Sequence", # YT8531 CSD (TDR) length measurement
    0x0800D47C: "LENG_link_test",         # speed / duplex
    0x0800DB8C: "LENG_flash",             # port-blink locate
    0x0801A9A8: "LENG_speed_result",      # decodes PHY reg 0x11: [15:14] speed, [13] duplex
    0x08015D18: "length_tolerance_cm",    # <10m:100 <100m:300 <200m:500 else 600
    0x08014BE4: "sort_u16_array",         # bubble sort, DESCENDING
    0x0801573A: "u16_max_min_spread",     # (arr, n, &max, &min) -> max-min
    0x08019774: "length_convert",         # cm -> display units (unit idx at 0x200002C0)
    0x080199B0: "length_result_draw",     # "%s = %d" + unit label, 4 rows
    0x080197EC: "length_unit_picker_draw",

    # --- measurement: PoE ----------------------------------------------------
    0x08019CDC: "poe_measure_mv",         # mV = (max-min ADC) * 3300 * 40 / 4096
    0x08019D20: "poe_read_4ch",           # 4 ADC channels -> 0x200000B4
    0x08019D40: "poe_class_detect",       # PB6/PB7 comparators -> class 3/4/6/8
    0x08019E10: "app_poe_set_standar",
    0x08019F00: "poe_state_machine",
    0x08014CA0: "CheckPoESpan",           # end/mid span + polarity, empirical 0.7/0.9 ratios
    0x08014C42: "poe_ring_is_stable",     # DEAD: byte data vs 40000 threshold, always 1

    # --- measurement: wiremap / continuity ----------------------------------
    0x0800BF40: "CNT_run_test",
    0x08018060: "cnt_select_wire",        # 4-bit mux on PE1/PE2/PE3/PC3
    0x08018B84: "cnt_measure_pulses",
    0x08018BA4: "abs_diff_u16",
    0x08018BB8: "cnt_hw_init",
    0x08018C28: "cnt_is_calibrated",

    # --- PHY (Motorcomm YT8531 over bit-banged MDIO) ------------------------
    0x08017AFC: "mdio_write",
    0x080178F0: "mdio_read",
    0x08018A9E: "phy_ext_write",          # via regs 0x1E/0x1F
    0x08018A80: "phy_ext_read",
    0x0801BD94: "phy_bit_write",
    0x0801D178: "yt8531_set_pwr_down",
    0x0801D2B4: "yt8531_set_1000M",
    0x0801D3F4: "yt8531_set_100M",
    0x0801D534: "yt8531_set_autoneg",
    0x0801BAAC: "mdio_gpio_init",

    # --- watchdog ------------------------------------------------------------
    0x08016998: "iwdg_start",
    0x080169A8: "iwdg_feed",
    0x080169B8: "iwdg_set_prescaler",     # writes IWDG+0x04 (PR), not RLR; init sets 3 = /32
    0x080169C4: "iwdg_write_key",
    0x0801B17E: "iwdg_init",              # PR=/32, RLR left at 0xFFF -> ~3.3 s timeout

    # --- misc hardware -------------------------------------------------------
    0x08015AF2: "GPIO_ReadInputDataBit",
    0x08015D46: "GPIO_WriteBit",
    0x08012C6C: "debug_uart_init",        # USART1 PA9, 1 Mbaud, TX only
    0x080189C4: "nvic_setup",
    0x08017DB0: "NVIC_Init",

    # --- GUI primitives ------------------------------------------------------
    0x0800EF6C: "gui_draw_text_box",   # async: posts GUI msg 0x38; size 0x0C/0x10 = 6x12/8x16,
                                       # 0x20 = 8x16 centred, 0x40 = CJK index string, 0x50 = mixed
    0x0800E37C: "gui_draw_rect",
    0x08016C18: "gui_draw_line",
    0x08016D08: "gui_draw_shape",
    0x080174E8: "gui_blit",            # draw ASCII string (x, y, w, h, [sp]=size, [sp+4]=str)
    0x080171D4: "gui_draw_ascii_glyph", # (x, y, ch, size, transparent): 6x12 / 8x16 column-major
    0x08017550: "gui_draw_cjk_glyph",  # (x, y, index, transparent): 16x16, u16 columns LSB=top
    0x080176AC: "gui_draw_cjk_string", # bytes = glyph indices, terminator >= 0xAB
    0x080173EC: "gui_draw_mixed_string", # u16 per glyph: 0x0020..0x007E ASCII, else low byte = index
    0x08016BF0: "lcd_put_pixel",       # (x, y) in colour 0x200001AC
    0x08016A44: "lcd_fill_screen",     # (colour); screen is cleared to 0x0000
    0x0800DEA8: "gui_draw_wire",

    # --- settings / Length screen glue -----------------------------------------
    0x08011174: "settings_cursor_move",    # (dir) item 1..5 at sysState+2
    0x080111D0: "settings_value_edit",     # (action 30/31/32) per-item tbb
    0x080101F0: "settings_item_draw",      # GUI msg 0x33; 5 tiles, y = 68/124/175/220/263
    0x08012EE4: "leng_enter_state",        # 0x08012F1C: unit index reset on Length entry
    0x08012E94: "leng_unit_change",        # LEFT/RIGHT on the Length screen
}

# ---------------------------------------------------------------- variables
VARS = {
    0x20000000: ("cnt_task_handle", 4),
    0x20000004: ("cnt_queue", 4),
    0x20000008: ("count_task_handle", 4),
    0x2000000C: ("count_queue", 4),
    0x20000014: ("menu_name_table", 4 * 8),   # -> "Cable Test","SCAN",... strings
    0x20000034: ("gui_task_handle", 4),
    0x20000038: ("gui_queue", 4),
    0x2000003C: ("blink_phase", 1),
    0x2000003D: ("batt_shutdown_ctr", 1),     # 0xFF = idle, else seconds remaining
    0x2000003F: ("batt_level_pct", 1),
    0x20000040: ("hal_key_task_handle", 4),
    0x20000044: ("event_key_task_handle", 4),
    0x20000048: ("key_queue", 4),
    0x20000068: ("net_task_handle", 4),
    0x20000070: ("net_queue", 4),
    0x20000076: ("leng_led_phase", 1),
    0x200000AC: ("poe_task_handle", 4),
    0x200000B0: ("poe_queue", 4),
    0x200000D0: ("scan_state", 4),
    0x200000D8: ("scan_tick", 4),
    0x2000013C: ("sysState", 1),              # 0=off 2=home 4..11=function screens
    0x20000140: ("home_task_handle", 4),
    0x20000144: ("home_queue", 4),
    0x20000150: ("dim_last_activity_ms", 4),  # +4 = dim_active flag
    0x20000158: ("backlight_level", 2),
    0x20000178: ("auto_off_ctr", 2),          # seconds of idle; compared to table
    0x2000017A: ("backlight_enable", 1),
    0x2000017B: ("batt_level_shown", 1),
    0x2000017C: ("batt_level_cand", 1),
    0x2000017D: ("batt_level_debounce", 1),
    0x20000180: ("log_task_handle", 4),
    0x20000184: ("log_queue", 4),
    0x20000188: ("log_slot_idx", 1),          # round-robin over 8 slots
    0x200001A0: ("g_ms_ticks", 4),            # incremented by tick_hook_1ms
    0x200001A4: ("tim2_ms_acc", 4),
    0x200001A8: ("tim2_div5", 1),
    0x200001B4: ("pxCurrentTCB", 4),
    0x200001F4: ("xStart_heap_list", 8),
    0x200001FC: ("pxEnd_heap", 4),
    0x20000200: ("xFreeBytesRemaining", 4),
    0x2000020C: ("xNumberOfSuccessfulFrees", 4),
    0x2000021C: ("cnt_baseline", 0x24),       # wiremap open-circuit reference
    0x200002B4: ("test_busy_flags", 2),       # [0]=flash busy [1]=leng/speed busy
    0x200002B6: ("phy_status_reg11", 2),      # last PHY reg 0x11 read (speed/duplex)
    0x200002B8: ("leng_last_result_cm", 8),   # 4 channels
    0x200002C0: ("leng_unit_idx", 1),         # index into unit table at 0x2000005C (ZI -> 0 at boot)
    0x2000004C: ("pair_name_table", 4 * 4),   # -> "1-2","3-6","4-5","7-8"
    0x2000005C: ("unit_name_table", 4 * 3),   # -> "Inch","Cent","Meter" (stock)
    0x200000B4: ("poe_adc_ch", 2 * 4),        # 4 PoE ADC channels
    0x200000C0: ("poe_mv", 2),
    0x20000C78: ("g_settings", 0xC8),         # mirror of flash page 0x0807F800
    0x20000D6C: ("log_slots", 8 * 61),
    0x20001028: ("ucHeap", 0xC000),
}

# settings struct fields (offsets into g_settings / flash page).  The whole
# 0xC8-byte struct is written to flash at power-off (power_off -> storage).
SETTINGS = {
    0x30: ("cal_double_a[6]", 48, "written by the defaults writer"),
    0x60: ("cal_double_b[6]", 48, "written by the defaults writer"),
    0x90: ("cnt_init_data", 16, "APP_Home_Storage_CntInitData"),
    0xA0: ("magic", 2, "must be 0x9718"),
    0xA2: ("auto_off_idx", 1, "0=OFF 1=5min 2=10min 3=15min"),
    0xA3: ("backlight", 1, "1..10"),
    0xA4: ("volume", 1, "0..10"),
    0xA5: ("language", 1, "1=Chinese 2=English"),
    0xA6: ("nvp_pct", 1, "MOD: 50..99, 0 = factory (69 %); stock zeroes it and never reads it"),
    0xA7: ("leng_unit", 1, "MOD: 0=m 1=cm 2=ft; stock zeroes it and never reads it"),
    0xA8: ("first_boot_flag", 1, "1 = show the language picker"),
    0xA9: ("net_cfg", 0x1C, "copied from 0x080131B4()"),
}

# ---------------------------------------------------------------- constants
CONSTS = {
    "SETTINGS_PAGE": 0x0807F800,
    "BOOTFLAG_PAGE": 0x0807F000,
    "SETTINGS_MAGIC": 0x9718,
    "BATT_LOW_MV": 3150,                 # arms shutdown countdown
    "BATT_SHUTDOWN_SECONDS": 30,
    "AUTO_OFF_TABLE": 0x08064D72,        # u16[4] = {0,300,600,900} seconds
    "BATT_LEVEL_TABLE": 0x08064D7A,      # u16[3] = {4000,3800,3600} mV
    "KEY_BINDING_TABLE": 0x0801E4DC,     # 37 x {u32 state_mask, u8 key, u8 evt, u8 action}
    "LENG_TIMEOUT_MS": 20000,
    "FONT_ASCII12": 0x08065904,          # 95 x 12 bytes, 6x12
    "FONT_ASCII16": 0x08065D78,          # 95 x 16 bytes, 8x16
    "FONT_CJK16": 0x08066368,            # 171 x 32 bytes, 16x16 (see cjk_chars.py)
    "LAYOUT_TABLE": 0x0801E604,          # 14-byte {x,y,w,h,c1,c2,style,pad} records
    "GUI_MSG_NVP_REDRAW": 0x3D,          # MOD: added by nvp-calibration
}

# sysState values
STATES = {
    0: "OFF", 1: "BOOT", 2: "HOME", 3: "LANGUAGE_SELECT",
    4: "CABLE_TEST", 5: "SCAN", 6: "SPEED", 7: "LENGTH",
    8: "FLASH", 9: "QC_TEST", 10: "POE", 11: "SETTING",
}

# keys as seen by Action_key_Process
KEYS = {1: "LEFT", 2: "UP", 3: "DOWN", 4: "OK/M", 5: "RIGHT"}
KEY_EVENTS = {3: "click", 6: "long_press", 8: "ll_press", 12: "repeat"}


def asm_symbols():
    """Flat name->address map for use as assembler symbols."""
    out = {}
    for a, n in FUNCS.items():
        out[n] = a | 1          # Thumb bit set: ready for bl/blx
        out[n + "_addr"] = a
    for a, (n, _) in VARS.items():
        out[n] = a
    out.update(CONSTS)
    out["RAM_ARENA"] = RAM_SAFE_ARENA
    return out
