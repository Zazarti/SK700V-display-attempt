import hid
from PyLibreHardwareMonitor import Computer
import time
import struct
import traceback
import json
import os
import math

# Default configuration values
DEFAULT_CONFIG = {
    "VENDOR_ID": 0x381C,
    "PRODUCT_ID": 0x0003,
    "ALPHA": 0.6,
    "POLL_RATE": 1.0,
    "RETRY_INTERVAL": 5.0,
    "VERBOSE": True
}

def load_config():
    """
    Loads user configuration from config.json, merges it with defaults, 
    and rigorously validates the resulting parameters.
    """
    config = DEFAULT_CONFIG.copy()
    
    # Resolve config path relative to the script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.json")
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                user_config = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Warning: {config_path} is malformed ({e}). Using default settings.")
            user_config = {}
        
        # Validation: Ensure the JSON root is an object (dictionary)
        if not isinstance(user_config, dict):
            print("Warning: Configuration root must be a JSON object. Using default settings.")
            user_config = {}
        
        # Log warning on unknown configuration keys to surface typos without failing
        unknown_keys = set(user_config.keys()) - set(DEFAULT_CONFIG.keys())
        if unknown_keys:
            print(f"Warning: Unknown configuration key(s) in {config_path} ignored: "
                  + ", ".join(sorted(unknown_keys)))
            
        # Merge defaults with user_config, ignoring unknown keys
        for k, v in user_config.items():
            if k in config:
                config[k] = v
                
        # Strict validation checks on the merged configuration
        if not (isinstance(config["VENDOR_ID"], int) and 0 <= config["VENDOR_ID"] <= 0xFFFF):
            raise ValueError("VENDOR_ID must be a valid 16-bit integer (0-65535).")
        
        if not (isinstance(config["PRODUCT_ID"], int) and 0 <= config["PRODUCT_ID"] <= 0xFFFF):
            raise ValueError("PRODUCT_ID must be a valid 16-bit integer (0-65535).")
            
        if not (isinstance(config["POLL_RATE"], (int, float)) and config["POLL_RATE"] > 0 and math.isfinite(config["POLL_RATE"])):
            raise ValueError("POLL_RATE must be a finite positive number.")
            
        if not (isinstance(config["RETRY_INTERVAL"], (int, float)) and config["RETRY_INTERVAL"] > 0 and math.isfinite(config["RETRY_INTERVAL"])):
            raise ValueError("RETRY_INTERVAL must be a finite positive number.")
            
        if not (isinstance(config["ALPHA"], (int, float)) and math.isfinite(config["ALPHA"]) and 0 < config["ALPHA"] <= 1.0):
            raise ValueError("ALPHA must be a finite number within the range (0, 1].")
            
        if not isinstance(config["VERBOSE"], bool):
            raise ValueError("VERBOSE must be a boolean (true or false).")
    else:
        # Generate the default configuration file if it doesn't exist
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
            
    return config

def run_utility():
    """
    Main loop for hardware monitoring and USB writing.
    """
    print("Loading configuration...")
    try:
        config = load_config()
    except Exception as e:
        print(f"Failed to load configuration: {e}")
        return  # Reject invalid configurations before the monitor starts
        
    print("Initializing LibreHardwareMonitor...")
    try:
        computer = Computer()
        computer.CPUEnabled = True
    except Exception as e:
        print(f"Error initializing hardware monitor: {e}")
        return

    smoothed_freq = 0.0

    print("Monitoring CPU... (Press Ctrl+C to stop)")
    
    # Outer loop handles robust reconnection and self-healing
    while True:
        device = hid.device()
        try:
            # 1. Connection setup
            device.open(config["VENDOR_ID"], config["PRODUCT_ID"])
            
            try:
                # Apply non-blocking or other setup steps
                device.set_nonblocking(1)
            except Exception as setup_e:
                # Close the HID handle immediately if setup fails after opening
                device.close()
                raise setup_e
                
            print("Connected to cooler.")

            # 2. Inner loop handles polling and packet writing
            while True:
                # Refresh hardware monitor data explicitly so readings aren't stale
                if hasattr(computer, 'update'):
                    computer.update()
                elif hasattr(computer, 'Update'):
                    computer.Update()

                cpu_dict = computer.cpu           
                if not cpu_dict:
                    time.sleep(config["POLL_RATE"])
                    continue

                cpu_name = list(cpu_dict.keys())[0]
                data_map = cpu_dict[cpu_name]

                # Extraction
                temp = data_map.get('Temperature', {}).get('Core (Tctl/Tdie)', 0)
                if temp == 0:
                     # Fallback if specific AMD/Intel core sensor name differs
                     temp = data_map.get('Temperature', {}).get('CPU Package', 0)
                     
                usage = data_map.get('Load', {}).get('CPU Total', 0)
                power_w = data_map.get('Power', {}).get('Package', 0)
     
                # Extract frequency natively without WMI
                clocks = data_map.get('Clock', {})
                core_freqs = [v for k, v in clocks.items() if 'Core' in k]
                raw_freq = max(core_freqs) if core_freqs else 0.0

                # Apply Exponential Moving Average (EMA) smoothing
                if smoothed_freq == 0.0:
                    smoothed_freq = raw_freq
                else:
                    smoothed_freq = (config["ALPHA"] * raw_freq) + ((1 - config["ALPHA"]) * smoothed_freq)

                # --- Packet Construction ---
                # 64-byte HID packet mapped via protocol sniffing
                data = [0] * 64
                data[0:7] = [16, 104, 1, 4, 13, 1, 2]
                
                data[7] = 0
                # Aligned power_w to 'big' endian to match frequency and temperature structure
                p_bytes = int(power_w).to_bytes(2, 'big')
                data[8], data[9] = p_bytes[0], p_bytes[1]
              
                data[10] = 0
                temp_bytes = struct.pack('>f', float(temp))
                data[11:15] = list(temp_bytes)

                data[15] = int(usage)

                f_bytes = int(smoothed_freq).to_bytes(2, 'big')
                data[16], data[17] = f_bytes[0], f_bytes[1]

                # End-of-packet Checksum Calculation
                data[18] = sum(data[1:18]) % 256
                data[19] = 22

                try:
                    device.write(data)
                except OSError:
                    # Attempt zero-padded write on specific HID implementations
                    device.write([0x00] + data)

                if config["VERBOSE"]:
                    print(f"Freq: {smoothed_freq:.1f}MHz | Temp: {temp:.1f}°C | Load: {usage:.1f}% | Power: {power_w:.1f}W ", end='\r')
                
                time.sleep(config["POLL_RATE"])

        except KeyboardInterrupt:
            print("\nStopping...")
            break
        except OSError as e:
            # Catch specific I/O device drops, sleeps, and OS-level disconnections
            print(f"\nHID Error/Disconnect: {e}. Retrying in {config['RETRY_INTERVAL']} seconds...")
            time.sleep(config['RETRY_INTERVAL'])
        finally:
            # Unconditionally close the device to guarantee no handle leaks
            device.close()

if __name__ == "__main__":
    run_utility()


