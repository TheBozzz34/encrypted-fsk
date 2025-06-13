# Enhanced MFSK Transmitter
import numpy as np
import sounddevice as sd
import cryptofunctions
import time

# MFSK Configuration
fs = 44100         # Sample rate
baud_rate = 45     # symbols per second
M = 16             # Number of frequencies (4 bits per symbol)
bits_per_symbol = int(np.log2(M))  # 4 bits per symbol
base_freq = 1000   # Base frequency
freq_spacing = 100 # Frequency separation between tones
volume = 0.3       # Volume level
preamble_symbols = 16  # Reduced since each symbol carries more data
postamble_symbols = 4  # Additional symbols after message
password = ""

# Generate frequency table
frequencies = [base_freq + i * freq_spacing for i in range(M)]
print(f"MFSK Frequencies: {frequencies[0]} Hz to {frequencies[-1]} Hz")

def list_output_devices():
    print("Available Output Devices:")
    devices = sd.query_devices()
    output_devices = []
    for i, device in enumerate(devices):
        if device['max_output_channels'] > 0:
            print(f"{i}: {device['name']}")
            output_devices.append(i)
    return output_devices

def select_output_device():
    output_devices = list_output_devices()
    while True:
        try:
            choice = int(input("Select output device by number: "))
            if choice in output_devices:
                sd.default.device = (None, choice)
                print(f"Selected: {sd.query_devices(choice)['name']}")
                break
            else:
                print("Invalid choice. Try again.")
        except ValueError:
            print("Please enter a valid number.")

def text_to_bits(text):
    return ''.join(f"{ord(c):08b}" for c in text)

def bits_to_symbols(bits):
    """Convert bit string to MFSK symbol values"""
    # Pad bits to multiple of bits_per_symbol
    while len(bits) % bits_per_symbol != 0:
        bits += '0'
    
    symbols = []
    for i in range(0, len(bits), bits_per_symbol):
        symbol_bits = bits[i:i + bits_per_symbol]
        symbol_value = int(symbol_bits, 2)
        symbols.append(symbol_value)
    
    return symbols

def generate_mfsk_tone(symbol_value, apply_windowing=True):
    """Generate MFSK tone for given symbol value"""
    if symbol_value >= M:
        raise ValueError(f"Symbol value {symbol_value} exceeds maximum {M-1}")
    
    freq = frequencies[symbol_value]
    samples_per_symbol = int(fs / baud_rate)
    t = np.linspace(0, 1 / baud_rate, samples_per_symbol, endpoint=False)
    
    # Generate clean sine wave
    tone = volume * np.sin(2 * np.pi * freq * t)
    
    # Apply windowing to reduce inter-symbol interference
    if apply_windowing:
        window_size = min(50, samples_per_symbol // 20)  # 5% of symbol duration
        if window_size > 0:
            # Cosine windowing for smoother transitions
            window = np.hanning(window_size * 2)
            tone[:window_size] *= window[:window_size]
            tone[-window_size:] *= window[window_size:]
    
    return tone

def generate_preamble(priority="normal"):
    """Generate MFSK preamble pattern"""
    if priority == "urgent":
        # Alternating pattern between high and low frequencies for urgent
        pattern = [M-1, 0] * (preamble_symbols // 2)
    else:
        # Sequential pattern for normal sync
        pattern = [i % M for i in range(preamble_symbols)]
    
    return pattern

def generate_postamble():
    """Generate MFSK postamble pattern"""
    # Simple alternating pattern
    return [1, M-2] * (postamble_symbols // 2)

def send_message(message, priority="normal"):
    start_time = time.time()
    
    # Encrypt and add CRC
    encrypted = cryptofunctions.encrypt(message, password)
    crc = cryptofunctions.compute_crc(encrypted)
    payload_with_crc = encrypted + "|" + crc
    
    # Create preamble and postamble
    preamble_symbols = generate_preamble(priority)
    postamble_symbols = generate_postamble()
    
    if priority == "urgent":
        print("[URGENT MESSAGE]")
    
    # Frame the message with STX and ETX
    framed = '\x02' + payload_with_crc + '\x03'
    
    # Convert to bits and apply Hamming encoding
    raw_bits = text_to_bits(framed)
    encoded_bits = ''
    for i in range(0, len(raw_bits), 4):
        nibble = raw_bits[i:i+4].ljust(4, '0')
        encoded_bits += cryptofunctions.hamming_encode_4bit(int(nibble, 2))
    
    # Convert encoded bits to MFSK symbols
    data_symbols = bits_to_symbols(encoded_bits)
    
    # Complete transmission structure
    all_symbols = preamble_symbols + data_symbols + postamble_symbols
    
    # Display transmission info
    print(f"\n{'='*50}")
    print(f"Transmitting: '{message}'")
    print(f"Encrypted: {encrypted}")
    print(f"CRC: {crc}")
    print(f"MFSK Configuration: {M}-FSK ({bits_per_symbol} bits/symbol)")
    print(f"Total symbols: {len(all_symbols)} ({len(preamble_symbols)} preamble + {len(data_symbols)} data + {len(postamble_symbols)} postamble)")
    print(f"Total bits transmitted: {len(all_symbols) * bits_per_symbol}")
    print(f"Raw data bits: {len(text_to_bits(message))}")
    print(f"Transmission time: {len(all_symbols) / baud_rate:.2f} seconds")
    print(f"Effective data rate: {len(text_to_bits(message)) / (len(all_symbols) / baud_rate):.1f} bps")
    print(f"Data efficiency: {len(text_to_bits(message)) / (len(all_symbols) * bits_per_symbol) * 100:.1f}%")
    
    # Generate signal
    signal_parts = []
    for symbol in all_symbols:
        signal_parts.append(generate_mfsk_tone(symbol))
    
    signal = np.concatenate(signal_parts)
    
    # Add leading and trailing silence
    silence_duration = 0.2
    silence_samples = int(fs * silence_duration)
    silence = np.zeros(silence_samples)
    final_signal = np.concatenate([silence, signal, silence])
    
    # Normalize to prevent clipping
    max_amplitude = np.max(np.abs(final_signal))
    if max_amplitude > 0.95:
        final_signal = final_signal * 0.95 / max_amplitude
        print(f"Signal normalized (was {max_amplitude:.3f})")
    
    print("Playing signal...")
    sd.play(final_signal, samplerate=fs)
    sd.wait()
    
    elapsed_time = time.time() - start_time
    print(f"Transmission completed in {elapsed_time:.2f} seconds")
    print(f"{'='*50}\n")

def send_test_pattern():
    """Send a test pattern for receiver calibration"""
    print("Sending MFSK test pattern...")
    
    # Send all frequencies in sequence for calibration
    test_symbols = list(range(M)) * 3  # Each frequency 3 times
    
    signal_parts = []
    for symbol in test_symbols:
        signal_parts.append(generate_mfsk_tone(symbol, apply_windowing=False))
    
    signal = np.concatenate(signal_parts)
    
    # Add frequency sweep
    sweep_duration = 2.0  # 2 seconds
    sweep_samples = int(fs * sweep_duration)
    t = np.linspace(0, sweep_duration, sweep_samples, endpoint=False)
    sweep_freq = np.linspace(frequencies[0], frequencies[-1], sweep_samples)
    sweep_signal = volume * np.sin(2 * np.pi * sweep_freq * t)
    
    final_signal = np.concatenate([signal, sweep_signal])
    
    print(f"Test pattern: {len(test_symbols)} symbols + frequency sweep")
    sd.play(final_signal, samplerate=fs)
    sd.wait()
    print("Test pattern complete.\n")

def send_beacon():
    """Send a simple beacon signal for testing"""
    beacon_message = "MFSK_BEACON"
    send_message(beacon_message, priority="normal")

def display_mfsk_info():
    """Display MFSK configuration details"""
    print(f"\n{'='*50}")
    print(f"MFSK CONFIGURATION")
    print(f"Modulation: {M}-FSK")
    print(f"Bits per symbol: {bits_per_symbol}")
    print(f"Base frequency: {base_freq} Hz")
    print(f"Frequency spacing: {freq_spacing} Hz")
    print(f"Frequency range: {frequencies[0]} - {frequencies[-1]} Hz")
    print(f"Symbol rate: {baud_rate} symbols/sec")
    print(f"Theoretical bit rate: {baud_rate * bits_per_symbol} bps")
    print(f"Bandwidth: {(M-1) * freq_spacing + 2*freq_spacing} Hz")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    print("=== Enhanced MFSK Audio Transmitter ===")
    print("Features: 16-FSK, Hamming codes, CRC, encryption, improved signaling")
    
    display_mfsk_info()
    select_output_device()

    password = input("Enter password for encryption: ")
    if not password:
        print("Password cannot be empty. Exiting.")
        exit(1)
    
    print(f"\nConfiguration Summary:")
    print(f"Sample rate: {fs} Hz")
    print(f"Symbol rate: {baud_rate} symbols/sec")
    print(f"Modulation: {M}-FSK ({bits_per_symbol} bits/symbol)")
    print(f"Samples per symbol: {fs // baud_rate}")
    print(f"Preamble symbols: {len(generate_preamble())}")
    print(f"Postamble symbols: {len(generate_postamble())}")
    
    while True:
        try:
            print("\nOptions:")
            print("1. Send message")
            print("2. Send test pattern")
            print("3. Send beacon")
            print("4. Show MFSK info")
            print("5. Exit")
            
            choice = input("Select option (1-5): ").strip()
            
            if choice == '1':
                msg = input("Enter message to transmit: ")
                if msg:
                    priority = input("Priority (normal/urgent) [normal]: ").strip().lower()
                    if priority not in ['normal', 'urgent']:
                        priority = 'normal'
                    send_message(msg, priority)
                    
            elif choice == '2':
                send_test_pattern()
                
            elif choice == '3':
                send_beacon()
                
            elif choice == '4':
                display_mfsk_info()
                
            elif choice == '5':
                break
                
            else:
                print("Invalid choice. Please enter 1-5.")
                
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")

    print("MFSK Transmitter stopped.")