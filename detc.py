from machine import LED
import sensor, time

print("START DETC")

leds = LED("LED_RED")
leds.on

roi = None
TRIGGER_THRESHOLD = 0.5
thresholdred = [(30, 100, 15, 127, -20, 40)]
first = True

# Camera setup
sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.QQVGA)
sensor.skip_frames(time=2000)
sensor.set_auto_whitebal(False)

clock = time.clock()

extra_fb = sensor.alloc_extra_fb(sensor.width(), sensor.height(), sensor.RGB565)




# Save background
print("About to save background image...")
sensor.skip_frames(time=2000)
extra_fb.replace(sensor.snapshot())
print("Saved background image - Now starting frame differencing!")
print()
with open("coords.txt", "r") as file: #fehler wahrscheinlich hier oder am ende ***
        line = file.readline()  # e.g., "ROI: (10, 20, 50, 50)"
        #print(line)
        if "ROI" in line:
            roi_str = line.split(":")[1].strip()
            roi = eval(roi_str)  # Use only if you trust the input
        if roi is None:
            print("error1")
            raise ValueError("ROI not loaded correctly")
        #print(roi)
while True:
    clock.tick()
    img = sensor.snapshot()
    copy = img.copy()
    img.difference(extra_fb)

    hist = img.get_histogram()
    diff = hist.get_percentile(0.99).l_value() - hist.get_percentile(0.90).l_value()
    triggered = diff > TRIGGER_THRESHOLD

    copy.draw_rectangle(roi, color=(255, 0, 0), thickness=2)

    if triggered and first:
        first = False
        for b in copy.find_blobs(thresholdred, roi=roi, pixels_threshold=15, area_threshold=15):
            r = b.roundness()
            if r is not None and r > 0.5:
                copy.draw_cross(b.cx(), b.cy())
                with open("coords.txt", "a") as file:
                    file.write(f"\nX: {b.cx()} # Y: {b.cy()}")
                    print(f"\nX: {b.cx()} # Y: {b.cy()}")
    else:
        first = True

    try:
        with open("protocol.txt", "r") as f:
            lines = f.readlines()
            if lines:  # only if file is not empty
              final_cmd = lines[-1].strip().lower()
              if final_cmd == "end":
                  print("End command detected. Exiting loop.")
                  break
            else:
                pass  # file is empty
    except OSError:
        # file does not exist yet
        pass
    except Exception as e:
        print("Error reading protocol.txt:", e)
        pass