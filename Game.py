import serial
import time
import tkinter as tk
import cv2
import numpy as np
import math
import random


# ------------------- CONFIG -------------------
SERIAL_PORT = "COM7"
BAUD_RATE = 9600
protocol_path = r"E:\protocol.txt"
coords_path = r"E:\coords.txt"
canvas_width = 1600
canvas_height = 1200
rounds= 6
length_x = 400
length_y = 200
edge_x = 50
edge_y = 100
distanz = 5
versatz = 20
leaderboard_size= 10

# Game 
TARGET_COLORS = ["black", "black", "black", "black", "black"]
TARGET_RINGS = 5
MOVE_INTERVAL = 1500  # ms between target moves
ring_step = 90

# Globals
root = None
canvas = None
ser = None
round_count = 0

# Variables
Blob = [None] * 6
radius = 75
A = None
transform_type = None
corr_l_x = 0
corr_l_y = 0
roi = None
length = int((length_x - (2 * distanz)) / rounds - distanz)
startpoint = [edge_x, canvas_height - edge_y - length_y]
endpoint = [startpoint[0] + length_x, startpoint[1] + length_y]
adminmode=False
Player=1

# Game State
points=[20,40,60,80]
score = 0
shots = 0
target_center = (canvas_width//2, canvas_height//2-50)
running = True
# ------------------- CALIBRATION -------------------
def calibration(cmd):
    global Blob, ser, corr_l_x, corr_l_y, roi
    Blob = []  # reset
    #print("test")

    if ser and ser.is_open:
        ser.close()
    time.sleep(0.5)
    #print("test")
    

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"Connected to {SERIAL_PORT} at {BAUD_RATE} baud.")
        with open(protocol_path, "a") as proto_file:
                    proto_file.write("\n" + cmd)
        line = ser.readline()
        msg = line.decode('utf-8').strip()
        print(msg)
        while True:
            line = ser.readline()
            if line:
                msg = line.decode('utf-8').strip()
                if "Blob" in msg and ":" in msg:
                    try:
                        parts = msg.split(":")[1].strip().split(",")
                        x_val = int(parts[0].split("=")[1])
                        y_val = int(parts[1].split("=")[1])
                        Blob.append({'x': x_val, 'y': y_val})
                        if len(Blob) > 6:
                            Blob = Blob[-6:]
                        #print(f"Detected blob: x={x_val}, y={y_val}")
                    except Exception as e:
                        print("Parsing blob error:", e)
                if "ROI" in msg:
                    roi_str = msg.split(":")[1].strip()
                    roi = eval(roi_str)
                    corr_l_x = (canvas_width - 20 - radius) / (roi[2] - roi[0])
                    corr_l_y = (canvas_height - 20 - radius) / (roi[3] - roi[1])
                if msg == "File written.":
                    Blob[:] = sort_blobs_by_position(Blob)
                    #print("\nSorted blobs:")
                    #for i, b in enumerate(["Top-Left", "Top-Mid", "Top-Right","Bottom-Left", "Bottom-Mid", "Bottom-Right"]):
                    #    print(f"{b}: {Blob[i]}")
                    print("Calibration complete.")
                    ser.close()
                    return
                else:
                    #print(msg)
                    pass
            if root:
                root.update()
            time.sleep(0.1)
    except Exception as e:
        print("Calibration serial error:", e)

# ------------------- CORRECTION -------------------
def correction(radius):
    global Blob
    valid_blobs = [b for b in Blob if b is not None]
    if len(valid_blobs) < 4:
        print("Not enough blobs for correction (need at least 4).")
        return None, None
    camera_pts = np.float32([[b['x'], b['y']] for b in valid_blobs])

    # Define 6 corresponding screen points
    screen_pts = np.float32([
        [20 + radius, 20 + radius],                               # TL
        [canvas_width / 2, 20 + radius],                          # TM
        [canvas_width - 20 - radius, 20 + radius],                # TR
        [20 + radius, canvas_height - 100 - radius],              # BL
        [canvas_width / 2, canvas_height - 100 - radius],         # BM
        [canvas_width - 20 - radius, canvas_height - 100 - radius]# BR
    ])

    # Perspective transform for 4+ points
    if len(valid_blobs) >= 4:
        A, _ = cv2.findHomography(camera_pts, screen_pts[:len(valid_blobs)])
        transform_type = "Perspective"
    else:
        print("Unexpected number of blobs.")
        return None, None
    #print(f"{transform_type} transformation matrix:\n{A}")
    return A, transform_type

# ------------------- BLOB SORTING -------------------
def sort_blobs_by_position(blobs):
    if not blobs:
        return [None] * 6
    # Sort top vs bottom
    sorted_by_y = sorted(blobs, key=lambda b: b['y'])
    half = len(sorted_by_y) // 2
    top = sorted(sorted_by_y[:half], key=lambda b: b['x'])
    bottom = sorted(sorted_by_y[half:], key=lambda b: b['x'])
    ordered = [None] * 6
    # TL, TM, TR, BL, BM, BR
    if len(top) >= 1: ordered[0] = top[0]
    if len(top) >= 2: ordered[1] = top[1]
    if len(top) >= 3: ordered[2] = top[2]
    if len(bottom) >= 1: ordered[3] = bottom[0]
    if len(bottom) >= 2: ordered[4] = bottom[1]
    if len(bottom) >= 3: ordered[5] = bottom[2]
    return ordered

# ------------------- ROUND START -------------------
def round_start(rounds,cmd,Name):
    global ser, round_count,canvas
    round_count = 0
    if ser and ser.is_open:
        ser.close()
    time.sleep(0.5)
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
        print(f"Connected to {SERIAL_PORT} at {BAUD_RATE} baud.")
        game_monitor(canvas,canvas_width,canvas_height)
        #canvas.create_text(target_center[0], target_center[1], text="START", fill="lawngreen", font=("Arial", 160, "bold"),tags="START")
        #time.sleep(1000)
        read_serial(rounds,Name)
        
    except Exception as e:
        print("Error opening serial port:", e)

    with open(protocol_path, "a") as proto_file:
        proto_file.write("\n" + cmd)

# ------------------- COORD CORRECTION -------------------
def correct_coords(x_cam, y_cam, A, transform_type):
    pt = np.array([[[x_cam, y_cam]]], dtype=np.float32)
    if transform_type == "Affine":
        pt_corr = cv2.transform(pt, A)
    elif transform_type == "Perspective":
        pt_corr = cv2.perspectiveTransform(pt, A)
    else:
        raise ValueError("Unknown transform type")
    return pt_corr[0][0]

# ------------------- SERIAL READER -------------------
def read_serial(rounds,Name):
    global ser, canvas, round_count, A, transform_type
    if ser is None or not ser.is_open:
        print("Serial port not open.")
        return
    
    try:
        line = ser.readline()
        if line:
            treffer = line.decode('utf-8').strip()
            if "differencing" in treffer:
                print(treffer)
                #canvas.create_text(target_center[0], target_center[1], text="START", fill="black", outline="cyan", font=("Arial", 160, "bold"),tags="START")

                for dx, dy in [(-2,0), (2,0), (0,-2), (0,2)]:
                    canvas.create_text(target_center[0]+dx, target_center[1]+dy, text="START", fill="cyan", font=("Arial", 160, "bold"),tags="START")

                    # Draw main text in black
                canvas.create_text(target_center[0], target_center[1], text="START", fill="black", font=("Arial", 160, "bold"), tags="START")
            elif "X" in treffer and "Y" in treffer:
                try:
                    canvas.delete("START")
                    parts = treffer.split("#")
                    hit_x = int(parts[0].split(":")[1])
                    hit_y = int(parts[1].split(":")[1])
                    #print(f"Hit coordinates: X={hit_x}, Y={hit_y}")

                    if A is not None and transform_type is not None:
                        x_corr, y_corr = correct_coords(hit_x, hit_y, A, transform_type)
                        if canvas:
                            game_hit(canvas, x_corr, y_corr)
                            canvas.delete(f"batt{rounds-round_count}")
                            root.update()
                    else:
                        print("Transform not computed yet. Run calibration first.")

                    round_count += 1
                    if round_count >= rounds:
                        print("All rounds complete.")
                        with open(protocol_path, "a") as proto_file:
                            proto_file.write("\nend")
                        ser.close()
                        game_end(canvas,Name)
                        return

                except Exception as e:
                    print("Parsing error:", e)
            elif treffer=="":
                pass
            else:
                print(treffer)
        root.after(100, lambda: read_serial(rounds,Name))

    except serial.SerialException as e:
        print("Serial error:", e)
        if ser and ser.is_open:
            ser.close()

# ------------------- GUI -------------------
def monitor_create():
    global root, canvas

    root = tk.Tk()
    root.title("Six Blob Calibration Display")
    canvas = tk.Canvas(root, width=canvas_width, height=canvas_height, bg="black")
    canvas.pack()
    
    root.update()
    print("Monitor window created.")
    return root, canvas

def monitor_setup(canvas, width, height, radius):
    try:
        canvas.delete("target")
        canvas.delete("START")
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

def game_monitor(canvas,width,height):
    global score
    draw_target(*target_center)
    #score=0
    batterie(canvas, height, width)


def draw_target(x, y):
    canvas.delete("target")
    for i in range(rounds):
        canvas.delete(f"batt{i+1}")
    for i in range(TARGET_RINGS):
        if i != TARGET_RINGS - 1:
            radius1 = (TARGET_RINGS - i) * ring_step
            radius2 = (TARGET_RINGS-(i+1)) * ring_step
            color = TARGET_COLORS[i % len(TARGET_COLORS)]
            canvas.create_oval(
                x - radius1, y - radius1,
                x + radius1, y + radius1,
                fill=color, outline="cyan", width=3, tags="target"
            
            )
            for dx, dy in [(-2,0), (2,0), (0,-2), (0,2)]:
                canvas.create_text(target_center[0]+dx, target_center[1]+(radius2+(radius1-radius2)/2)+dy, text=points[i], fill="cyan", font=("Arial", 50, "bold"),tags="target")

                        # Draw main text in black
            canvas.create_text(target_center[0], target_center[1]+(radius2+(radius1-radius2)/2), text=points[i], fill="black", font=("Arial", 50, "bold"), tags="target")
            for dx, dy in [(-2,0), (2,0), (0,-2), (0,2)]:
                canvas.create_text(target_center[0]+dx, target_center[1]-(radius2+(radius1-radius2)/2)+dy, text=points[i], fill="cyan", font=("Arial", 50, "bold"),tags="target")

                        # Draw main text in black
            canvas.create_text(target_center[0], target_center[1]-(radius2+(radius1-radius2)/2), text=points[i], fill="black", font=("Arial", 50, "bold"), tags="target")
        else:    
            radius1 = (TARGET_RINGS - i) * ring_step
            color = TARGET_COLORS[i % len(TARGET_COLORS)]
            canvas.create_oval(
                x - radius1, y - radius1,
                x + radius1, y + radius1,
                fill=color, outline="cyan", width=3, tags="target"
            
            )
    print("test")
    for dx, dy in [(-2,0), (2,0), (0,-2), (0,2)]:
        canvas.create_text(target_center[0]+dx, target_center[1]+dy, text="100", fill="cyan", font=("Arial", 50, "bold"),tags="target")
                    # Draw main text in black
    canvas.create_text(target_center[0], target_center[1], text="100", fill="black", font=("Arial", 50, "bold"), tags="target")

def batterie(canvas, height, width):
    canvas.create_rectangle(startpoint[0], startpoint[1], endpoint[0], endpoint[1],
                            fill="lawngreen", tags="target")
    canvas.create_rectangle(startpoint[0] + distanz, startpoint[1] + distanz,
                            endpoint[0] - distanz, endpoint[1] - distanz,
                            fill="black", tags="target")

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
        #print(f"batt{g+1}")

def game_hit(canvas, hit_x, hit_y):
    global score
    #print(hit_x,hit_y)
    canvas.create_oval(hit_x-10, hit_y-10, hit_x+10, hit_y+10, fill="lawngreen", outline="lawngreen",tags="target")
    #print(hit_x,hit_y)
    dx = hit_x - target_center[0]
    dy = hit_y - target_center[1]
    dist = math.sqrt(dx*dx + dy*dy)

    # Scoring based on proximity
    if dist < ring_step:
        points = 100
        color = "black"
    elif dist < ring_step*2:
        points = 80
        color = "black"
    elif dist < ring_step*3:
        points = 60
        color = "black"
    elif dist < ring_step*4:
        points = 40
        color = "black"
    elif dist < ring_step*5:
        points = 20
        color = "black"
    else:
        points = 0
        color = "black"

    # Draw hit marker
    score=score+points
    #print(score)
    #if points > 0:
    #    canvas.create_text(hit_x, hit_y-15, text=f"+{points}", fill="lawngreen", font=("Arial", 14, "bold"),tags="target")
    #else:
    #    canvas.create_text(hit_x, hit_y-15, text="MISS", fill="lawngreen", font=("Arial", 12, "bold"),tags="target")


def show_leaderboard(canvas):
    global leaderboard_size
    
    canvas.delete("target")
    try:
        with open(r"D:\FJN_2025-26\Project_Han_Solo\leaderboard.txt", "r") as f:
            lines = [line.strip().split(",") for line in f if "," in line]

        # Sort by score descending
        lines.sort(key=lambda x: int(x[1]), reverse=True)

        # Keep only top N entries
        top = lines[:leaderboard_size]

        # Starting y position and spacing
        y = canvas_height / (leaderboard_size+2)+25

        for i, (name, score) in enumerate(top, start=1):
            # Choose color based on rank
            if i == 1:
                color = "gold"
                size = 95
            elif i == 2:
                color = "silver"
                size = 80
            elif i == 3:
                color = "#cd7f32"  # bronze hex color
                size=65
            else:
                color = "white"
                size=50

            # Draw leaderboard entry
            canvas.create_text(
                canvas_width / 2,
                y,
                text=f"{i}# {name}: {score}",
                fill=color,
                font=("Arial", size, "bold"),
                tags="target"
            )
            if i == 1:
                y+=130
            elif i == 2:
                y+= 120
            elif i == 3:
                y+= 110
            else:
                y+= 90
            

    except FileNotFoundError:
        print("Leaderboard file not found.")
    except Exception as e:
        print("Error loading leaderboard:", e)

def save_score(name, score):
    print("name saved",name)
    with open(r"D:\FJN_2025-26\Project_Han_Solo\leaderboard.txt", "a") as f:
        f.write(f"\n{name},{score}")


def save_name():
    Name=input("\nEnter Name: ").strip().lower()
    if Name:
        save_score(Name, score)
        show_leaderboard(canvas)
        print("\nEnter command: ")

def coords():
    print(f"ROI: {roi}\n")
    print("Sorted blobs:")
    for i, b in enumerate(["Top-Left", "Top-Mid", "Top-Right","Bottom-Left", "Bottom-Mid", "Bottom-Right"]):
        print(f"{b}: {Blob[i]}")
    print("\nMatrix: ",A)

def game_end (canvas,Name):
    time.sleep(3)
    canvas.delete("target")
    canvas.create_text(target_center[0], target_center[1]-100, text="YOUR SCORE IS", fill="white", font=("Arial", 140, "bold"),tags="target")
    canvas.create_text(target_center[0], target_center[1]+100, text=score, fill="white", font=("Arial", 140, "bold"),tags="target")
    root.update()
    #Name=input("\nEnter Name: ").strip().lower()
    #print("\n\n\n\nEnter Name")
    #save_name()
    save_score(Name,score)
    time.sleep(5)
    show_leaderboard(canvas)
    print("\nEnter command: ")


# ------------------- MAIN LOOP -------------------
def main():
    global root, canvas, A, transform_type, score, adminmode, rounds, Player, length
    print("Available commands: monitor, start, calib, end, exit, score, coords\n","for an explaination of these commands please enter ´help` into the Console")
    while True:
        try:
            cmd = input("\nEnter command: ").strip().lower()
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
                        Name=f"Player_{Player}"
                        Player += Player
                    else:
                        Name=name
                    score=0
                    round_start(rounds,cmd,Name)

                    

            elif cmd == "calib":
                
                monitor_setup(canvas, canvas_width, canvas_height, radius)
                calibration(cmd)
                A, transform_type = correction(radius)
                canvas.delete("Calib")

            elif cmd == "score":
                show_leaderboard(canvas)
                
            elif cmd == "coords":
                coords()

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
                print("\033[93mmonitor\033[0m  : Opens the main game display window (the target monitor).")
                print("           Required before starting or calibrating.\n")
                print("\033[93mstart\033[0m    : Starts a new shooting round. Prompts for player name.\n")
                print("\033[93mcalib\033[0m    : Runs calibration with six visible reference points.\n")
                print("\033[93mscore\033[0m    : Displays the current leaderboard.\n")
                print("\033[93mcoords\033[0m   : Prints ROI, blob positions, and transformation matrix.\n")
                print("\033[93mexit\033[0m     : Safely exits the program and closes the GUI.\n")
                print("\033[93mend\033[0m      : Sends an 'end' command to stop the decetion program on the camera (only necessary if the start program needs to be interuped).\n")
                print("────────────────────────────────────────────")
            else:
                print("Unknown command:", cmd)

        except Exception as e:
            print("Error:", e)

# ------------------- RUN -------------------
if __name__ == "__main__":
    main()
