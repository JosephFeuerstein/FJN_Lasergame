#  IMPORTS

import serial              # Serial communication with camera firmware
import time                # Timing, delays, scheduling
import tkinter as tk       # GUI / game display
import cv2                 # point transformation
import numpy as np         # Numerical calculations
import math                # Scoring distances
import random              # Randomized target movement
import os                  # File-path validation

#  FILE & SYSTEM CONFIGURATION

serial_port = "COM7"        # Default COM port for camera device
baud_rate = 9600            # Baud rate for serial communication

# Paths for logs, ROI coords, and leaderboard
protocol_path    = r"E:\protocol.txt"
coords_path      = r"E:\coords.txt"
leaderboard_path = r"D:\FJN_2025-26\Project_Han_Solo\leaderboard.txt"

#  CANVAS SETUP (monitor resolution)

canvas_width  = 1600
canvas_height = 1200

#  GAME CONFIGURATION

rounds   = 6        # Number of shots / rounds per game
length_x = 400      # Battery UI dimensions
length_y = 200

edge_x = 50         # Battery offset from left
edge_y = 100        # Battery offset from bottom

distanz = 5         # Spacing inside battery UI
versatz = 20        # Trapezoid side offset

leaderboard_size = 10     # Show top X scores
game_mode = 1             # Default game mode (1=Easy)

hold = False              # Auto-player lock

#  TARGET CONFIGURATION

target_rings = 5        
ring_step = 75            # Pixel width per scoring ring

target_visible = True
target_hide_time = 1000   # For moving modes
move_interval   = 2000    # Delay between moves

#  GLOBAL VARS / STATE

root = None               # Tkinter root window
canvas = None             # Tkinter canvas for game display
ser = None                # Serial port object

round_count = 0           # How many shots taken
mrc = 0                   # Battery UI index for marking missed shots
rbs = 0                   # Remove Battery segment 

# Calibration & transformation
blob = []                 # Detected calibration blobs from camera
radius = 75               # Calibration circle radius
matrix = None                  # transformation matrix
transform_type = None     # “Perspective” (usually)
corr_l_x = 0              # Correction factors (legacy)
corr_l_y = 0
roi = None                # Region of interest returned by camera

# Admin mode
adminmode = False

# Player management
player = 1
START = True
hit = False
first = True     # For auto-start function
free = True      # Controls hit registration in moving modes
diff = 0         # Unused?

# Scoring system
points = [20, 40, 60, 80, 100]   # Outer → inner
score = 0

shotsx = []      # X coords of hits for display
shotsy = []      # Y coords of hits for display
shots = 0        # Number of valid hits

# Initial target position (center screen)
target_center = (canvas_width//2, canvas_height//2 - 50)
temp_center = (0,0)

running = False     # Game running or not
step = 20           # Unused?
last_hide_time = 0  # Timestamp for hiding target
missed_rounds = 0   # Missed shots in gamemode 3

# Precompute battery UI size
length = int((length_x - (2 * distanz)) / rounds - distanz)

# Start/end of ammo UI rectangle
startpoint = [edge_x, canvas_height - edge_y - length_y]
endpoint   = [startpoint[0] + length_x, startpoint[1] + length_y]


#  CALIBRATION PROCESS

def calibration(cmd):
    """
    Performs camera calibration by listening for coordinates of
    6 detected green blobs sent from the external camera program.

    """

    global blob, ser, corr_l_x, corr_l_y, roi
    blob = []   # Reset detected blobs list

    # Reset / reopen serial port
    if ser and ser.is_open:
        ser.close()
    time.sleep(0.5)

    # Log calibration start into protocol file
    with open(protocol_path, "a") as proto_file:
        proto_file.write("\nend")

    try:
        # Attempt to open serial communication
        ser = serial.Serial(serial_port, baud_rate, timeout=1)
        print(f"\nConnected to {serial_port} at {baud_rate} baud.")

        with open(protocol_path, "a") as proto_file:
            proto_file.write("\n" + cmd)

        # Wait for camera to acknowledge calibration start
        line = ser.readline()
        msg = line.decode('utf-8').strip()
        if msg == "Starting calibration phase":
            print(msg)

        # Main loop: read blobs until firmware sends "File written."
        while True:
            line = ser.readline()
            if line:
                msg = line.decode('utf-8').strip()

                # Parse camera blobd
                if "Blob" in msg and ":" in msg:
                    try:
                        # Expected format: "Blob: x=123, y=456"
                        parts = msg.split(":")[1].strip().split(",")
                        x_val = int(parts[0].split("=")[1])
                        y_val = int(parts[1].split("=")[1])

                        blob.append({'x': x_val, 'y': y_val})

                        # Keep only the last 6 points (camera may overshoot)
                        if len(blob) > 6:
                            blob = blob[-6:]
                    except Exception as e:
                        print("Parsing blob error:", e)

                # Parse ROI
                if "ROI" in msg:
                    # Expected: "ROI: (x1, y1, x2, y2)"
                    roi_str = msg.split(":")[1].strip()
                    roi = eval(roi_str)

                    # Normalize camera coords → screen coords multipliers
                    corr_l_x = (canvas_width - 20 - radius) / (roi[2] - roi[0])
                    corr_l_y = (canvas_height - 20 - radius) / (roi[3] - roi[1])

                # Finish calibration
                if msg == "File written.":
                    # Sort blobs into TL/TM/TR + BL/BM/BR
                    blob[:] = sort_blobs_by_position(blob)
                    print("Calibration complete.")
                    ser.close()
                    return

                # If camera script failed
                if "Error running calib.py" in msg:
                    ser.close()
                    return

            # Keep UI responsive
            if root:
                root.update()
            time.sleep(0.1)

    except Exception as e:
        print("Calibration serial error:", e)
        ser.close()
        return


#  IMAGE - SCREEN COORDINATE CALIBRATION

def correction(radius):
    """
    Computes the perspective transformation matrix 
    from camera coordinates to screen coordinates based on the
    6 calibration blobs.

    """

    global blob

    # Filter out missing blobs
    valid_blobs = [b for b in blob if b is not None]

    if len(valid_blobs) < 4:
        print("Not enough blobs for correction (need at least 4).")
        return None, None

    # Camera detection positions
    camera_pts = np.float32([[b['x'], b['y']] for b in valid_blobs])

    # Corresponding exact screen positions of calibration circles
    screen_pts = np.float32([
        [20 + radius, 20 + radius],                               # Top-left
        [canvas_width / 2, 20 + radius],                          # Top-middle
        [canvas_width - 20 - radius, 20 + radius],                # Top-right
        [20 + radius, canvas_height - 100 - radius],              # Bottom-left
        [canvas_width / 2, canvas_height - 100 - radius],         # Bottom-middle
        [canvas_width - 20 - radius, canvas_height - 100 - radius]# Bottom-right
    ])

    # Compute transformation
    if len(valid_blobs) >= 4:
        matrix, _ = cv2.findHomography(camera_pts, screen_pts[:len(valid_blobs)])
        transform_type = "Perspective"
    else:
        print("Unexpected number of blobs.")
        return None, None

    return matrix, transform_type


#  BLOB SORTING 

def sort_blobs_by_position(blobs):
    """
    Sorts the detected calibration blobs into a consistent order:
        0 = Top-left
        1 = Top-middle
        2 = Top-right
        3 = Bottom-left
        4 = Bottom-middle
        5 = Bottom-right

    Sorting is performed by first splitting into top/bottom rows
    based on Y values, then left→right by X values.

    """

    if not blobs:
        return [None] * 6

    # Sort by vertical (y)
    sorted_by_y = sorted(blobs, key=lambda b: b['y'])
    half = len(sorted_by_y) // 2

    top = sorted(sorted_by_y[:half], key=lambda b: b['x'])
    bottom = sorted(sorted_by_y[half:], key=lambda b: b['x'])

    # Prepare ordered list
    ordered = [None] * 6

    # Assign sorted blobs to positions
    if len(top) >= 1: ordered[0] = top[0]  # TL
    if len(top) >= 2: ordered[1] = top[1]  # TM
    if len(top) >= 3: ordered[2] = top[2]  # TR

    if len(bottom) >= 1: ordered[3] = bottom[0]  # BL
    if len(bottom) >= 2: ordered[4] = bottom[1]  # BM
    if len(bottom) >= 3: ordered[5] = bottom[2]  # BR

    return ordered


#  ROUND START

def round_start(rounds,cmd,Name):
    """
    Prepares and starts a game session.

    Steps:
    1. Resets `round_count`
    2. Reopens serial port
    3. Draws game monitor UI (target + battery)
    4. Starts serial reading loop that waits for hits

    """

    global ser, round_count,canvas,game_mode
    round_count = 0

    # Ensure serial starts fresh
    if ser and ser.is_open:
        ser.close()
    time.sleep(0.5)

    if matrix is not None:   # Calibration must be done
        try:
            ser = serial.Serial(serial_port, baud_rate, timeout=0.1)
            print(f"\nConnected to {serial_port} at {baud_rate} baud.")

            # Draw game UI
            game_monitor(canvas)

            # Begin serial reading for hits/detections
            read_serial(rounds, Name)
        
        except Exception as e:
            print("Error opening serial port:", e)

                # Log into protocol
        with open(protocol_path, "a") as proto_file:
            proto_file.write("\n" + cmd)
    else:
        print("run calibration first")


#  COORD CORRECTION

def correct_coords(x_cam, y_cam, matrix, transform_type):
    pt = np.array([[[x_cam, y_cam]]], dtype=np.float32)
    if transform_type == "Affine":
        pt_corr = cv2.transform(pt, matrix)
    elif transform_type == "Perspective":
        pt_corr = cv2.perspectiveTransform(pt, matrix)
    else:
        raise ValueError("Unknown transform type")
    return pt_corr[0][0]


#  SERIAL READER

def read_serial(rounds, Name):
    """
    Main loop that listens to serial input from camera.

    Camera sends:
        "differencing..." → start game
        "X:123 # Y:456"    → shot detected
        other debug text → printed

    Based on game mode:
        Mode 1 = fixed target
        Mode 2 = hide + teleport target
        Mode 3 = timed appearance + strict scoring

    """

    global ser, canvas, round_count, matrix, transform_type
    global game_mode, running, target_hide_time, move_interval
    global shots, free, rbs, missed_rounds

    # No serial port available
    if ser is None or not ser.is_open:
        print("Serial port not open.")
        return

    try:

        # Read serial line

        line = ser.readline()
        if line:
            treffer = line.decode('utf-8').strip()

            # Start Sequence
            if "differencing" in treffer:
                for dx, dy in [(-2,0), (2,0), (0,-2), (0,2)]:
                    canvas.create_text(
                        target_center[0] + dx, target_center[1] + dy,
                        text="READY?", fill="cyan",
                        font=("Arial", 160, "bold"), tags="READY"
                    )
                canvas.create_text(
                    target_center[0], target_center[1],
                    text="READY?", fill="black",
                    font=("Arial", 160, "bold"), tags="READY"
                )
                root.update()
                time.sleep(3)

                canvas.delete("READY")

                for dx, dy in [(-2,0), (2,0), (0,-2), (0,2)]:
                    canvas.create_text(
                        target_center[0] + dx, target_center[1] + dy,
                        text="START!", fill="cyan",
                        font=("Arial", 160, "bold"), tags="START"
                    )
                canvas.create_text(
                    target_center[0], target_center[1],
                    text="START!", fill="black",
                    font=("Arial", 160, "bold"), tags="START"
                )

                root.update()
                time.sleep(1)
                canvas.delete("START")

                # Start game loop
                running = True

                # mode 3 = hard mode (timed, moving target)
                if game_mode == 3:
                    print("Started Hard-difficulty\n")
                    target_hide_time = 1500
                    move_interval = 3000
                    auto_move_target(Name)

                # mode 2 = Medium (random hide/move)
                elif game_mode == 2:
                    print("Started Medium-difficulty\n")
                    target_hide_time = random.randint(700,1500)
                    move_interval = target_hide_time + random.randint(700,1500) + 500
                    auto_move_target(Name)

                # mode 1 = Easy (fixed target)
                else:
                    print("Started Easy-difficulty\n")

            # Shots detected: "X:### # Y:###" 
            elif "X" in treffer and "Y" in treffer:
                try:
                    parts = treffer.split("#")
                    hit_x = int(parts[0].split(":")[1])
                    hit_y = int(parts[1].split(":")[1])

                    # Mode 3 uses "free" to prevent double-scoring
                    if not free or game_mode != 3:
                        round_count += 1

                    # Transformation from camera → screen coordinates
                    if matrix is not None and transform_type is not None:
                        x_corr, y_corr = correct_coords(hit_x, hit_y, matrix, transform_type)

                        # Do not exceed max rounds
                        if canvas and missed_rounds + shots < rounds + 1:
                            game_hit(canvas, x_corr, y_corr)
                            free = False

                            # Remove next battery segment (visual ammo)
                            canvas.delete(f"batt{rounds - rbs + 1}")
                            root.update()
                    else:
                        print("Transform not computed yet. Run calibration first.")

                except Exception as e:
                    print("Parsing error:", e)

            # Camera sent unrelated text
            else:
                print(treffer)

        # Continue polling
        root.after(100, lambda: read_serial(rounds, Name))

    except serial.SerialException as e:
        print("Serial error:", e)
        if ser and ser.is_open:
            ser.close()

# ------------------- GUI -------------------
def monitor_create():
    # Creates the Canvas on which ever other screen is build 
    # (if this function is run twice only the newer one will run the screens)
    global root, canvas

    root = tk.Tk()
    root.title("Laser-Game")
    canvas = tk.Canvas(root, width=canvas_width, height=canvas_height, bg="black")
    canvas.pack()
    
    root.update()
    print("Monitor window created.")
    Credits()
    return root, canvas

def monitor_setup(canvas, width, height, radius):
    # runs the screen for the calibration
    try:
        canvas.delete("target","START","batt")
        for i in range(rounds+1):
            canvas.delete(f"batt{i}")
    except:
        pass 
    """Draw 6 calibration circles"""
    # Top row (L, M, R)
    canvas.create_oval(20, 20, 20 + 2 * radius, 20 + 2 * radius, fill="chartreuse2",tags="Calib")  # TL
    canvas.create_oval(width/2 - radius, 20, width/2 + radius, 20 + 2 * radius, fill="chartreuse2",tags="Calib")  # TM
    canvas.create_oval(width - 20 - 2 * radius, 20, width - 20, 20 + 2 * radius, fill="chartreuse2",tags="Calib")  # TR
    # Bottom row (L, M, R)
    y_bottom = height - 100
    canvas.create_oval(20, y_bottom - 2 * radius, 20 + 2 * radius, y_bottom, fill="chartreuse2",tags="Calib")  # BL
    canvas.create_oval(width/2 - radius, y_bottom - 2 * radius, width/2 + radius, y_bottom, fill="chartreuse2",tags="Calib")  # BM
    canvas.create_oval(width - 20 - 2 * radius, y_bottom - 2 * radius, width - 20, y_bottom, fill="chartreuse2",tags="Calib")  # BR

def game_monitor(canvas):
    # runs the screen for the for the game 
    global score   
    draw_target(*target_center) 
    batterie(canvas)

def draw_target(x, y):
    # Creates the target
    global target_visible, canvas, target_center
    canvas.delete("target")
    if not target_visible:
        print("nicht sichtbar")
        return

    for i in range(target_rings):
        if i != target_rings - 1:
            radius1 = (target_rings - i) * ring_step
            radius2 = (target_rings-(i+1)) * ring_step
            color = "black"
            canvas.create_oval(
                x - radius1, y - radius1,
                x + radius1, y + radius1,
                fill=color, outline="cyan", width=3, tags="target"
            
            )
            for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
                canvas.create_text(target_center[0]+dx, target_center[1]+(radius2+(radius1-radius2)/2)+dy, text=points[i], fill="cyan", font=("Arial", 50, "bold"),tags="target")
            canvas.create_text(target_center[0], target_center[1]+(radius2+(radius1-radius2)/2), text=points[i], fill="black", font=("Arial", 50, "bold"), tags="target")

            for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
                canvas.create_text(target_center[0]+dx, target_center[1]-(radius2+(radius1-radius2)/2)+dy, text=points[i], fill="cyan", font=("Arial", 50, "bold"),tags="target")

            canvas.create_text(target_center[0], target_center[1]-(radius2+(radius1-radius2)/2), text=points[i], fill="black", font=("Arial", 50, "bold"), tags="target")
        else:    
            radius1 = (target_rings - i) * ring_step
            color = "black"
            canvas.create_oval(
                x - radius1, y - radius1,
                x + radius1, y + radius1,
                fill=color, outline="cyan", width=3, tags="target"
            
            )
    for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
        canvas.create_text(target_center[0]+dx, target_center[1]+dy, text="100", fill="cyan", font=("Arial", 50, "bold"),tags="target")
    canvas.create_text(target_center[0], target_center[1], text="100", fill="black", font=("Arial", 50, "bold"), tags="target")

    if game_mode==3 or game_mode==2:
        for i in range(len(shotsx)):
            if shotsx[i] and shotsy[i]:
                canvas.create_oval(
                shotsx[i] - 10, shotsy[i] - 10,
                shotsx[i] + 10, shotsy[i] + 10,
                fill="chartreuse2", outline="chartreuse2", tags="target"
            )

def batterie(canvas):
    # Functions as an Ammonition counter 
    canvas.create_rectangle(startpoint[0], startpoint[1], endpoint[0], endpoint[1],
                            fill="lawngreen", tags="batt")
    canvas.create_rectangle(startpoint[0] + distanz, startpoint[1] + distanz,
                            endpoint[0] - distanz, endpoint[1] - distanz,
                            fill="black", tags="batt")

    points = []
    for g in range(rounds):
        x_offset = startpoint[0] + distanz * 2 + g * (length + distanz)
        top_y = startpoint[1] + distanz * 2
        bottom_y = endpoint[1] - distanz * 2

        if g == 0:
            trapezoid = [
                x_offset, top_y,
                x_offset + length, top_y,
                x_offset + length - versatz, bottom_y,
                x_offset, bottom_y
            ]
        elif g == rounds-1:
            trapezoid = [
                x_offset, top_y,
                x_offset + length - distanz, top_y,
                x_offset + length - distanz, bottom_y,
                x_offset - versatz , bottom_y
            ]
        else:
            trapezoid = [
                x_offset, top_y,
                x_offset + length, top_y,
                x_offset + length - versatz, bottom_y,
                x_offset - versatz, bottom_y
            ]

        points.append(trapezoid)
        canvas.create_polygon(trapezoid, fill="lawngreen", tags=f"batt{g+1}")


#  HIT PROCESSING

def game_hit(canvas, x, y):
    """
    Called whenever a shot is detected.

    Computes:
        - distance to target center
        - score based on ring hit
        - missed handling
        - hit marker on screen

    """

    global score, shotsx, shotsy, target_center
    global target_visible, step, last_hide_time
    global missed_rounds, shots, rbs

    # Distance from target center
    r = math.hypot(x - target_center[0], y - target_center[1])
    rbs += 1

    # Miss conditions
    if r >= ring_step * 5 or (not target_visible and (time.time() - last_hide_time) > 0.1):
        # Draw miss mark
        canvas.create_oval(x-10, y-10, x+10, y+10,
                           fill="chartreuse2", outline="chartreuse2", tags="miss")
        score += 0
        missed_rounds += 1
        return

    # hit conditions
    shots += 1

    # Scoring by ring distances
    if r <= ring_step:
        score += points[4]
    elif r <= ring_step * 2:
        score += points[3]
    elif r <= ring_step * 3:
        score += points[2]
    elif r <= ring_step * 4:
        score += points[1]
    elif r <= ring_step * 5:
        score += points[0]

    # If target is hidden , do not draw hit point
    if (time.time() - last_hide_time) < 0.1:
        pass
    else:
        canvas.create_oval(x-10, y-10, x+10, y+10,
                           fill="chartreuse2", outline="chartreuse2", tags="target")

    # Save hit for redraw in moving-target modes
    shotsx.append(x)
    shotsy.append(y)

#  Battery — mark missed shots (mode 3)
def mark_missed_battery():

    global missed_rounds, rounds, canvas, mrc

    missed_rounds += 1

    if missed_rounds <= rounds:
        tag = f"batt{mrc}"
        canvas.itemconfig(tag, fill="gray")  # turn segment gray
        mrc += 1


#  TARGET MOVEMENT 

def tp_target():
    # Teleports the target for gamemode 2 & 3
    global target_center, canvas, shotsx,shotsy
    margin = ring_step * target_rings
    new_x = random.randint(60+margin, canvas_width - 60 - margin)
    new_y = random.randint(60+margin, canvas_height - 140 - margin)
    dx = new_x - target_center[0]
    dy = new_y - target_center[1]
    for i in range(len(shotsx)):
        shotsx[i]=shotsx[i]+dx
        shotsy[i]=shotsy[i]+dy
    canvas.move("target", dx, dy)
    target_center = (new_x, new_y)

def hide_target():
    global target_visible, last_hide_time, round_count, game_mode, running, missed_rounds
    target_visible = False
    last_hide_time = time.time()  # record when it was hidden

    if game_mode == 3 and running:
        round_count += 1
        def check_missed():
            # Only mark missed if no shot occurred for this round
            if len(shotsx) < round_count and (len(shotsx) + missed_rounds) < round_count:
                mark_missed_battery()

        root.after(200, check_missed)  # 200 ms = 0.2 seconds

    canvas.delete("target")
    root.update()


def show_target():
    global target_visible, free,target_center
    target_visible = True
    free = True
    draw_target(*target_center)

def hide_and_move_target():
    hide_target()
    root.after(target_hide_time, move_and_show_target)

def move_and_show_target():
    global round_count, rounds
    if round_count<= rounds:
        tp_target()
    show_target()


def auto_move_target(Name):
    # loops the functions for gamemode 2 & 3
    global round_count, rounds, running, shots, missed_rounds

    if not running:
        return

    # Stop if all rounds (target appearances) are complete
    if round_count >= rounds and game_mode == 3 :
        print("All rounds complete (Hard+ mode).")
        hide_and_move_target()
        running = False
        with open(protocol_path, "a") as proto_file:
            proto_file.write("\nend")
        ser.close()
        game_end(canvas, Name)  # or pass current Name variable
        return
    
    hide_and_move_target()
    root.after(move_interval, lambda: auto_move_target(Name))


# ------------------- USER INTERFACE -------------------

def show_leaderboard(canvas):
    """
    Displays the leaderboard on the monitor canvas.
    Loads entries from leaderboard_path and filters them by the
    current Gamemode

    """
    # Leaderboard with the best scores from each gamemode 
    global leaderboard_size
    
    canvas.delete("target","batt")
    Emblem()
    try:
        with open(leaderboard_path, "r") as f:
            lines_raw = [line.strip() for line in f if "," in line]

        entries = []
        for line in lines_raw:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 3:
                name, score_str, gm_str = parts
                try:
                    score = int(score_str)
                    gamemode = int(gm_str)
                    entries.append((name, score, gamemode))
                except ValueError:
                    print(f"Skipping invalid line: {line}")
            else:
                print(f"Skipping malformed line: {line}")

        filtered = [entry for entry in entries if entry[2] == game_mode or entry[2]==5]

        if not filtered:
            print(f"No leaderboard entries for Game Mode {game_mode}.")
            canvas.create_text(
                canvas_width / 2,
                canvas_height / 2,
                text=f"No scores yet for Game Mode {game_mode}",
                fill="white",
                font=("Arial", 60, "bold"),
                tags="target"
            )
            return

        filtered.sort(key=lambda x: x[1], reverse=True)

        top = filtered[:leaderboard_size]

        canvas.create_text(
            canvas_width / 2,
            80,
            text=f"LEADERBOARD - MODE {game_mode}",
            fill="white",
            font=("Arial", 50, "bold"),
            tags="target"
        )

        y = 190

        for i, (name, score, gamemode) in enumerate(top, start=1):
            if i == 1:
                color = "gold"; size = 95
            elif i == 2:
                color = "silver"; size = 80
            elif i == 3:
                color ="#cd7f32"; size = 65  
            else:
                color = "white"; size = 50

            # Draw leaderboard entry
            canvas.create_text(
                canvas_width / 2,
                y,
                text=f"{i}# {name}: {score}",
                fill=color,
                font=("Arial", size, "bold"),
                tags="target"
            )

            y += size + 35

    except FileNotFoundError:
        print("Leaderboard file not found.")
        canvas.create_text(
            canvas_width / 2,
            canvas_height / 2,
            text="Leaderboard file not found.",
            fill="red",
            font=("Arial", 50, "bold"),
            tags="target"
        )
    except Exception as e:
        print("Error loading leaderboard:", e)

def save_score(name, score):
    """
    Appends a new score entry to the leaderboard file.

    """
    global game_mode
    print("Name saved:",name)
    with open(leaderboard_path, "a") as f:
        f.write(f"\n{name},{score},{game_mode}")

def change_path():
    """
    Opens console UI to change file paths:
        1 = protocol_path
        2 = coords_path
        3 = leaderboard_path

    """

    global protocol_path, coords_path, leaderboard_path

    print("\nWhich path do you want to change?")
    print("1 = protocol_path")
    print("2 = coords_path")
    print("3 = leaderboard_path")
    choice = input("\nSelect (1/2/3): ").strip()

    if choice not in {"1", "2", "3"}:
        print("Invalid selection.")
        return

    new_path = input("Enter new full path:\n").strip()

    # Validate directory

    directory = os.path.dirname(new_path)

    if not os.path.isdir(directory):
        print("ERROR: Directory does not exist!")
        return

    if choice == "1":
        protocol_path = new_path
        print(f"protocol_path updated to:\n{protocol_path}")

    elif choice == "2":
        coords_path = new_path
        print(f"coords_path updated to:\n{coords_path}")

    elif choice == "3":
        leaderboard_path = new_path
        print(f"leaderboard_path updated to:\n{leaderboard_path}")


def save_name():
    Name=input("\nEnter Name: ").strip().lower()
    if Name:
        save_score(Name, score)

def coords():

    print(f"ROI: {roi}\n")
    print("Sorted blobs:")
    for i, b in enumerate(["Top-Left", "Top-Mid", "Top-Right","Bottom-Left", "Bottom-Mid", "Bottom-Right"]):
        print(f"{b}: {blob[i]}")

    if matrix is None:
        print("Matrix not yet computed. Run calibration first.")
    else:
        print("\nMatrix: ",matrix)

def Credits():

    canvas.create_text(
        target_center[0], target_center[1] - 100,
        text="Created by:", fill="DarkGoldenrod3",
        font=("Arial", 100, "bold"), tags="target"
    )

    canvas.create_text(
        target_center[0], target_center[1] + 100,
        text="J.F", fill="DarkGoldenrod3", 
        font=("Arial", 100, "bold"), tags="target"
    )
    Emblem()

def Emblem():

    edge = [canvas_width-200, canvas_height - 300]
    t = [
        edge[0] + 12*1, edge[1] + 12*1,
        edge[0] + 12*6, edge[1] + 12*6,
        edge[0] + 12*6, edge[1] + 12*14,
        edge[0] + 12*7, edge[1] + 12*15,
        edge[0] + 12*9, edge[1] + 12*15,
        edge[0] + 12*10, edge[1] + 12*14,
        edge[0] + 12*10, edge[1] + 12*6,
        edge[0] + 12*15, edge[1] + 12*1
    ]
    canvas.create_polygon(t, fill="DarkGoldenrod2", tags="target")

    II1=[
        edge[0] + 12*14, edge[1] + 12*3,
        edge[0] + 12*11, edge[1] + 12*6,
        edge[0] + 12*11, edge[1] + 12*15,
        edge[0] + 12*14, edge[1] + 12*12
    ]
    II2=[
        edge[0] + 12*2, edge[1] + 12*3,
        edge[0] + 12*5, edge[1] + 12*6,
        edge[0] + 12*5, edge[1] + 12*15,
        edge[0] + 12*2, edge[1] + 12*12
    ]
    canvas.create_polygon(II1, fill="DarkGoldenrod3", tags="target")
    canvas.create_polygon(II2, fill="DarkGoldenrod3", tags="target")

def game_end(canvas, Name):
    """
    Called after all rounds or target sequences finish.
    Responsibilities:
        - Stop game
        - Reset flags and counters
        - Move target back to center
        - Clear hits and shot markers
        - After 3 seconds: show_results()

    """

    global running, START, target_center, target_visible
    global shots, shotsx, shotsy, score
    global hold, temp_center, missed_rounds, mrc, rbs

    running = False
    START = True
    target_visible = True
    hold = False

    missed_rounds = 0
    mrc = 0
    rbs = 0

    # Store old position and move target back to center
    temp_center = target_center
    target_center = (canvas_width//2, canvas_height//2 - 50)

    dx = target_center[0] - temp_center[0]
    dy = target_center[1] - temp_center[1]

    # Shift all shot markers visually back to center
    for i in range(len(shotsx)):
        shotsx[i] += dx
        shotsy[i] += dy

    shots = 0

    # Draw new center target
    show_target()

    # Clear historical shots
    shotsx.clear()
    shotsy.clear()

    # Show score after delay
    root.after(3000, lambda: show_results(canvas, Name))

def show_results(canvas,Name):
    """
    Displays the final score.
    Automatically saves result to leaderboard.
    After 5 seconds the leaderboard appears.

    """
    canvas.delete("miss", "target","speed","batt")
    for i in range (rounds+1):
        canvas.delete(f"batt{i}")
    canvas.create_text(target_center[0], target_center[1]-220,
                       text= Name.upper(), fill="white", font=("Arial", 140, "bold"), tags="target")
    canvas.create_text(target_center[0], target_center[1],
                       text="YOUR SCORE IS", fill="white", font=("Arial", 140, "bold"), tags="target")
    canvas.create_text(target_center[0], target_center[1]+220,
                       text=score, fill="white", font=("Arial", 140, "bold"), tags="target")
    save_score(Name, score)
    print("\nEnter command:   ")
    root.after(5000, lambda: show_leaderboard(canvas))


# ------------------- MAIN LOOP -------------------
def main():
    """
    The central supervisory loop of the entire application.
    Runs continuously and handles console commands while the Tkinter
    GUI is operating. This allows the user to:

        - Start games
        - Toggle calibration
        - Change game mode
        - Edit file paths
        - Display leaderboard / credits
        - View coords, matrix, or protocol
        - Quit safely

    The loop remains active until the user enters 'quit' or closes
    the Tkinter window.

    Responsibilities:
    -----------------
    1. Poll terminal input for user commands.
    2. Update flags that control the GUI loop (running, START, calibrate etc.).
    3. Manage game launch (name input + calling game_start_UI()).
    4. Maintain safe cleanup (camera + serial + window).

    """
        
    global root, canvas, matrix, transform_type, score, adminmode, rounds, player, length, game_mode, serial_port,first,hold

    print("\n\nAvailable commands: \033[93mmonitor\033[0m, \033[93mstart\033[0m, \033[93mcalib\033[0m, \033[93mend\033[0m, \033[93mexit\033[0m, \033[93mscore\033[0m, \033[93mcoords\033[0m\n\nFor an explaination of these commands please enter \033[93m`help´\033[0m into the Console")
    while True:
        try:
            cmd = input("\nEnter command:\n").strip().lower()
            if cmd in {"exit", "end", "coords"}:
                with open(protocol_path, "a") as proto_file:
                    proto_file.write("\n" + cmd)

            if cmd == "monitor":
                monitor_create()
                if adminmode==True:  
                    monitor_setup(canvas, canvas_width, canvas_height, radius)

            elif cmd == "start":
                canvas.delete("target")
                Name=None
                if canvas is None:
                    print("Please open the monitor first (type 'monitor').")
                else:
                    name=input("\nEnter Name: ").strip().lower()
                    if name=="---":
                        Name=f"Player_{player}"
                        player += 1
                    else:
                        Name=name
                    score=0
                    round_start(rounds,cmd,Name)

            elif cmd == "":
                if first:
                    print("want to activate auto modus?")
                    automode=input("\n<y or n>\n")
                    if automode == "y":
                        first=False
                        canvas.delete("target")
                        Name=None
                        if canvas is None:
                            print("Please open the monitor first (type 'monitor').")
                        else:
                            Name=f"Player_{player}"
                            player += 1
                            score=0
                            round_start(rounds,"start",Name)
                            hold=True
                    else:
                        pass
                elif not hold:
                    canvas.delete("target")
                    Name=None
                    if canvas is None:
                        print("Please open the monitor first (type 'monitor').")
                    else:
                        Name=f"Player_{player}"
                        player += 1
                        score=0
                        round_start(rounds,"start",Name)
                        hold = True

            elif cmd == "path":
                change_path()

            elif cmd == "port":
                global serial_port
                new_port = input("\nEnter Port Number: ").strip()

                if new_port.isdigit():
                    serial_port = f"COM{new_port}"
                    print(f"New serial port set to {serial_port}")
                else:
                    print("Invalid input. Please enter a numeric COM port number")

            elif cmd == "calib":
                
                monitor_setup(canvas, canvas_width, canvas_height, radius)
                calibration(cmd)
                matrix, transform_type = correction(radius)
                canvas.delete("Calib")

            elif cmd == "score":
                show_leaderboard(canvas)
                
            elif cmd == "coords":
                coords()

            elif cmd.startswith("gamemode"):
                global game_mode
                parts = cmd.split()
                if len(parts) == 2 and parts[1].isdigit():
                    game_mode = int(parts[1])
                    print("Gamemode set to:", game_mode)
                else:
                    print("Usage: gamemode <1 or 2>")

            elif cmd.startswith("rounds"):
                if adminmode == True:
                    parts = cmd.split()
                    if len(parts) == 2 and parts[1].isdigit():
                        rounds = int(parts[1])
                        length = int((length_x - (2 * distanz)) / rounds - distanz)

                        print(f"Rounds set to {rounds}")
                    else:
                        print("Usage: rounds <number>")
                else:
                    print("Only admin can change number of rounds.")
            
            elif cmd == "exit":
                print("Exiting program.")
                if root:
                    root.destroy()
                break

            elif cmd == "admin":
                adminmode = not adminmode
                print("Enter Adminmode")

            elif cmd == "help":
                print("\n\033[96mAvailable Commands:\033[0m")
                print("────────────────────────────────────────────")

                print("\033[93mmonitor\033[0m")
                print("  Opens the game window (the target monitor). Required before starting or calibrating.\n")

                print("\033[93mstart\033[0m")
                print("  Starts a new game round and allows to enter a player name (for a Player-name use `---´).\n")

                print("\033[93mcalib\033[0m")
                print("  Shows 6 calibration circles and begins camera calibration.\n")

                print("\033[93m<ENTER> (empty command)\033[0m")
                print("  Starts the next player automatically by pressing <ENTER> after first activation.\n")

                print("\033[93mcoords\033[0m")
                print("  Shows blob coordinates, ROI, and the transformation matrix.\n")

                print("\033[93mport\033[0m")
                print("  Change the COM port (e.g. enter 7 for COM7).\n")

                print("\033[93mpath\033[0m")
                print("  Change file paths used by the system:")
                print("    1 = protocol_path")
                print("    2 = coords_path")
                print("    3 = leaderboard_path\n")

                print("\033[93mscore\033[0m")
                print("  Displays the leaderboard for the current game mode.\n")

                print("\033[93mgamemode <1–4>\033[0m")
                print("  Sets difficulty mode:")
                print("    1 = Easy")
                print("    2 = Medium (hide + move)")
                print("    3 = Hard (timed appearances)\n")

                print("\033[93mend\033[0m")
                print("  Sends 'end' to the camera detection program.\n")

                print("\033[93mexit\033[0m")
                print("  Closes the program and GUI.\n")

                print("────────────────────────────────────────────")


            else:
                print("Unknown command:", cmd)

        except Exception as e:
            print("Error:", e)

# ------------------- RUN -------------------
if __name__ == "__main__":
    main()
