import pyb
from machine import LED
#print("test")
proto_path = "protocol.txt"
coords_path = "coords.txt"
led_pin = pyb.Pin('P7', pyb.Pin.OUT_PP)
with open(proto_path, "a") as proto_file:
    proto_file.write("\ntest" )
last_line_count=0
leds = LED("LED_BLUE")
leds.on()
#print("start")
def run_script(filename):
    try:
        with open(filename) as f:
            exec(f.read())
    except Exception as e:
        print("Error running", filename, ":", e)

while True:
    try:
        # Read file
        with open(proto_path, "r") as f:
            lines = f.readlines()
            line_count = len(lines)

        if lines:
            final_cmd = lines[-1].strip().lower()
        else:
            final_cmd = ""

        # Only act when a new line is added
        if line_count > last_line_count:
            print("New line detected:", final_cmd)

            if final_cmd:
                try:
                    if final_cmd == "start":
                        run_script("detc.py")

                    elif final_cmd == "calib":
                        run_script("calib.py")

                    elif final_cmd == "end":
                        print("End command received.")

                    elif final_cmd == "exit":
                        print("Exiting main loop.")
                        break

                    elif final_cmd == "coords":
                        try:
                            with open(coords_path, "r") as file:
                                coord_lines = file.readlines()
                                if not coord_lines:
                                    print("coords.txt is empty.")
                                else:
                                    for line in coord_lines:
                                        print(line.strip())
                        except OSError as e:
                            print("coords.txt not found:", e)

                    elif final_cmd == "test":
                        pass
                        print("Now active.")

                    elif final_cmd == "led_off":
                        led_pin.low()
                        print("LED is now inactive.")

                    else:
                        print("Unknown command:", final_cmd)

                except Exception as cmd_error:
                    print("Error while executing command:", final_cmd,",",cmd_error)

            # update line counter
            last_line_count = line_count

    except Exception as loop_error:
        print("Error in main loop:",loop_error)

    pyb.delay(200)  # wait before checking again
