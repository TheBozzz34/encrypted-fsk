# FSK Audio Transmitter & Receiver with Encryption and CRC Verification

This project implements a **Python-based Frequency-Shift Keying (FSK)** audio communication system over sound. It securely transmits messages between devices using two distinct audio frequencies to represent binary data. It includes:

- 🔐 **AES Encryption**
- ✅ **CRC-16 Verification**
- 📡 **FSK Modulation/Demodulation**
- 🖥️ Selectable audio input/output devices

It was written with the intent of sending secure, encrypted messaged over a radio transmitter plugged into a computer.

---

## 📁 Project Structure

```

.
├── transmitter.py        # Transmitter: encrypts, adds CRC, modulates, and plays audio
├── receiver.py           # Receiver: records audio, demodulates, decrypts, verifies CRC
├── cryptofunctions.py    # Contains AES encryption and CRC utilities
└── README.md             # You're reading it!

````

---

## ⚙️ Features

- **FSK Modulation** using two sine wave frequencies (`f0` and `f1`)
- **AES-128/256 Encryption** (via `cryptofunctions.py`)
- **CRC-16 Verification** to ensure data integrity
- **Preamble Sync Detection** using alternating `01` pattern
- **Start/End Framing** using ASCII STX (`\x02`) and ETX (`\x03`)
- **Goertzel-based Demodulator** with noise filtering

---

## 📦 Requirements

- Python 3.7+
- Dependencies:

```bash
pip install numpy sounddevice cryptography
````

---

## ▶️ Usage

### 1. Start the Transmitter

```bash
python transmitter.py
```

* Select output device
* Enter the password for encryption
* Input your message and it will be transmitted via audio

### 2. Start the Receiver

```bash
python receiver.py
```

* Select input device
* Enter the same password for decryption
* It listens for incoming messages and displays decrypted content if the CRC check passes

---

## 🔒 Security

* **Encryption** is handled using symmetric AES encryption.
* **CRC-16 (XMODEM variant)** ensures data integrity.
* Encrypted message and CRC are joined with a `|` before transmission.

Example transmitted frame (encrypted):

```
\x02 <encrypted_payload>|<CRC> \x03
```

---

## 📡 Modulation Parameters

| Parameter   | Value               |
| ----------- | ------------------- |
| Sample Rate | 44100 Hz            |
| Baud Rate   | 40 symbols/sec      |
| Frequency 0 | 1000 Hz             |
| Frequency 1 | 2000 Hz             |
| Preamble    | 16 bits (`0101...`) |
| CRC         | CRC-16 (XMODEM)     |

---

## 🧠 Credits

Developed using:

* `sounddevice` for audio I/O
* `numpy` for signal processing
* `cryptography` for encryption

---

## 🚧 Future Enhancements

* Multi-character encoding (e.g., Base64)
* Error correction (e.g., Hamming code)
* Visual waveform/debugging tools
* Duplex communication

---

## 📜 License

MIT License – free to use, modify, and share.
