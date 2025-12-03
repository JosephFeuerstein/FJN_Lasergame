from pyb import LED, Pin
import sensor, time

led = LED(1)  # red LED
led.on()
sound_pin= Pin('P7', Pin.OUT_PP) 
sound_pin.low()
roi = None
thresholdred = [(30, 100, 15, 127, -20, 40)]
first = True

# Camera setup
sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.QQVGA)
sensor.skip_frames(time=2000)
sensor.set_auto_whitebal(False)

clock = time.clock()

# Load ROI
try:
    with open("coords.txt", "r") as file:
        line = file.readline()
        if "ROI" in line:
            roi_str = line.split(":")[1].strip().strip("()")
            roi = tuple(map(int, roi_str.split(",")))
except OSError:
    print("coords.txt not found")


if roi is None:
    raise ValueError("ROI not loaded correctly")
print("differencing")
while True:
    clock.tick()
    img = sensor.snapshot()

    if first:
        first = False
        sound_pin.high()
        for b in img.find_blobs(thresholdred, roi=roi, pixels_threshold=15, area_threshold=15):
            if b.roundness() > 0.5:
                print(f"\nX: {b.cx()} # Y: {b.cy()}")
                time.sleep(0.5)
    else:
        first = True
        sound_pin.low()

    try:
        with open("protocol.txt", "r") as f:
            lines = f.readlines()
            if lines and lines[-1].strip().lower() == "end":
                print("End command detected. Exiting loop.")
                break
    except OSError:
        pass
    except Exception:
        print("Error reading protocol.txt")
        pass