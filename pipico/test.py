import sys
import select
from machine import Pin, I2C
import ssd1306
import time
import json  

trg_pin = Pin(8, Pin.OUT)
do_pins = [Pin(i, Pin.OUT) for i in range(8)]
button = Pin(16, Pin.IN, Pin.PULL_UP)
MASK_RELEASE_AFTER_SEC = 200

i2c = I2C(1, sda=Pin(26), scl=Pin(27), freq=400000)
display = ssd1306.SSD1306_I2C(128, 64, i2c)

TRIG_TIMER_SEC = 1
PULSE_WIDTH_US = 2000 
COUNT = 0

def clear_all_outputs():
    for pin in do_pins:
        pin.value(0)
    trg_pin.value(0)

def large_text(text, x, y, scale=2):
    for i, char in enumerate(text):
        for row in range(8):
            char_buf = bytearray(8)
            fb = ssd1306.framebuf.FrameBuffer(char_buf, 8, 8, ssd1306.framebuf.MONO_VLSB)
            fb.text(char, 0, 0, 1)
            
            for col in range(8):
                if fb.pixel(col, row):
                    for sy in range(scale):
                        for sx in range(scale):
                            display.pixel(x + (i * 8 * scale) + (col * scale) + sx, 
                                          y + (row * scale) + sy, 1)

def update_display(status_text, current_count, elapsed_ms):
    if config_mode:
        display.fill(0)
        display.text("== CONFIG MODE ==", 0, 0)
        large_text("PC APP", 16, 18, 2)
        display.text("Connect via PC Tool", 0, 52)
        display.show()
        return

    total_seconds = int(elapsed_ms / 1000)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    display.fill(0) 
    display.text(f"STATUS: {status_text}", 0, 0)
    count_str = f"C:{current_count:02d}/95"
    large_text(count_str, x=0, y=16, scale=2)
    large_text(time_str, x=0, y=44, scale=2)
    display.show()

def display_error(error_msg):
    display.fill(0)
    display.text("== ERROR ==", 0, 0)
    display.text("JSON LOAD FAILED", 0, 18)
    display.text(str(error_msg)[:16], 0, 36)
    display.text(str(error_msg)[16:32], 0, 50)
    display.show()

def set_pins_to_count(current_count):
    number = current_count & 0xFF 
    for i in range(8):
        bit_status = (number >> i) & 1
        do_pins[i].value(bit_status)

def trig(elapsed_ms, current_count):
    release_time_ms = MASK_RELEASE_TIME_MS[current_count]
    if elapsed_ms >= release_time_ms or elapsed_ms >= (MASK_RELEASE_AFTER_SEC * 1000):
        trg_pin.value(1)
    else:
        trg_pin.value(0)
    set_pins_to_count(current_count)
    time.sleep_us(PULSE_WIDTH_US)
    trg_pin.value(0)

json_success = False
try:
    with open("config.json", "r") as f:
        raw_data = json.load(f)
    MASK_RELEASE_TIME_SEC = {int(k): v for k, v in raw_data.items()}
    MASK_RELEASE_TIME_MS = {k: v * 1000 for k, v in MASK_RELEASE_TIME_SEC.items()}
    json_success = True
except Exception as e:
    MASK_RELEASE_TIME_SEC = {i: 0.0 for i in range(96)}
    MASK_RELEASE_TIME_MS = {i: 0 for i in range(96)}
    display_error(e)   

running = False
start_time = 0
next_trig_deadline = 0
last_button_state = 1
last_click_time = 0
button_press_start = 0
button_held = False

clear_all_outputs()
update_display("READY", 0, 0)

while True:
    now_ms = time.ticks_ms()
    current_button_state = button.value()
    if last_button_state == 1 and current_button_state == 0:
        time.sleep_ms(20) # Debounce
        if button.value() == 0:
            button_press_start = now_ms
            button_held = True

    if button_held and current_button_state == 0:
        # Check if held for 5000ms (5 seconds)
        if time.ticks_diff(now_ms, button_press_start) >= 5000:
            button_held = False # Reset hold trigger
            if running:
                running = False
                clear_all_outputs()
            
            # Toggle Configuration Mode
            config_mode = not config_mode
            if config_mode:
                print("Entered CONFIG MODE")
                update_display("CONFIG", 0, 0)
            else:
                print("Exited CONFIG MODE")
                update_display("READY", 0, 0)
            
            # Wait for user to release button so it doesn't trigger clicks
            while button.value() == 0:
                time.sleep_ms(10)

    # --- Button Released ---
    if last_button_state == 0 and current_button_state == 1:
        if button_held: # Meaning it was released BEFORE 5 seconds
            button_held = False
            if not config_mode: # Ignore clicks if in config mode
                if not running:
                    running = True
                    COUNT = 0
                    start_time = time.ticks_ms()
                    next_trig_deadline = time.ticks_add(start_time, TRIG_TIMER_SEC * 1000)
                    clear_all_outputs()
                    last_click_time = now_ms
                else:
                    if time.ticks_diff(now_ms, last_click_time) < 500:
                        running = False
                        clear_all_outputs()
                        update_display("STOPPED", COUNT, time.ticks_diff(now_ms, start_time))
                    else:
                        last_click_time = now_ms

    last_button_state = current_button_state

    # --- Standard Execution Mode ---
    if running and not config_mode:
        if time.ticks_diff(now_ms, next_trig_deadline) >= 0:
            elapsed_total_ms = time.ticks_diff(now_ms, start_time)
            current_count = COUNT if COUNT <= 95 else 0
            trig(elapsed_total_ms, current_count)
            update_display("RUNNING", current_count, elapsed_total_ms)
            COUNT = (current_count + 1) if (current_count < 95) else 0
            next_trig_deadline = time.ticks_add(next_trig_deadline, TRIG_TIMER_SEC * 1000)

    time.sleep_ms(1)