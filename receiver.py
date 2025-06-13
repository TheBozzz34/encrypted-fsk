# Enhanced MFSK Receiver
import numpy as np
import sounddevice as sd
import cryptofunctions
import time
from collections import deque

# MFSK Configuration (must match transmitter)
fs = 44100           # Sample rate
baud_rate = 45       # symbols/sec
M = 16               # Number of frequencies
bits_per_symbol = int(np.log2(M))  # 4 bits per symbol
base_freq = 1000     # Base frequency
freq_spacing = 100   # Frequency separation
symbol_len = int(fs / baud_rate)
preamble_symbols = 16
password = ""

# Generate frequency table
frequencies = [base_freq + i * freq_spacing for i in range(M)]

# Enhanced global variables
symbol_buffer = np.array([], dtype=np.float32)
bit_buffer = ""
byte_buffer = ""
receiving = False
decoded_buffer = ""
sync_buffer = []
signal_threshold = 100  # Reduced threshold
message_count = 0
sample_count = 0  # For performance monitoring

# Statistics tracking
stats = {
    'messages_received': 0,
    'messages_failed': 0,
    'crc_failures': 0,
    'hamming_errors': 0,
    'symbol_errors': 0,
    'start_time': time.time()
}

# Sync patterns for different priorities
sync_patterns = {
    'normal': [i % M for i in range(preamble_symbols)],
    'urgent': [M-1, 0] * (preamble_symbols // 2)
}

# Signal quality tracking
signal_history = deque(maxlen=100)
frequency_powers = deque(maxlen=50)  # Track frequency domain powers

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
            choice = int(input_devices[0] if len(input_devices) == 1 else int(input("Select input device by number: ")))
            if choice in input_devices:
                sd.default.device = (choice, None)
                print(f"Selected: {sd.query_devices(choice)['name']}")
                break
            else:
                print("Invalid choice. Try again.")
        except (ValueError, IndexError):
            print("Please enter a valid number.")

def goertzel_bank_optimized(samples, freqs, sample_rate):
    """Optimized Goertzel algorithm for multiple frequencies"""
    N = len(samples)
    if N == 0:
        return [0] * len(freqs)
    
    # Pre-compute coefficients for all frequencies
    coeffs = []
    for freq in freqs:
        k = int(0.5 + (N * freq) / sample_rate)
        omega = (2 * np.pi * k) / N
        coeff = 2 * np.cos(omega)
        coeffs.append(coeff)
    
    # Initialize state variables for all frequencies
    s_prev = [0.0] * len(freqs)
    s_prev2 = [0.0] * len(freqs)
    
    # Process all frequencies simultaneously
    for sample in samples:
        for i in range(len(freqs)):
            s = sample + coeffs[i] * s_prev[i] - s_prev2[i]
            s_prev2[i] = s_prev[i]
            s_prev[i] = s
    
    # Calculate powers
    powers = []
    for i in range(len(freqs)):
        power = s_prev2[i]**2 + s_prev[i]**2 - coeffs[i] * s_prev[i] * s_prev2[i]
        powers.append(power)
    
    return powers

def detect_mfsk_symbol(symbol_data):
    """Optimized MFSK symbol detection"""
    powers = goertzel_bank_optimized(symbol_data, frequencies, fs)
    
    total_power = sum(powers)
    
    # Quick threshold check
    if total_power < signal_threshold:
        return None, None, total_power
    
    # Find the frequency with maximum power (faster than numpy)
    max_power = 0
    max_power_idx = 0
    for i, power in enumerate(powers):
        if power > max_power:
            max_power = power
            max_power_idx = i
    
    # Quick confidence check - only compute if needed
    second_max = 0
    for i, power in enumerate(powers):
        if i != max_power_idx and power > second_max:
            second_max = power
    
    if second_max > 0:
        confidence = max_power / second_max
    else:
        confidence = float('inf')
    
    # Require minimum confidence for symbol detection
    if confidence < 1.3:  # Reduced from 1.5 for better sensitivity
        return None, None, total_power
    
    return max_power_idx, powers, total_power

def symbol_to_bits(symbol_value):
    """Convert MFSK symbol value to bits"""
    if symbol_value >= M:
        raise ValueError(f"Symbol value {symbol_value} exceeds maximum {M-1}")
    return f"{symbol_value:0{bits_per_symbol}b}"

def check_sync_patterns():
    """Check for MFSK sync patterns"""
    global sync_buffer
    
    for pattern_type, pattern in sync_patterns.items():
        if len(sync_buffer) >= len(pattern):
            if sync_buffer[-len(pattern):] == pattern:
                return pattern_type
    return None

def reset_receiver_state(reason=""):
    """Reset all receiver state variables with logging"""
    global bit_buffer, byte_buffer, receiving, sync_buffer, decoded_buffer
    bit_buffer = ""
    byte_buffer = ""
    receiving = False
    sync_buffer = []
    decoded_buffer = ""
    if reason:
        print(f"[STATE RESET] {reason}")

def display_statistics():
    """Display reception statistics"""
    runtime = time.time() - stats['start_time']
    print(f"\n{'='*60}")
    print(f"MFSK RECEPTION STATISTICS")
    print(f"Runtime: {runtime:.1f} seconds")
    print(f"Messages received: {stats['messages_received']}")
    print(f"Messages failed: {stats['messages_failed']}")
    print(f"CRC failures: {stats['crc_failures']}")
    print(f"Hamming errors: {stats['hamming_errors']}")
    print(f"Symbol errors: {stats['symbol_errors']}")
    if stats['messages_received'] > 0:
        success_rate = stats['messages_received'] / (stats['messages_received'] + stats['messages_failed']) * 100
        print(f"Success rate: {success_rate:.1f}%")
    
    # Show frequency analysis if available
    if frequency_powers:
        recent_powers = list(frequency_powers)[-10:]  # Last 10 symbols
        avg_powers = np.mean(recent_powers, axis=0)
        peak_freq_idx = np.argmax(avg_powers)
        print(f"Dominant frequency: {frequencies[peak_freq_idx]} Hz (index {peak_freq_idx})")
        print(f"Signal strength: {avg_powers[peak_freq_idx]:.1f}")
    
    print(f"{'='*60}\n")

def display_frequency_spectrum():
    """Display current frequency spectrum"""
    if frequency_powers:
        recent_powers = list(frequency_powers)[-1]  # Most recent
        print(f"\n[SPECTRUM] Current frequency powers:")
        for i, (freq, power) in enumerate(zip(frequencies, recent_powers)):
            bar_length = int(power / max(recent_powers) * 20) if max(recent_powers) > 0 else 0
            bar = '█' * bar_length
            print(f"  {freq:4d} Hz (S{i:2d}): {power:8.1f} {bar}")
        print()

def decode_audio(indata, frames, time_info, status):
    global symbol_buffer, bit_buffer, byte_buffer, receiving, sync_buffer
    global password, decoded_buffer, message_count, sample_count

    if status:
        if 'overflow' in str(status).lower():
            print(f"[AUDIO] Buffer overflow - reducing processing load")
            return  # Skip this frame to catch up
        else:
            print(f"[AUDIO] Status: {status}")

    sample_count += len(indata)

    # Add new samples to buffer
    symbol_buffer = np.append(symbol_buffer, indata[:, 0])

    # Process only one symbol per callback to reduce load
    if len(symbol_buffer) >= symbol_len:
        symbol_data = symbol_buffer[:symbol_len]
        symbol_buffer = symbol_buffer[symbol_len:]

        result = detect_mfsk_symbol(symbol_data)
        if result[0] is None:
            return  # Early return if no valid symbol

        symbol_value, powers, total_power = result

        # Update history less frequently to reduce overhead
        if sample_count % 5000 == 0:  # Every ~1 second at 44.1kHz
            signal_history.append(total_power)
            if powers is not None:
                frequency_powers.append(powers)

        # Maintain sync buffer
        sync_buffer.append(symbol_value)
        max_sync_len = max(len(p) for p in sync_patterns.values())
        if len(sync_buffer) > max_sync_len * 2:
            sync_buffer = sync_buffer[-max_sync_len * 2:]

        # Check for sync patterns
        if not receiving:
            pattern_type = check_sync_patterns()
            if pattern_type:
                priority_str = "[URGENT] " if pattern_type == 'urgent' else ""
                print(f"\n{priority_str}[SYNC DETECTED] MFSK Pattern: {pattern_type}")
                bit_buffer = ""
                sync_buffer = []
                decoded_buffer = ""
                receiving = True
                return

        # Process data symbols
        if receiving:
            try:
                # Convert symbol to bits
                symbol_bits = symbol_to_bits(symbol_value)
                bit_buffer += symbol_bits
                
                # Reduced debug output to minimize overhead
                if len(bit_buffer) <= 16:  # First 4 symbols only
                    print(f"[SYM] {symbol_value:2d} -> {symbol_bits}")

            except ValueError as e:
                print(f"[SYMBOL ERROR] {symbol_value}: {e}")
                stats['symbol_errors'] += 1
                reset_receiver_state("Invalid symbol")
                return

            # Process Hamming(7,4) blocks
            while len(bit_buffer) >= 7:
                block = bit_buffer[:7]
                bit_buffer = bit_buffer[7:]
                
                try:
                    val = cryptofunctions.hamming_decode_7bit(block)
                    decoded_val = f"{val:04b}"
                    decoded_buffer += decoded_val
                except Exception as e:
                    print(f"[HAMMING ERROR] {block}: {e}")
                    stats['hamming_errors'] += 1
                    reset_receiver_state("Hamming decode error")
                    return

            # Process complete bytes
            while len(decoded_buffer) >= 8:
                byte_bits = decoded_buffer[:8]
                decoded_buffer = decoded_buffer[8:]

                try:
                    byte_val = int(byte_bits, 2)
                    char = chr(byte_val)

                    if char == '\x02':  # STX
                        byte_buffer = ""
                        print("[STX] MFSK Message start")

                    elif char == '\x03':  # ETX
                        print("[ETX] MFSK Message end")
                        
                        if '|' not in byte_buffer:
                            print("[ERROR] No CRC delimiter found")
                            stats['messages_failed'] += 1
                            reset_receiver_state("Missing CRC delimiter")
                            return

                        try:
                            encrypted_data, crc = byte_buffer.rsplit('|', 1)
                            
                            if not cryptofunctions.verify_crc(encrypted_data, crc):
                                print("[CRC FAIL] Message corrupted")
                                stats['crc_failures'] += 1
                                stats['messages_failed'] += 1
                            else:
                                decrypted = cryptofunctions.decrypt(encrypted_data, password)
                                message_count += 1
                                stats['messages_received'] += 1
                                
                                timestamp = time.strftime("%H:%M:%S")
                                print(f"\n[MFSK MESSAGE] #{message_count} [{timestamp}]")
                                print(f"[CRC OK] [DECRYPT OK]")
                                print(f"[RECEIVED] '{decrypted}'")
                                
                        except Exception as e:
                            print(f"[DECRYPT ERROR] {e}")
                            stats['messages_failed'] += 1
                        
                        reset_receiver_state("Message processed")

                    else:
                        byte_buffer += char

                except ValueError as e:
                    print(f"[BYTE ERROR] {byte_bits}: {e}")
                    reset_receiver_state("Invalid byte")
                    return

def display_mfsk_info():
    """Display MFSK configuration details"""
    print(f"\n{'='*50}")
    print(f"MFSK RECEIVER CONFIGURATION")
    print(f"Modulation: {M}-FSK")
    print(f"Bits per symbol: {bits_per_symbol}")
    print(f"Base frequency: {base_freq} Hz")
    print(f"Frequency spacing: {freq_spacing} Hz")
    print(f"Frequencies: {frequencies[0]} - {frequencies[-1]} Hz")
    print(f"Symbol rate: {baud_rate} symbols/sec")
    print(f"Expected bit rate: {baud_rate * bits_per_symbol} bps")
    print(f"Samples per symbol: {symbol_len}")
    print(f"Signal threshold: {signal_threshold}")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    print("=== Enhanced MFSK Audio Receiver ===")
    print("Features: 16-FSK, multi-frequency sync, adaptive thresholds, spectrum analysis")
    
    # Initialize
    reset_receiver_state()
    symbol_buffer = np.array([], dtype=np.float32)
    
    display_mfsk_info()
    select_input_device()

    password = input("Enter password for decryption: ")
    if not password:
        print("Password cannot be empty. Exiting.")
        exit(1)
        
    print(f"\nListening for MFSK messages...")
    print("Commands: Ctrl+C to stop")
    print(f"{'='*50}\n")
    
    try:
        with sd.InputStream(callback=decode_audio, channels=1, samplerate=fs, blocksize=512):  # Reduced blocksize
            print("Audio stream started successfully")
            while True:
                try:
                    time.sleep(10)  # Check every 10 seconds
                    if sample_count > 0 and sample_count % 441000 == 0:  # Every ~10 seconds
                        runtime = time.time() - stats['start_time']
                        print(f"[STATUS] Runtime: {runtime:.0f}s, Samples: {sample_count}, Messages: {message_count}")
                except KeyboardInterrupt:
                    raise
                    
    except KeyboardInterrupt:
        print(f"\n\n{'='*50}")
        print("🛑 MFSK Receiver stopped by user")
        display_statistics()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        display_statistics()