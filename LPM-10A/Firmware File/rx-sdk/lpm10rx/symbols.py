"""
Symbol database for the LPM-10A receiver (probe) firmware
APP_LPM-10RX_V3.0.0_260416.bin.

Recovered by static analysis and by booting the image under CPU emulation
(see boot_emu.py); there is no vendor source.  Names marked (?) are
inferred from behaviour.  All addresses are absolute flash / RAM addresses
as the CPU sees them.

The receiver is a very different animal from the transmitter:

  * raw Cortex-M image, no container header, loaded at 0x08006800 above a
    bootloader; VTOR is set to the image base by SystemInit.  The last
    bootloader page (0x08006000) holds a 24-byte licence block at 0x08006700
    that binds the unit to its chip UID, and the tag "_V3." at 0x0800676C.
  * Nations N32L40x class: Cortex-M4F, 16 MHz HSI, MSI, ADC on the AHB bus
    at 0x40020800.  SystemInit and rcc_init both end at 64 MHz (HSI x PLL 4),
    APB1 = APB2 = 32 MHz, timer clocks 64 MHz (an APB prescaler of /2
    doubles the timer clock, as the Nations SDK's own TIM examples state).
  * ARM Compiler (Keil MDK) at -O0: every other instruction is a `b .+2`;
    addresses are built with movw/movt, so there are almost no literal
    pools; the C library is ARM's (__aeabi_*, scatter-loading).
  * no RTOS: two timer interrupts and a main-loop state machine
"""

MCU = "Nations N32L40x class, Cortex-M4F @ 64 MHz (HSI 16 MHz x PLL 4)"
FLASH_BASE = 0x08000000
APP_BASE = 0x08006800           # image load address; the bootloader lives below
LICENCE_BLOCK = 0x08006700      # 24-byte UID-binding record + "_V3." tag at 0x0800676C (bootloader page)
APP_SIZE = 26152                # stock image size (0x6628)
APP_END = APP_BASE + APP_SIZE
EXTEND_LIMIT = 0x0801E000       # appended code may grow the image up to here (version page 0x0801F000 stays clear)
VERSION_PAGE = 0x0801F000       # holds the version string "3.0.0"; rewritten by main when it differs (no settings live there)
RAM_BASE = 0x20000000
STACK_TOP = 0x20001618          # initial MSP from the vector table

STOCK_SHA256 = "083f3825e8f8a38627417e26732e88fd13ee0dbe3c13ca1cd1cd9c4875c7c8c5"

# ---------------------------------------------------------------- functions
FUNCS = {
    # --- startup ---------------------------------------------------------------
    0x08006948: "__main",                 # sets sp, bl 0x08006DDC (data/bss init), bx main
    0x0800695C: "Reset_Handler",          # ldr SystemInit / blx; ldr __main / bx
    0x08006976: "Default_Handler",        # b . (vectors 16..81)
    0x08006DDC: "__scatterload",          # ARM scatter-loading: walks the region table at 0x0800CDEC
    0x0800CA30: "__scatterload_copy",     # .data copy (0x0800CE10 -> 0x20000000, 0x18 bytes)
    0x0800CA40: "__scatterload_zeroinit", # .bss clear (0x20000018, 0x1600 bytes)
    0x0800A7D8: "SystemInit",             # FPU on (CPACR), RCC reset, SetSysClock, VTOR = 0x08006800
    0x0800A0A8: "SetSysClock",            # HSI/2 x 8 = 64 MHz; APB1 /4, APB2 /2 (rcc_init redoes it: HSI x 4, APB /2 /2)
    0x0800B70C: "main",

    # --- interrupts --------------------------------------------------------------
    0x0800A97C: "TIM1_UP_IRQHandler",     # 1 ms tick: keys every 5 ms, battery every 500 ms, countdowns, auto-off 300000 ticks = 5 min
    0x0800AC1C: "TIM5_IRQHandler",        # 40 kHz (25 us): ADC sampling per mode; speaker duty flip every 8 ticks (2.5 kHz tone)
    0x080081F4: "HardFault_Handler",      # IWDG reload then loop (?)
    0x08008714: "NMI_Handler",
    0x08009DB0: "SVC_Handler",            # stub
    0x0800A600: "SysTick_Handler",        # stub

    # --- timers ------------------------------------------------------------------
    0x0800A908: "tim1_init",              # period 64000, prescaler 0 at 64 MHz -> 1 kHz
    0x0800AB74: "tim5_init",              # period 1600, prescaler 0 at 64 MHz -> 40 kHz; CH4 PWM = speaker (a prescaler is computed from SystemCoreClock and never used)
    0x0800B364: "speaker_pwm_set",        # (duty) -> TIM5 CCR4; 800 = silent, 900/700 alternating = tone
    0x08007508: "speaker_tick",           # (keep_alive) called every 0.2 ms: flips duty 900/700 while beeping = 2.5 kHz
    0x08007724: "speaker_tick_mode0",     # mode 0: 50 ms beeps with 50 ms gaps while signal_recent > 0
    0x0800AF08: "tim_get_it_status",      # (TIMx, flag)
    0x0800ADC0: "tim_clear_it",           # (TIMx)
    0x0800B9A0: "delay_ms",               # SysTick busy loop
    0x0800BA48: "delay_us",               # (?) SysTick busy loop

    # --- sampling / detection ----------------------------------------------------
    0x080072A4: "adc_read_channel",       # (ADC, ch) -> u16  (calls 6FC0/7020/7224/7294)
    0x08007320: "adc_read_n",             # (ch, buf) -> 5 samples
    0x0800B630: "trimmed_mean",           # (buf, n) -> (sum - min - max) / (n - 2) for n >= 3
    0x080075F8: "sampler_modes_0_1",      # mode 0: called every 20 ticks (0.5 ms); reads at sub-steps 6..10 (3.0..5.0 ms) -> trimmed mean of five = one sample per 5 ms, 48 samples = 240 ms
                                          # mode 1: one reading per 13 ticks (0.325 ms), 64 samples = 20.8 ms
    0x08009E08: "analyse_mode0",          # threshold + exact 16-bit match against 0xB6B6, >= 2 of 3 periods
    0x08009F58: "analyse_mode1",          # 32-bin DFT; bin 17 (817 Hz = the TX's ~825 Hz second cadence) against the floor of the rest -> 3 levels; stronger = shorter beep (50/100/200 ms) = faster repeat
    0x080085F4: "analyse_mode2",          # DFT bins 5 and 6 of 64 samples at 1.55 ms (fs 645 Hz) = 50.4 / 60.5 Hz: mains detection on ADC ch 7 -> 3 levels
    0x0800B4A0: "dft_bin_magnitude",      # (k) over the 64-sample buffer
    0x0800B5F0: "dft_cos_table",          # (?)
    0x0800B5B0: "dft_sin_table",          # (?)

    # --- keys / power / battery --------------------------------------------------
    0x080082B8: "key_scan",               # every 10 ms; PC15 mode 0<->1, PD15 mode 2, PD14 lamp; 6-scan debounce
    0x08007770: "battery_500ms",          # every 500 ms: trimmed mean of 5, mV = raw*6600/4096, LED hysteresis, critical -> power off
    0x08007570: "power_off",              # PA10 high, PA8 low, PB15 low, PB8 high (PB8 high releases the power latch)
    0x080084D8: "agc_update_500ms",       # (?) every 500 ms: ADC ch 3 trimmed mean -> mode0_gate / mode1_gate (= level/580), then gain_select_3bit
    0x0800A4FC: "gain_select_3bit",       # (?) writes a 3-bit code (level/580, 0..7) to PB12..PB14: AGC gain select or level LEDs

    # --- GPIO helpers ------------------------------------------------------------
    0x08008108: "gpio_read_pin",          # (GPIOx, pin) -> 0/1
    0x08008170: "gpio_set_pin",           # (GPIOx, pin)
    0x08008184: "gpio_reset_pin",         # (GPIOx, pin)
    0x08008198: "gpio_toggle_pin",        # (GPIOx, pin)
    0x080081C8: "gpio_write_pin",         # (GPIOx, pin, level)

    # --- flash (settings page 0x0801F000) ------------------------------------------
    0x080079BC: "flash_unlock",
    0x080079D8: "flash_erase_page",       # -> 6 = complete
    0x08007A44: "flash_wait_busy",
    0x08007AE4: "flash_lock",
    0x08007AF8: "flash_program_word",     # -> 6 = complete
    0x08007BA8: "flash_set_latency",      # (?)
    0x0800B924: "version_page_write",     # (words, n) -> page 0x0801F000
    0x0800B388: "version_page_check",     # once from main: if page 0x0801F000 != "3.0.0" (0x0800CDE4), erase and rewrite it; no settings are stored

    # --- recovered by the naming pass (2026-09-17); (?) = low confidence; see docs/RX-AUDIT.md ---
    0x08006950: "main_after_scatterload",  # ARM C library (Keil/armlink, MicroLib) __main_after_scatterload: 'ldr r0, =main; bx r0'
    0x08006972: "PendSV_Handler",          # Weak default handler stub from the Keil startup file: a single 'b .' (0xE7FE)
    0x08006980: "strlen",                  # C library strlen: byte loop until NUL, returns pointer difference
    0x0800698E: "memcmp",                  # Byte-wise memcmp(a, b, n): returns 0 if all n bytes match, otherwise a[i] - b[i] at the
    0x080069A8: "__aeabi_dadd",            # Soft-float IEEE double addition (a+b, args in r0:r1 / r2:r3, result r0:r1)
    0x08006BDA: "__aeabi_ddiv",            # ARM RT-ABI double-precision floating-point divide (r0:r1 / r2:r3), soft-float runtime li
    0x08006CE6: "__ieee754_sqrt",          # Soft-float double square-root core (bit-serial restoring algorithm over 53 bits)
    0x08006D88: "__aeabi_i2d",             # ARM Compiler fplib int32 -> double conversion: computes |x| and the sign bit, then hands
    0x08006E00: "__aeabi_llsl",            # ARM RT-ABI 64-bit logical shift left: (r0:r1) << r2; for shifts >= 32 the low word moves
    0x08006E1E: "__aeabi_llsr",            # Compiler runtime helper: 64-bit unsigned logical shift right, (r1:r0) >> r2
    0x08006E3E: "aeabi_lasr",              # ARM Compiler runtime __aeabi_lasr (a.k.a
    0x08006E80: "softfloat_pack_double",   # Internal soft-float helper (library routine, not SDK): normalises, rounds and packs an I
    0x08006F1C: "memcpy",                  # ARM C library __aeabi_memcpy/memcpy(dst, src, n): word-copy loop (ldm/stm) when both poi
    0x08006F40: "__aeabi_memset",          # ARM EABI runtime helper __aeabi_memset(void* dest, size_t n, int c): r2 = (uint8_t)c, th
    0x08006F4E: "__aeabi_memclr",          # ARM RT-ABI __aeabi_memclr(dst, n): sets r2 = 0 and falls into __aeabi_memset at 0x08006F
    0x08006F64: "__aeabi_d2iz",            # Library soft-float routine: double (r0:r1) to signed 32-bit integer with truncation towa
    0x08006FA4: "adc_config_clk_ahb",      # Nations SDK ADC_ConfigClk(ADC1, ADC_CTRL3_CKMOD_AHB) with the arguments folded: ADC1->CT
    0x08006FC0: "adc_clear_flag",          # Nations SDK ADC_ClearFlag(ADCx, flag): writes (0x7F & ~flag) to ADCx->STS (offset 0x00,
    0x08006FDC: "adc_clock_config",        # ADC clock selection, the Nations SDK ADC_ConfigClk(ADC_CTRL3_CKMOD_AHB, RCC_ADCHCLK_DIV1
    0x08007020: "adc_config_regular_channel", # Nations SDK ADC_ConfigRegularChannel(ADCx, channel) with Rank=1 and SampleTime=7 (239.5
    0x080071D8: "adc_enable",              # (ADC_Module *adc) Sets AD_ON (bit 0) in ADCx->CTRL2 (+0x08); the ENABLE argument is a ha
    0x08007224: "adc_software_start_conv", # SDK ADC_EnableSoftwareStartConv(ADCx, ENABLE) with the Cmd argument folded to ENABLE: AD
    0x08007254: "adc_get_calibration_status", # SDK ADC_GetCalibrationStatus(ADCx) (Nations n32x_adc.c): returns SET (1) while the CAL b
    0x08007294: "adc_get_data",            # SDK ADC_GetDat / ADC_GetConversionValue(ADCx): returns the low 16 bits of the ADC regula
    0x080072E8: "adc_get_ready_flag",      # (ADCx) -> 0/1
    0x08007378: "adc_init",                # Nations SDK ADC_Init(ADC_Module* ADCx, ADC_InitType* init)
    0x0800742C: "adc_init_struct",         # Nations ADC_InitStruct(ADC_InitType*): resets the ADC init structure (single channel, si
    0x0800744C: "adc1_init",               # Application ADC1 bring-up
    0x080074B0: "adc1_clk_mode_pll",       # Nations SDK ADC_ConfigClk(ADCx, ADC_CTRL3_CKMOD) specialised to ADC1 and the PLL mode: A
    0x080074CC: "adc_start_calibration",   # SDK ADC_StartCalibration(ADCx) (Nations n32x_adc.c): if ADC_CALFACT is zero, sets the CA
    0x080075B8: "power_on_latch",         # PB8 low (holds the power latch), PA8 high (mode-0 LED, toggled at 0.5 Hz by TIM1), PA15 high (low-batt LED off), PB15 low
    0x080078C4: "BusFault_Handler",       # vector 5: `b .+2 ; b .` trap stub, like MemManage/UsageFault
    0x080078C8: "pwr_regulator_mode_switch", # Power-regulator (LDO/core-voltage range) switch executed with interrupts masked (mrs pri
    0x080079B8: "DebugMon_Handler",        # Empty debug-monitor exception handler (single bx lr)
    0x08007B7C: "flash_set_latency_2",     # (u32 latency) FLASH->AC (0x40022000) = (AC & 0xF8) | latency: sets LATENCY[2:0], keeps b
    0x08007BC8: "flash_wait_for_last_operation", # (timeout) -> status
    0x08007C20: "bootinfo_version_tag_missing", # Returns 0 when the byte at 0x0800676E equals 0x33 ('3'), i.e
    0x08007C50: "board_gpio_init",         # Board-level GPIO setup called once from main
    0x08007D60: "gpio_init",               # Nations SDK GPIO_InitPeripheral(GPIOx, GPIO_InitType*)
    0x080080E0: "gpio_init_struct",        # Nations GPIO_InitStruct(GPIO_InitType*): fills the init structure with defaults (all pin
    0x0800813C: "gpio_read_output_pin",    # SPL GPIO_ReadOutputDataBit(GPIOx, pin): returns 1 if the pin's bit is set in the output
    0x080081F8: "iwdg_set_reload_max",     # Nations SDK IWDG_CntReload(Reload) with the argument folded to 0xFFF: writes IWDG->RELV
    0x08008214: "iwdg_enable",             # IWDG_Enable(): writes the start key 0xCCCC to IWDG->KEY (0x40003000)
    0x08008224: "iwdg_reload",             # Independent watchdog kick: writes the reload key 0xAAAA to IWDG->KEY (0x40003000)
    0x08008234: "iwdg_set_prescaler_32",   # SDK IWDG_SetPrescaler / IWDG_SetPrescalerDiv with the argument hard-coded to 3 (= /32):
    0x08008250: "iwdg_write_access_enable", # SDK IWDG_WriteAccessCmd(IWDG_WriteAccess_Enable) / IWDG_WriteConfig with the key hard-co
    0x0800826C: "gpio_init_leds_pa15_pb4", # Board helper: GPIO_InitStruct() defaults, RCC_EnableAPB2PeriphClk(0xC = GPIOA|GPIOB, ENA
    0x08008478: "rcc_config_lse_trim",     # (u16 trim) Writes a 9-bit trim value into bits 8:0 of 0x40001808 (APB1+0x1800 = Nations
    0x08008524: "bootinfo_page_write",     # (u32 *words) Rewrites the shared boot-info block in the last bootloader flash page: FLAS
    0x080085C8: "MemManage_Handler",       # Four-byte trap: a `b .+2` no-op followed by `b .` (while(1))
    0x080085CC: "gpio_init_pa6_analog",    # Board helper: GPIO_InitStruct() defaults, then GPIO_InitPeripheral(GPIOA, {Pin=0x40 (PA6
    0x08008718: "nvic_init",               # STM32 std-periph NVIC_Init(NVIC_InitType*) from misc.c: struct = {u8 IRQChannel, u8 Pree
    0x080087C8: "nvic_set_vector_table",   # SPL NVIC_SetVectorTable(NVIC_VectTab_FLASH, 0x6800) with both args as locals: SCB->VTOR
    0x080087F4: "rcc_config_adc_1m_clk",   # Nations RCC_ConfigAdc1mClk(src, prescaler) with src=0 (HSI) and prescaler=0x1000 (ADC1MP
    0x08008838: "rcc_config_adc_hclk",     # Nations SDK RCC_ConfigAdcHclk(RCC_ADCHCLK_DIVx): RCC_CFG2 (0x4002102C) = (CFG2 & ~0xF) |
    0x08008864: "rcc_config_adc_pll_clk",  # Nations RCC_ConfigAdcPllClk(prescaler, Cmd): sets the ADC PLL-clock prescaler field ADCP
    0x080088B8: "rcc_hclk_config_div1",    # SDK RCC_ConfigHclk / RCC_HCLKConfig with the argument hard-coded to RCC_SYSCLK_DIV1: cle
    0x080088E4: "rcc_config_hse_disable",  # Nations SDK RCC_ConfigHse(RCC_HSE) with the argument folded to the constant 0 (RCC_HSE_D
    0x08008940: "rcc_hsi_enable",          # Enables the 16 MHz HSI oscillator: RCC->CTRL (0x40021000) bit 0 (HSIEN) is cleared and,
    0x08008978: "rcc_lse_config_disable",  # Specialised copy of the Nations/ST SDK RCC_ConfigLse() with the mode argument folded to
    0x08008A2C: "rcc_msi_config",          # Configures the MSI (multi-speed internal RC) oscillator: RCC->CTRLSTS (0x40021024) bits
    0x08008A84: "rcc_pclk1_config",        # STM32-style RCC_PCLK1Config / Nations RCC_ConfigPclk1(RCC_HCLK_DIVx): read-modify-write
    0x08008AB0: "rcc_pclk2_config",        # STM32-style RCC_PCLK2Config / Nations RCC_ConfigPclk2(RCC_HCLK_DIVx): read-modify-write
    0x08008AE0: "rcc_config_pll",          # Nations SDK RCC_ConfigPll(PLLSource, PLLMul, PLLPre)
    0x08008B74: "rcc_config_sysclk",       # Nations SDK RCC_ConfigSysclk(src): RCC->CFG (0x40021004) bits 1:0 (SCLKSW) = src, other
    0x08008BA0: "rcc_init",                # Board clock initialisation, called once from main before GPIO init
    0x08008BF0: "rcc_ahb_adc_clock_enable", # RCC_EnableAHBPeriphClk(RCC_AHB_PERIPH_ADC, ENABLE) with both arguments baked in: RCC->AH
    0x08008C30: "rcc_apb1_periph_clock_cmd", # SPL RCC_EnableAPB1PeriphClk(periph, ENABLE): ORs the mask into RCC APB1PCLKEN (the disab
    0x08008C6C: "rcc_apb1_periph_reset_all", # Nations SDK RCC_EnableAPB1PeriphReset(periph, Cmd) with periph folded to 0xFFFFFFFF; the
    0x08008CAC: "rcc_apb2_periph_clock_enable", # Nations/ST SDK RCC_EnableAPB2PeriphClk(mask, Cmd) with Cmd constant-folded to ENABLE (th
    0x08008CE8: "rcc_apb2_periph_reset_all", # (cmd): SDK RCC_APB2PeriphResetCmd() with the peripheral mask folded to 0xFFFFFFFF: cmd !
    0x08008D28: "rcc_enable_pll",          # SDK RCC_EnablePll(FunctionalState Cmd): writes the byte argument to the bit-band alias 0
    0x08008D40: "rcc_get_clocks_freq",     # Nations SDK RCC_GetClocksFreqValue(RCC_ClocksType*)
    0x08008F74: "rcc_get_flag_status",     # SPL RCC_GetFlagStatus(flag): selects RCC->CTRL, BDCTRL or CTRLSTS from flag>>5 and retur
    0x08008FF8: "rcc_get_sysclk_src",      # Nations SDK RCC_GetSysclkSrc(): returns RCC->CFG & 0xC (SCLKSTS): 0 = MSI, 0x4 = HSI, 0x
    0x08009008: "rcc_wait_hsi_ready",      # Waits for the HSI oscillator to become ready: loops calling rcc_get_flag_status(0x21) (0
    0x08009070: "rcc_wait_msi_stable",     # Polls RCC flag 0x63 (CTRLSTS bit 3 = MSIRD) up to 0x500 times, then returns 1 if the MSI
    0x080090D8: "modexp_decrypt_blocks",   # (out, in, len): for each big-endian 32-bit word of `in` (count = (len>>2)&0xFF) computes
    0x08009424: "rsa30_encrypt_blocks",    # (uint8_t *out, const uint8_t *in, uint16_t len)
    0x08009DA0: "cipher_set_key",          # Stores a 64-bit key (r0 = low word, r1 = high word) with strd into 0x2000000C/0x20000010
    0x08009DB4: "gpio_init_adc_led_pins",  # Secondary GPIO setup called only from board_gpio_init: GPIO_InitStruct defaults (0x08008
    0x0800A208: "sysclk_config_64mhz",    # SetSysClockToPLL(64 MHz, HSI) then SystemCoreClockUpdate; called from rcc_init
    0x0800A238: "set_sysclk_to_pll_64mhz", # Nations SDK SetSysClockToPLL(freq, src) with freq = 64 000 000 and src = HSI baked in as
    0x0800A5C8: "systick_clk_source_hclk", # CMSIS/SDK misc.c SysTick_CLKSourceConfig(SysTick_CLKSource) with the argument folded to
    0x0800A604: "system_core_clock_update", # SDK SystemCoreClockUpdate() from the Nations system_n32l40x/n32g43x.c family
    0x0800A958: "tim1_nvic_init",          # Builds a NVIC_InitType on the stack {IRQChannel = 25 (TIM1_UP_IRQn), PreemptionPriority
    0x0800AD98: "tim5_nvic_init",          # Enables the TIM5 interrupt in the NVIC: builds an NVIC_InitType {IRQChannel = 50 (TIM5_I
    0x0800ADD4: "tim5_arr_preload_enable", # SDK TIM_ConfigArPreload / TIM_ARRPreloadConfig with both arguments hard-coded: TIMx = TI
    0x0800AE0C: "tim_enable_update_it",    # Nations SDK TIM_ConfigInt(TIMx, TIM_INT, Cmd) with TIM_INT = 1 (update) and Cmd = 1 (ENA
    0x0800AE44: "tim5_oc4_preload_enable", # SDK TIM_OC4PreloadConfig(TIM5, TIM_OCPreload_Enable) with both arguments folded in: read
    0x0800AE8C: "tim1_set_prescaler_immediate", # (prescaler): SDK TIM_PrescalerConfig(TIM1, prescaler, TIM_PSCReloadMode_Immediate) with
    0x0800AEB8: "tim_enable",              # SDK TIM_Enable(TIMx, ENABLE) with Cmd folded to ENABLE: TIMx->CTRL1 (0x00) |= 1 (CEN), s
    0x0800AEE8: "tim5_generate_update_event", # Nations SDK TIM_GenerateEvent(TIMx, TIM_EVT_SRC) with both arguments folded to constants
    0x0800AF54: "tim5_oc4_init",           # SDK TIM_InitOc4 / TIM_OC4Init(TIMx, OCInitType*) with TIMx hard-coded to TIM5; r0 = poin
    0x0800B02C: "tim_oc_struct_init",      # SDK TIM_InitOcStruct / TIM_OCStructInit: zero-fills the 8 halfwords (16 bytes) of a TIM_
    0x0800B058: "tim_time_base_struct_init", # Nations SDK TIM_InitTimBaseStruct(TIM_TimeBaseInitType *s): Period (+4) = 0xFFFF, Presca
    0x0800B094: "tim_time_base_init",      # Nations SDK TIM_InitTimeBase(TIMx, TIM_TimeBaseInitType*)
    0x0800B384: "UsageFault_Handler",      # 4-byte trap stub: `b .+2; b .` (infinite loop)
    0x0800B484: "iwdg_init",               # Configures and starts the independent watchdog: unlock, prescaler /32, reload 0xFFF, kic
    0x0800BAE8: "uid_license_check",       # Anti-clone / UID-binding check run once from main after power-on
    0x0800BBB0: "pow",                     # C library pow(double x, double y): fdlibm/newlib e_pow.c with the SVID wrapper folded in
    0x0800C810: "sqrt",                    # C library double sqrt() wrapper (hard-float ABI: argument and result in d0 = s0:s1)
    0x0800C988: "__mathlib_dbl_divzero",   # ARM Compiler mathlib helper that returns 1.0 / 0.0 = +Infinity (raising divide-by-zero)
    0x0800CA50: "__set_errno",             # ARM Compiler C-library errno setter: stores r0 to the errno word at 0x20000000 (the firs
}

# ---------------------------------------------------------------- variables
VARS = {
    0x20000004: ("system_core_clock", 4),
    0x20000008: ("sampling_active", 1),   # 1 while the ISR fills the sample buffer, 0 when a window is ready
    0x2000000C: ("cipher_key", 8),        # two exponents of the UID-binding cipher, loaded from the licence block
    0x20000030: ("rcc_clocks", 0x18),     # RCC_GetClocksFreq output (?)
    0x20000048: ("mode", 1),              # 0 digital, 1 band-energy, 2 DFT (third key)
    0x2000004A: ("batt_samples", 10),     # 5 x u16 ADC channel 2
    0x20000054: ("batt_state_shadow", 1), # copy of batt_state at the end of battery_1s
    0x20000055: ("speaker_phase", 1),     # toggles 900/700 duty
    0x20000056: ("batt_state", 1),        # 0 ok, 1 low (LED), 2 critical
    0x20000057: ("batt_crit_count", 1),   # readings (500 ms apart) in critical; power off at 5 = 2.5 s
    0x20000058: ("dft_level", 2),
    0x2000005A: ("beep_gap_ctr", 1),      # counts down between repeated beeps (mode 0)
    0x2000005B: ("sample_idx_mode0", 1),
    0x2000005C: ("sample_idx_mode1", 1),
    0x2000005E: ("agc_samples", 10),      # 5 x u16 ADC channel 3
    0x20000068: ("mode0_gate", 2),        # channel-3 level; mode-0 analysis runs only when >= 2
    0x2000006A: ("mode1_gate", 2),        # channel-3 level / 580 (0..7); mode-1 analysis runs only when >= 1
    0x2000006C: ("signal_recent", 2),     # set to 800 ticks (0.8 s) on each detection
    0x2000006E: ("sample_buf", 128),      # 64 x u16
    0x200000EE: ("sub_step", 1),          # 1..10 within a 5 ms mode-0 sample, 0.5 ms each; ADC read at 6..9
    0x200000F0: ("sub_buf", 10),          # 5 x u16, slots 4..0 written at sub-steps 6..10
    0x200000FC: ("tick_1ms", 4),          # TIM1 tick counter
    0x20000100: ("tick_40khz", 4),        # TIM5 tick counter
    0x20000104: ("idle_ticks", 4),        # -> power_off at 300 000 ms (5 min)
    0x20000108: ("sample_idx_mode2", 1),
    0x2000010A: ("pwr_key_hold_ms", 2),   # PC13 held low: power_off at 1200 ms
    0x2000010C: ("keep_alive", 1),        # beep length in ms; resets idle_ticks while non-zero
    0x2000010E: ("key1_hold", 2),         # PC15
    0x20000110: ("key2_hold", 2),         # PD15
    0x20000112: ("key3_hold", 2),         # PD14
}

CONSTS = {
    "SYSCLK_HZ": 64000000,
    "TIM_CLK_HZ": 64000000,
    "TIM1_TICK_MS": 1,
    "TIM5_HZ": 40000,
    "AUTO_OFF_TICKS": 300000,             # 5 min
    "BATT_PERIOD_MS": 500,
    "BATT_LOW_MV": 3579,                  # LED on at or below
    "BATT_LOW_CLEAR_MV": 3621,            # LED off at or above
    "BATT_CRIT_MV": 3280,                 # critical below (stock: no way back)
    "BATT_CRIT_READINGS": 5,              # x 500 ms = 2.5 s
    "PATTERN": 0xB6B6,                    # the TX "Normal" cadence, 16 slots of 5 ms (period 8 slots)
    "VERSION_STRING": 0x0800CDE4,         # "3.0.0", 6-byte slot; not displayed (no screen)
}

PERIPHERALS = {
    0x40010800: "GPIOA", 0x40010C00: "GPIOB", 0x40011000: "GPIOC", 0x40011400: "GPIOD",
    0x40021000: "RCC", 0x40022000: "FLASH", 0x40020800: "ADC1", 0x40012C00: "TIM1",
    0x40000000: "TIM2", 0x40000400: "TIM3", 0x40000800: "TIM4", 0x40000C00: "TIM5",
    0x40001000: "TIM6", 0x40001400: "TIM7", 0x40003000: "IWDG", 0x40007000: "PWR",
    0x40010400: "EXTI", 0x40013400: "TIM8", 0x40001800: "AFEC", 0xE000E010: "SysTick",
    0xE000E100: "NVIC", 0xE000ED00: "SCB",
}
PERIPHERAL_SIZE = {"SysTick": 0x10, "NVIC": 0x400, "SCB": 0x90}   # default window 0x400


FUNCS_BY_NAME = {n: a for a, n in FUNCS.items()}
PERIPHERALS_BY_NAME = {n: a for a, n in PERIPHERALS.items()}


def asm_symbols():
    out = {}
    for a, n in FUNCS.items():
        out[n] = a | 1
        out[n + "_addr"] = a
    for a, (n, _) in VARS.items():
        out[n] = a
    out.update(CONSTS)
    return out
