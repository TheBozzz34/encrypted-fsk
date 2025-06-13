import numpy as np
import sounddevice as sd
import time
import cryptofunctions

# Configuration
fs = 44100         # Sample rate
baud_rate = 40      # symbols per second
f0 = 1000          # Frequency for binary 0
f1 = 2000          # Frequency for binary 1
volume = 0.3       # Reduced volume to prevent clipping
preamble_bits = 16 # Number of alternating bits for sync
password = ""

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
                sd.default.device = (None, choice)  # (input, output)
                print(f"Selected: {sd.query_devices(choice)['name']}")
                break
            else:
                print("Invalid choice. Try again.")
        except ValueError:
            print("Please enter a valid number.")

def text_to_bits(text):
    return ''.join(f"{ord(c):08b}" for c in text)

def generate_tone(bit):
    freq = f1 if bit == '1' else f0
    samples_per_bit = int(fs / baud_rate)
    t = np.linspace(0, 1 / baud_rate, samples_per_bit, endpoint=False)
    
    # Generate clean sine wave
    tone = volume * np.sin(2 * np.pi * freq * t)
    
    # Apply gentle windowing to reduce clicking between bits
    window_size = min(100, samples_per_bit // 10)  # 10% of bit duration
    if window_size > 0:
        # Smooth transitions at bit boundaries
        tone[:window_size] *= np.linspace(0, 1, window_size)
        tone[-window_size:] *= np.linspace(1, 0, window_size)
    
    return tone

def send_message(message):
    encrypted = cryptofunctions.encrypt(message, password)

    crc = cryptofunctions.compute_crc(encrypted)
    payload_with_crc = encrypted + "|" + crc  # '|' separates message and CRC

    # Add preamble for synchronization (alternating 0101...)
    preamble = '01' * (preamble_bits // 2)
    
    # Frame the message
    framed = '\x02' + payload_with_crc + '\x03'  # STX ... ETX
    bits = text_to_bits(framed)
    
    # Complete transmission: preamble + data
    full_bits = preamble + bits
    
    print(f"Transmitting: {message}")
    print(f"Preamble + Data bits: {len(full_bits)} bits")
    print(f"Transmission time: {len(full_bits) / baud_rate:.1f} seconds")
    
    # Generate the complete signal
    signal = np.concatenate([generate_tone(b) for b in full_bits])
    
    # Add silence at the end to ensure complete transmission
    silence_duration = 0.5  # 500ms of silence
    silence_samples = int(fs * silence_duration)
    silence = np.zeros(silence_samples)
    signal = np.concatenate([signal, silence])
    
    # Play the signal
    sd.play(signal, samplerate=fs)
    sd.wait()
    
    print("Transmission complete.\n")

if __name__ == "__main__":
    print("=== FSK Audio Transmitter (Improved) ===")
    select_output_device()

    password = input("Enter password for decryption: ")
    if not password:
        print("Password cannot be empty. Exiting.")
        exit(1)
    
    print(f"\nConfiguration:")
    print(f"Sample rate: {fs} Hz")
    print(f"Baud rate: {baud_rate} bps")
    print(f"Frequency 0: {f0} Hz")
    print(f"Frequency 1: {f1} Hz")
    print(f"Samples per bit: {fs // baud_rate}")
    
    while True:
        try:
            msg = input("\nEnter message to transmit (or 'exit'): ")
            if msg.lower() == "exit":
                break
            send_message(msg)
        except KeyboardInterrupt:
            break