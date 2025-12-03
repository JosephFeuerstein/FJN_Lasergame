# FJN_Lasergame
A game i programmed for my FJN. You shoot a laser on a Monitor, this laser is detected by a camera (in my case a Openmv Cam H7)


## --- Setup ---
### List of Materials

OpenMV Cam (code made for model H7)

USB cable (for the camera)

Monitor with projection foil (for better detection of the laser)
(Alternatively, you may be able to use a beamer, but this has not been tested yet)

Laser gun

PC or Laptop

## --Software Setup--

Copy dect.py, calib.py, main.py, as well as protocol.txt and coords.txt onto the camera.

Start Game.py on your PC.

For a more in-depth explanation of the commands, use the help command.

Make sure your paths to the text files are correct
(you can change them with the path command).

## --Display Requirements--

The game is programmed for a 4:3 resolution (1600×1200).
(This may need to be changed depending on your setup.)

## --Initial Setup--

Run the monitor command.

Move the created window onto the monitor with the projection foil.

Make sure it is displayed in full-screen mode.

Run the calibration command.

Choose your game mode (default is Mode 1).

## --Different Game Modes--

Easy – static target

Medium – target hides + moves

Hard – timed target appearances with automatic movement

## --Start the Game--

Use the start command and enjoy!
