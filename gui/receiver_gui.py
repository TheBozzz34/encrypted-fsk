import sys
import numpy as np
import sounddevice as sd
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLineEdit, QLabel, QPushButton, QComboBox, QTextEdit
)
import cryptofunctions

# Configuration
fs = 44100
baud_rate = 40
f0 = 1000
f1 = 2000
symbol_len = int(fs / baud_rate)
preamble_bits = 16
sync_pattern = '01' * (preamble_bits // 2)
signal_threshold = 1000

class ReceiverApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FSK Audio Receiver")
        self.setGeometry(100, 100, 400, 300)

        self.bit_buffer = ""
        self.symbol_buffer = np.array([], dtype=np.float32)
        self.byte_buffer = ""
        self.receiving = False
        self.sync_buffer = ""
        self.password = ""

        self.init_ui()
        self.devices = self.get_input_devices()
        self.device_combo.addItems(self.devices)

    def init_ui(self):
        layout = QVBoxLayout()

        self.device_combo = QComboBox()
        layout.addWidget(QLabel("Select Input Device:"))
        layout.addWidget(self.device_combo)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(QLabel("Decryption Password:"))
        layout.addWidget(self.password_input)

        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        layout.addWidget(QLabel("Received Messages:"))
        layout.addWidget(self.output_box)

        self.start_button = QPushButton("Start Listening")
        self.start_button.clicked.connect(self.start_receiving)
        layout.addWidget(self.start_button)

        self.setLayout(layout)

    def get_input_devices(self):
        devices = sd.query_devices()
        return [device['name'] for device in devices if device['max_input_channels'] > 0]

    def goertzel(self, samples, freq):
        N = len(samples)
        k = int(0.5 + (N * freq) / fs)
        omega = (2 * np.pi * k) / N
        coeff = 2 * np.cos(omega)
        s_prev = s_prev2 = 0
        for sample in samples:
            s = sample + coeff * s_prev - s_prev2
            s_prev2 = s_prev
            s_prev = s
        return s_prev2**2 + s_prev**2 - coeff * s_prev * s_prev2

    def detect_bit(self, symbol):
        power0 = self.goertzel(symbol, f0)
        power1 = self.goertzel(symbol, f1)
        total_power = power0 + power1
        if total_power < signal_threshold:
            return None
        ratio = power1 / power0 if power0 > 0 else float('inf')
        if ratio > 1.5:
            return '1'
        elif ratio < 0.67:
            return '0'
        return None

    def decode_audio(self, indata, frames, time, status):
        self.symbol_buffer = np.append(self.symbol_buffer, indata[:, 0])
        while len(self.symbol_buffer) >= symbol_len:
            symbol = self.symbol_buffer[:symbol_len]
            self.symbol_buffer = self.symbol_buffer[symbol_len:]
            bit = self.detect_bit(symbol)
            if bit is None:
                continue
            self.sync_buffer += bit
            if len(self.sync_buffer) > len(sync_pattern) * 2:
                self.sync_buffer = self.sync_buffer[-len(sync_pattern) * 2:]
            if not self.receiving and self.sync_buffer.endswith(sync_pattern):
                self.bit_buffer = ""
                self.byte_buffer = ""
                self.receiving = True
                continue
            if self.receiving:
                self.bit_buffer += bit
                while len(self.bit_buffer) >= 8:
                    byte = self.bit_buffer[:8]
                    self.bit_buffer = self.bit_buffer[8:]
                    try:
                        char = chr(int(byte, 2))
                        if char == '\x02':
                            self.byte_buffer = ""
                        elif char == '\x03':
                            if '|' not in self.byte_buffer:
                                self.receiving = False
                                return
                            encrypted, crc = self.byte_buffer.rsplit('|', 1)
                            if not cryptofunctions.verify_crc(encrypted, crc):
                                self.output_box.append("[ERROR] CRC mismatch.")
                            else:
                                msg = cryptofunctions.decrypt(encrypted, self.password)
                                self.output_box.append(f"[RECEIVED]: {msg}")
                            self.receiving = False
                        else:
                            self.byte_buffer += char
                    except Exception:
                        self.receiving = False

    def start_receiving(self):
        try:
            sd.default.device = (self.device_combo.currentIndex(), None)
            self.password = self.password_input.text()
            self.output_box.append("Listening...\n")
            self.stream = sd.InputStream(
                callback=self.decode_audio,
                channels=1,
                samplerate=fs,
                blocksize=1024
            )
            self.stream.start()
        except Exception as e:
            self.output_box.append(f"Error: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ReceiverApp()
    window.show()
    sys.exit(app.exec_())
