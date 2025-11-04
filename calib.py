from machine import LED
import sensor, image, time, os, math

print("START CALIB")
# ---------------- CONFIG ----------------
thresholdblack = [(50, 100, -70, -10, 0, 50)]  # adjust as needed
leds = LED("LED_GREEN")
leds.on
# Camera setup
sensor.reset()

sensor.set_pixformat(sensor.RGB565)
#print("test")
sensor.set_framesize(sensor.QVGA)
#print("test")
sensor.skip_frames(time=2000)
sensor.set_auto_whitebal(False)
#print("test")



posx = []
posy = []
blobs_data = []  # store blobs from all frames

print("Starting calibration phase for 5 seconds...")


# Warm-up frames
for _ in range(10):
    try:
        sensor.snapshot()
        time.sleep_ms(50)
    except Exception as e:
        print("Warm-up snapshot failed:", e)
        time.sleep_ms(100)

# ---------------- CALIBRATION LOOP ----------------
start_time = time.ticks_ms()

while time.ticks_diff(time.ticks_ms(), start_time) < 5000:
    try:
        cal = sensor.snapshot()
    except Exception as e:
        print("Snapshot failed:", e)
        continue  # Skip this frame

    blobs = cal.find_blobs(thresholdblack, pixels_threshold=100, area_threshold=100)

    frame_blobs = []
    for c in blobs[:6]:  # take up to 6 blobs now
        r = c.roundness()
        if r is not None and r > 0.7 and c.pixels() < 999:
            cal.draw_cross(c.cx(), c.cy(), color=(255, 0, 0))
            cal.draw_circle(c.cx(), c.cy(), 5, color=(0, 255, 0))
            frame_blobs.append((c.cx(), c.cy()))

    if frame_blobs:
        blobs_data.append(frame_blobs)

    time.sleep_ms(100)


# ---------------- POST-PROCESSING ----------------
if not blobs_data:
    raise ValueError("No valid blobs detected during calibration.")

# --- Distance helper ---
def distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

clusters = []

# --- Cluster blobs across frames ---
for frame in blobs_data:
    for blob in frame:
        found_cluster = False
        for cluster in clusters:
            if distance(blob, cluster[0]) < 30:  # within 30px → same blob
                cluster.append(blob)
                found_cluster = True
                break
        if not found_cluster:
            clusters.append([blob])  # new blob

# --- Average position per cluster ---
averaged_points = []
for cluster in clusters:
    xs = [p[0] for p in cluster]
    ys = [p[1] for p in cluster]
    avg_x = int(round(sum(xs) / len(xs))/2)
    avg_y = int(round(sum(ys) / len(ys))/2)
    averaged_points.append((avg_x, avg_y))

# --- Sort blobs by position for consistency (top row then bottom row) ---
averaged_points = sorted(averaged_points, key=lambda p: (p[1], p[0]))  # sort by y then x
if len(averaged_points) > 6:
    averaged_points = averaged_points[:6]  # only keep 6 most consistent blobs

# ---------------- SAVE RESULTS ----------------
print("\nAveraged Blob Coordinates:")
for i, (x, y) in enumerate(averaged_points):
    print(f"Blob {i+1}: X={x}, Y={y}")

# Compute ROI (bounding box of all blobs)
all_x = [x for x, _ in averaged_points]
all_y = [y for _, y in averaged_points]
roi = (min(all_x), min(all_y), max(all_x)-min(all_x), max(all_y)-min(all_y))

# Save to file
with open("coords.txt", "w") as file:
    file.write(f"ROI: {roi}\n")
    print(f"ROI: {roi}\n")
    file.write("Averaged Points:\n")
    for i, (x, y) in enumerate(averaged_points):
        file.write(f"Blob {i+1}: X={x}, Y={y}\n")

with open("coords.txt", "r") as file:
                    lines = file.readlines()
print("File written.")
