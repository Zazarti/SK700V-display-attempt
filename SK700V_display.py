import hid
from PyLibreHardwareMonitor import Computer
import time
import struct
import traceback

VENDOR_ID = 0x381C 
PRODUCT_ID = 0x0003

# Smoothing factor (0.1 = very smooth/slow, 0.9 = very reactive/fast)
ALPHA = 0.6 

def run_utility():
    device = None
    print("Initializing LibreHardwareMonitor...")
    
    try:
        computer = Computer()
        computer.CPUEnabled = True

        smoothed_freq = 0.0
        
        # Initialize HID Device
        try:
            device = hid.device()
            device.open(VENDOR_ID, PRODUCT_ID)
            print(f"Connected to cooler: {device.get_product_string()}")
        except Exception as e:
            print(f"Hardware Monitor Error: {e}")
            return

        print("Monitoring CPU... (Press Ctrl+C to stop)")
    
        while True:
            cpu_dict = computer.cpu           
            if not cpu_dict:
                time.sleep(1)
                continue

            cpu_name = list(cpu_dict.keys())[0]
            data_map = cpu_dict[cpu_name]

            # Extraction
            temp = data_map.get('Temperature', {}).get('Core (Tctl/Tdie)', 0)
            usage = data_map.get('Load', {}).get('CPU Total', 0)
            power_w = data_map.get('Power', {}).get('Package', 0)

            # 1. Safely extract the CPU clocks
            clocks = data_map.get('Clock', {})
            
            # 2. Get the maximum frequency across all cores (default to 0 if none found)
            if clocks:
                raw_freq = max(clocks.values())
            else:
                raw_freq = 0.0

            # 3. Calculate the smoothed frequency without square brackets around ALPHA
            # Note: We assign this back to 'smoothed_freq' instead of 'freq' so it 
            # remembers the value for the next loop, and matches your f_bytes code below!
            smoothed_freq = (ALPHA * raw_freq) + ((1 - ALPHA) * smoothed_freq)
            
            # --- Packet Construction ---
            data = [0] * 64
            data[0:7] = [16, 104, 1, 4, 13, 1, 2]
                
            #Some scaling happens with byte 7
            data[7] = 0
            p_bytes = int(power_w).to_bytes(2, 'little')
            data[8], data[9] = p_bytes[0], p_bytes[1]
          
            # Temp
            data[10] = 0  # Note: This contains the Celsius flag
            temp_bytes = struct.pack('>f', float(temp))
            data[11:15] = list(temp_bytes)

            # Usage
            data[15] = int(usage)

            # Frequency
            f_bytes = int(smoothed_freq).to_bytes(2, 'big')
            data[16], data[17] = f_bytes[0], f_bytes[1]

            # Checksum
            data[18] = sum(data[1:18]) % 256
            data[19] = 22

            device.write(data)
            
            print(f"Freq: {smoothed_freq:.1f}MHz | Temp: {temp:.1f}°C | Load: {usage:.1f}% | Power: {power_w:.1f}W ", end='\r')
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception:
        traceback.print_exc()
    finally:
        if device:
            device.close()

if __name__ == "__main__":
    run_utility()
