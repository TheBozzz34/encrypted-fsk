import numpy as np
import sounddevice as sd
import cryptofunctions

# Configurations (must match transmitter)
fs = 44100           # Sample rate
baud_rate = 40        # symbols/sec
f0 = 1000            # Frequency for 0
f1 = 2000            # Frequency for 1
symbol_len = int(fs / baud_rate)
preamble_bits = 16   # Number of alternating bits for sync
password = ""

# Global variables
bit_buffer = ""
symbol_buffer = np.array([], dtype=np.float32)
byte_buffer = ""
receiving = False
sync_pattern = '01' * (preamble_bits // 2)  # Expected preamble pattern
sync_buffer = ""
signal_threshold = 1000  # Minimum signal strength to consider valid
decoded_buffer = ""  # Move to global scope for better tracking

def list_input_devices():
    print("Available Input Devices:")
    devices = sd.query_devices()
    input_devices = []
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            print(f"{i}: {device['name']}")
            input_devices.append(i)
    return input_devices

def select_input_device():
    input_devices = list_input_devices()
    while True:
        try:
            choice = int(input("Select input device by number: "))
            if choice in input_devices:
                sd.default.device = (choice, None)
                print(f"Selected: {sd.query_devices(choice)['name']}")
                break
            else:
                print("Invalid choice. Try again.")
        except ValueError:
            print("Please enter a number.")

def goertzel(samples, freq, sample_rate):
    """Improved Goertzel algorithm for frequency detection"""
    N = len(samples)
    k = int(0.5 + (N * freq) / sample_rate)
    omega = (2 * np.pi * k) / N
    coeff = 2 * np.cos(omega)
    
    s_prev = 0
    s_prev2 = 0
    
    for sample in samples:
        s = sample + coeff * s_prev - s_prev2
        s_prev2 = s_prev
        s_prev = s
    
    power = s_prev2**2 + s_prev**2 - coeff * s_prev * s_prev2
    return power

def detect_bit(symbol):
    """Detect bit with improved noise handling"""
    power0 = goertzel(symbol, f0, fs)
    power1 = goertzel(symbol, f1, fs)
    
    # Calculate signal strength and ratio
    total_power = power0 + power1
    power_ratio = power1 / power0 if power0 > 0 else float('inf')
    
    # Only process if signal is strong enough
    if total_power < signal_threshold:
        return None, power0, power1
    
    # Determine bit based on power ratio (more robust than simple comparison)
    if power_ratio > 1.5:  # Strong preference for f1
        bit = '1'
    elif power_ratio < 0.67:  # Strong preference for f0 (1/1.5)
        bit = '0'
    else:
        # Ambiguous signal, return None
        return None, power0, power1
    
    return bit, power0, power1

def check_sync():
    """Check if we have a valid sync pattern"""
    global sync_buffer
    if len(sync_buffer) >= len(sync_pattern):
        # Check for sync pattern match
        if sync_buffer[-len(sync_pattern):] == sync_pattern:
            return True
    return False

def reset_receiver_state():
    """Reset all receiver state variables"""
    global bit_buffer, byte_buffer, receiving, sync_buffer, decoded_buffer
    bit_buffer = ""
    byte_buffer = ""
    receiving = False
    sync_buffer = ""
    decoded_buffer = ""
    print("[STATE RESET]")

def decode_audio(indata, frames, time, status):
    global bit_buffer, symbol_buffer, byte_buffer, receiving, sync_buffer
    global password, decoded_buffer

    if status:
        print(f"Audio status: {status}")

    symbol_buffer = np.append(symbol_buffer, indata[:, 0])

    while len(symbol_buffer) >= symbol_len:
        symbol = symbol_buffer[:symbol_len]
        symbol_buffer = symbol_buffer[symbol_len:]

        bit, power0, power1 = detect_bit(symbol)

        if bit is None:
            continue

        # Add bit to sync buffer for pattern detection
        sync_buffer += bit
        if len(sync_buffer) > len(sync_pattern) * 2:
            sync_buffer = sync_buffer[-len(sync_pattern) * 2:]

        # Check for sync pattern
        if not receiving and check_sync():
            print("\n[SYNC DETECTED] - Starting reception")
            bit_buffer = ""
            sync_buffer = ""
            decoded_buffer = ""
            receiving = True
            continue

        if receiving:
            bit_buffer += bit
            print(f"[RAW BIT] {bit} (Buffer: {len(bit_buffer)} bits)")

            # Process Hamming(7,4) blocks
            while len(bit_buffer) >= 7:
                block = bit_buffer[:7]
                bit_buffer = bit_buffer[7:]
                
                try:
                    val = cryptofunctions.hamming_decode_7bit(block)
                    decoded_val = f"{val:04b}"
                    decoded_buffer += decoded_val
                    print(f"[HAMMING] {block} -> {val} -> {decoded_val} (Decoded buffer: {len(decoded_buffer)} bits)")
                except Exception as e:
                    print(f"[ERROR] Hamming decode failed for {block}: {e}")
                    reset_receiver_state()
                    return

            # Process complete bytes from decoded_buffer
            while len(decoded_buffer) >= 8:
                byte_bits = decoded_buffer[:8]
                decoded_buffer = decoded_buffer[8:]

                try:
                    byte_val = int(byte_bits, 2)
                    char = chr(byte_val)
                    print(f"[BYTE] {byte_bits} -> {byte_val} -> {repr(char)}")

                    if char == '\x02':  # STX (Start of Text)
                        byte_buffer = ""
                        print("[STX] Start of Message detected")

                    elif char == '\x03':  # ETX (End of Text)
                        print(f"[ETX] End of Message detected. Buffer content: {repr(byte_buffer)}")
                        
                        if '|' not in byte_buffer:
                            print("[ERROR] CRC delimiter '|' not found in message.")
                            reset_receiver_state()
                            continue

                        try:
                            encrypted_data, crc = byte_buffer.rsplit('|', 1)
                            print(f"[PARSING] Encrypted: {repr(encrypted_data)}, CRC: {repr(crc)}")
                            
                            if not cryptofunctions.verify_crc(encrypted_data, crc):
                                print("[ERROR] CRC check failed.")
                            else:
                                decrypted = cryptofunctions.decrypt(encrypted_data, password)
                                print(f"[RECEIVED MESSAGE]: '{decrypted}' ✅ CRC OK")
                        except Exception as e:
                            print(f"[ERROR] Failed to process message: {e}")
                        
                        # Reset state after processing message
                        reset_receiver_state()

                    else:
                        byte_buffer += char
                        print(f"[DATA] Added '{repr(char)}' to buffer. Buffer: {repr(byte_buffer)}")

                except ValueError as e:
                    print(f"[ERROR] Invalid byte conversion for {byte_bits}: {e}")
                    reset_receiver_state()
                    return

if __name__ == "__main__":
    print("=== FSK Audio Receiver (Enhanced Debug Version) ===")
    
    # Reset global variables
    reset_receiver_state()
    symbol_buffer = np.array([], dtype=np.float32)
    
    print(f"\nConfiguration:")
    print(f"Sample rate: {fs} Hz")
    print(f"Baud rate: {baud_rate} bps")
    print(f"Frequency 0: {f0} Hz") 
    print(f"Frequency 1: {f1} Hz")
    print(f"Samples per bit: {symbol_len}")
    print(f"Signal threshold: {signal_threshold}")
    print(f"Sync pattern: {sync_pattern}")
    
    select_input_device()

    password = input("Enter password for decryption: ")
    if not password:
        print("Password cannot be empty. Exiting.")
        exit(1)
        
    print("\nListening for messages...")
    print("(Press Ctrl+C to stop)\n")
    
    try:
        with sd.InputStream(callback=decode_audio, channels=1, samplerate=fs, blocksize=1024):
            while True:
                sd.sleep(1000)
    except KeyboardInterrupt:
        print("\nStopped.")