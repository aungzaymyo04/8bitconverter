import board
import busio
import digitalio
import time
import json
import adafruit_ssd1306


trg_pin = digitalio.DigitalInOut(board.GP8)
trg_pin.direction = digitalio.Direction.OUTPUT

do_pins = []
for i in range(8):
    pin = digitalio.DigitalInOut(getattr(board, f"GP{i}"))
    pin.direction = digitalio.Direction.OUTPUT
    do_pins.append(pin)

button = digitalio.DigitalInOut(board.GP16)
button.direction = digitalio.Direction.INPUT
button.pull = digitalio.Pull.UP

MASK_RELEASE_AFTER_SEC = 200
TRIG_TIMER_SEC = 1
PULSE_WIDTH_SEC = 2000 / 1000000.0 
COUNT = 0

i2c = busio.I2C(scl=board.GP27, sda=board.GP26, frequency=400000)
display = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3C)

def clear_all_outputs():
    for pin in do_pins:
        pin.value = False
    trg_pin.value = False

def large_text(text, x, y, scale=2):
    display.text(text, x, y, 1, size=scale)

def update_display(status_text, current_count, elapsed_sec):
    total_seconds = int(elapsed_sec)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    display.fill(0) 
    display.text(f"STATUS: {status_text}", 0, 0, 1)
    count_str = f"C:{current_count:02d}/95"
    large_text(count_str, x=0, y=16, scale=2)
    large_text(time_str, x=0, y=44, scale=2)
    display.show()

def display_error(error_msg):
    display.fill(0)
    display.text("== ERROR ==", 0, 0, 1)
    display.text("JSON LOAD FAILED", 0, 18, 1)
    display.text(str(error_msg)[:16], 0, 36, 1)
    display.text(str(error_msg)[16:32], 0, 50, 1)
    display.show()

def set_pins_to_count(current_count):
    number = current_count & 0xFF 
    for i in range(8):
        bit_status = (number >> i) & 1
        do_pins[i].value = bool(bit_status)

def trig(elapsed_sec, current_count):
    target_time_sec = MASK_RELEASE_TIME_SEC[current_count]
    if elapsed_sec >= target_time_sec:
        trg_pin.value = True
    else:
        trg_pin.value = False
    set_pins_to_count(current_count)
    
    if trg_pin.value:
        time.sleep(PULSE_WIDTH_SEC)
        trg_pin.value = False

json_success = False
try:
    with open("config.json", "r") as f:
        raw_data = json.load(f)
    MASK_RELEASE_TIME_SEC = {int(k): v for k, v in raw_data.items()}
    print("JSON configuration loaded successfully.")
    json_success = True
except Exception as e:
    print("Failed to load JSON:", e)
    display_error(e)   
    clear_all_outputs() 

if not json_success:
    print("Program halted due to JSON error.")
    while True:
        time.sleep(1.0)

running = False
start_time = 0.0
next_trig_deadline = 0.0
last_button_state = True
last_click_time = 0.0

clear_all_outputs()
print("System Ready. 1-click to Start / Double-click to Stop.")
update_display("READY", 0, 0.0)

while True:
    current_button_state = button.value
    now = time.monotonic()
    
    if last_button_state and not current_button_state:
        time.sleep(0.02) 
        if not button.value:
            if not running:
                running = True
                COUNT = 0
                start_time = time.monotonic()
                next_trig_deadline = start_time + TRIG_TIMER_SEC
                clear_all_outputs()
                print("System STARTED")
                last_click_time = now
            else:
                if (now - last_click_time) < 0.6:
                    running = False
                    clear_all_outputs()
                    print("System STOPPED (Double-click)")
                    update_display("STOPPED", COUNT, now - start_time)
                else:
                    print("Click detected (Waiting for second click to stop...)")
                    last_click_time = now

    last_button_state = current_button_state

    if running:
        if now >= next_trig_deadline:
            elapsed_total_sec = now - start_time
            current_count = COUNT if COUNT <= 95 else 0
            
            print(f"Count: {current_count}, Elapsed: {elapsed_total_sec:.2f} s")
            
            trig(elapsed_total_sec, current_count)
            update_display("RUNNING", current_count, elapsed_total_sec)
            
            COUNT = (current_count + 1) if (current_count < 95) else 0
            next_trig_deadline += TRIG_TIMER_SEC

    time.sleep(0.001)