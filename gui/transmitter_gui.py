import sys
import numpy as np
import sounddevice as sd
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QLineEdit, QLabel, QComboBox, QTextEdit
)
import cryptofunctions

# Configuration
fs = 44100
baud_rate = 40
f0 = 1000
f1 = 2000
volume = 0.3
preamble_bits = 16
symbol_len = int(fs / baud_rate)

class TransmitterApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FSK Audio Transmitter")
        self.setGeometry(100, 100, 400, 300)

        self.password = ""
        self.init_ui()
        self.devices = self.get_output_devices()
        self.device_combo.addItems(self.devices)

    def init_ui(self):
        layout = QVBoxLayout()

        self.device_combo = QComboBox()
        layout.addWidget(QLabel("Select Output Device:"))
        layout.addWidget(self.device_combo)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(QLabel("Encryption Password:"))
        layout.addWidget(self.password_input)

        self.message_input = QTextEdit()
        layout.addWidget(QLabel("Message to Transmit:"))
        layout.addWidget(self.message_input)

        self.send_button = QPushButton("Send Message")
        self.send_button.clicked.connect(self.send_message)
        layout.addWidget(self.send_button)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def get_output_devices(self):
        devices = sd.query_devices()
        return [device['name'] for device in devices if device['max_output_channels'] > 0]

    def text_to_bits(self, text):
        return ''.join(f"{ord(c):08b}" for c in text)

    def generate_tone(self, bit):
        freq = f1 if bit == '1' else f0
        t = np.linspace(0, 1 / baud_rate, symbol_len, endpoint=False)
        tone = volume * np.sin(2 * np.pi * freq * t)
        window = min(100, symbol_len // 10)
        if window:
            tone[:window] *= np.linspace(0, 1, window)
            tone[-window:] *= np.linspace(1, 0, window)
        return tone

    def send_message(self):
        try:
            device_index = self.device_combo.currentIndex()
            selected_device = sd.query_devices(device_index)
            max_channels = selected_device['max_output_channels']
        
            # Set the selected device as default
            sd.default.device = (None, device_index)

            self.password = self.password_input.text()
            if not self.password:
                self.status_label.setText("Password cannot be empty.")
                return

            message = self.message_input.toPlainText()
            encrypted = cryptofunctions.encrypt(message, self.password)
            crc = cryptofunctions.compute_crc(encrypted)
            payload = encrypted + "|" + crc
            framed = '\x02' + payload + '\x03'
            bits = self.text_to_bits(framed)
            full_bits = '01' * (preamble_bits // 2) + bits
            signal = np.concatenate([self.generate_tone(b) for b in full_bits])
            signal = np.concatenate([signal, np.zeros(int(fs * 0.5))])  # 0.5s silence at end

            # Reshape only if mono output
            if max_channels == 1:
                signal = signal.reshape(-1, 1)
        
            sd.play(signal, samplerate=fs)
            sd.wait()
            self.status_label.setText("Transmission complete.")
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TransmitterApp()
    window.show()
    sys.exit(app.exec_())
