# SK700V-display
Python script *for Windows* to enable and feed CPU monitoring data to SK700V cooler display, a HID device.

Manufacturer control software is a large (1.5GB) electron app and does not do much. This does less but is only a few lines.

## ⚠️ Use at your own risk, this is unsupported software ⚠️

## Pre requisite
Python. We use hidapi, but most importantly LibreHardwareMonitor.

python -m pip install PyLibreHardwareMonitor hidapi --user

## Usage

Copy the python file in a folder like ~\Python Scripts\ and launch it in an Administrator command: python .\SK700V_display.py

# Run automatically

Setup a new task in Task Scheduler: Configure for Windows 10, Run with highest privileges, Triggers At Log On, Uncheck "Stop the task if it runs longer than".

Action: "Start a program"

Program: locate your local pythonw.exe binary

Arguments: your script file with its full path ("C:\Users\...\Python Scripts\SK700V_display.py")

Starts in: the containing folder

