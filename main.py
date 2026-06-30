import sys, os, time, threading, urllib.parse, re
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QTextEdit, QLabel, QMessageBox,
                             QSpinBox)
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


# ----------------- Normalizer -----------------
def normalize_iranian_number(raw: str):
    """ورودی: شماره خام - خروجی: شماره استاندارد یا None"""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()  # حذف فاصله‌های اضافی
    digits = re.sub(r'\D', '', raw)  # حذف همه غیر عددها

    # حذف پیش‌شماره‌های مختلف
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("098"):
        digits = digits[3:]
    elif digits.startswith("98") and len(digits) > 10:
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = digits[1:]

    digits = digits.strip()  # اطمینان از نبود فاصله اضافی
    if len(digits) == 10 and digits.startswith("9"):
        return "98" + digits
    if len(digits) == 12 and digits.startswith("98"):
        return digits
    return None


def clean_numbers_bulk(raw_lines):
    valid, invalid, seen = [], [], set()
    for raw in raw_lines:
        raw_str = (raw or "").strip()
        if not raw_str:
            continue
        normalized = normalize_iranian_number(raw_str)
        if normalized:
            if normalized not in seen:
                seen.add(normalized)
                valid.append(normalized)
        else:
            invalid.append(raw_str)
    return valid, invalid


# ----------------- Thread for sending messages -----------------
class SenderThread(QThread):
    log_signal = pyqtSignal(str, str)  # (message, type)
    finished_signal = pyqtSignal()

    def __init__(self, numbers, message, delay=5, profile_dir=None):
        super().__init__()
        self.numbers = numbers
        self.message = message
        self.delay = float(delay)
        self.profile_dir = profile_dir
        self.ready_event = threading.Event()
        self._stop_requested = False
        self.driver = None

    def stop(self):
        self._stop_requested = True
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass

    def run(self):
        try:
            chrome_options = Options()
            if self.profile_dir:
                chrome_options.add_argument(f"user-data-dir={self.profile_dir}")
            chrome_options.add_argument("--disable-notifications")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

            try:
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as e:
                self.log_signal.emit(f"خطا در راه‌اندازی مرورگر: {e}", "error")
                return

            self.driver.get("https://web.whatsapp.com")
            self.log_signal.emit("📱 لطفاً QR را اسکن کن و روی 'من آماده‌ام' کلیک کن.", "info")

            while not self.ready_event.is_set():
                if self._stop_requested:
                    self.log_signal.emit("⏹️ عملیات لغو شد", "error")
                    try: self.driver.quit()
                    except: pass
                    return
                time.sleep(0.3)

            self.log_signal.emit("🚀 شروع ارسال پیام‌ها...", "info")

            for number in self.numbers:
                if self._stop_requested:
                    self.log_signal.emit("⏹️ عملیات متوقف شد", "error")
                    break

                if not (number.startswith('98') and len(number) == 12 and number.isdigit()):
                    self.log_signal.emit(f"⚠ شماره نامعتبر: {number}", "warn")
                    continue

                try:
                    encoded_msg = urllib.parse.quote(self.message)
                    url = f"https://web.whatsapp.com/send?phone={number}&text={encoded_msg}"
                    self.driver.get(url)

                    msg_box = WebDriverWait(self.driver, 30).until(
                        EC.presence_of_element_located((By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]'))
                    )
                    msg_box.click()
                    time.sleep(1)
                    msg_box.send_keys(Keys.ENTER)
                    self.log_signal.emit(f"✅ پیام ارسال شد به {number}", "success")

                    slept = 0.0
                    while slept < self.delay:
                        if self._stop_requested:
                            break
                        time.sleep(0.2)
                        slept += 0.2

                except Exception as e:
                    self.log_signal.emit(f"❌ خطا در ارسال به {number}: {e}", "error")
                    continue

            self.log_signal.emit("✅ همه پیام‌ها ارسال شدند.", "success")
            try:
                self.driver.quit()
            except:
                pass
            self.finished_signal.emit()

        except Exception as e:
            self.log_signal.emit(f"خطای کلی: {e}", "error")
            try:
                if self.driver: self.driver.quit()
            except: pass


# ----------------- Main Window -----------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WhatsApp Sender - Mohammad")
        self.resize(750, 550)

        layout = QVBoxLayout()

        self.label_numbers = QLabel("شماره‌ها (هر خط یک شماره):")
        layout.addWidget(self.label_numbers)
        self.text_numbers = QTextEdit()
        layout.addWidget(self.text_numbers)

        self.label_message = QLabel("متن پیام:")
        layout.addWidget(self.label_message)
        self.text_message = QTextEdit()
        layout.addWidget(self.text_message)

        settings_row = QHBoxLayout()
        self.label_delay = QLabel("تاخیر (ثانیه):")
        settings_row.addWidget(self.label_delay)
        self.spin_delay = QSpinBox()
        self.spin_delay.setRange(1, 60)
        self.spin_delay.setValue(5)
        settings_row.addWidget(self.spin_delay)
        layout.addLayout(settings_row)

        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("▶ شروع ارسال")
        self.btn_start.clicked.connect(self.start_sending)
        btn_row.addWidget(self.btn_start)

        self.btn_ready = QPushButton("✔️ من آماده‌ام (QR اسکن شد)")
        self.btn_ready.setEnabled(False)
        self.btn_ready.clicked.connect(self.set_ready)
        btn_row.addWidget(self.btn_ready)

        self.btn_stop = QPushButton("⏹️ توقف")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_sending)
        btn_row.addWidget(self.btn_stop)

        layout.addLayout(btn_row)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        self.setLayout(layout)
        self.thread = None

        self.profile_dir = os.path.join(os.getcwd(), "SeleniumProfile")
        if not os.path.exists(self.profile_dir):
            os.makedirs(self.profile_dir)
            self.append_log(f"✅ فولدر پروفایل خودکار ساخته شد: {self.profile_dir}", "info")

        self.setStyleSheet("""
QWidget {background-color: #f0f2f5; font-family: 'Segoe UI';}
QTextEdit {background-color: #ffffff; border-radius: 8px; padding: 6px; font-size: 14px;}
QPushButton {background-color: #4caf50; color: white; border-radius: 10px; padding: 8px 15px; font-weight: bold;}
QPushButton:hover {background-color: #45a049;}
QPushButton:pressed {background-color: #3e8e41;}
QLabel {font-size: 14px; font-weight: bold;}
QSpinBox {border-radius: 5px; padding: 2px;}
""")

    def append_log(self, text, type_="info"):
        cursor = self.log.textCursor()
        fmt = QTextCharFormat()
        if type_ == "success":
            fmt.setForeground(QColor("green"))
        elif type_ == "error":
            fmt.setForeground(QColor("red"))
        elif type_ == "warn":
            fmt.setForeground(QColor("orange"))
        else:
            fmt.setForeground(QColor("black"))
        cursor.setCharFormat(fmt)
        cursor.insertText(text + "\n")
        self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()

    def start_sending(self):
        numbers_text = self.text_numbers.toPlainText().strip()
        message_text = self.text_message.toPlainText().strip()
        if not numbers_text or not message_text:
            QMessageBox.warning(self, "خطا", "شماره‌ها و متن پیام را وارد کنید.")
            return

        raw_lines = numbers_text.splitlines()
        numbers, invalids = clean_numbers_bulk(raw_lines)

        if invalids:
            self.append_log(f"⚠ {len(invalids)} شماره نامعتبر:", "warn")
            for bad in invalids[:10]:
                self.append_log(f"   {bad}", "warn")
            if len(invalids) > 10:
                self.append_log(f"   ... و {len(invalids)-10} مورد دیگر", "warn")

        if not numbers:
            QMessageBox.warning(self, "خطا", "هیچ شماره معتبر یافت نشد.")
            return

        self.thread = SenderThread(numbers, message_text, delay=self.spin_delay.value(), profile_dir=self.profile_dir)
        self.thread.log_signal.connect(self.append_log)
        self.thread.finished_signal.connect(self.on_finished)
        self.thread.start()

        self.btn_ready.setEnabled(True)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.append_log("🔔 واتساپ وب باز شد. QR را اسکن کن و روی 'من آماده‌ام' کلیک کن.", "info")

    def set_ready(self):
        if self.thread:
            self.thread.ready_event.set()
            self.btn_ready.setEnabled(False)
            self.append_log("✅ ادامه ارسال شروع شد.", "info")

    def stop_sending(self):
        if self.thread:
            self.thread.stop()
            self.btn_stop.setEnabled(False)
            self.btn_start.setEnabled(True)
            self.append_log("✋ عملیات متوقف شد.", "warn")

    def on_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_ready.setEnabled(False)
        self.append_log("🔚 عملیات پایان یافت.", "info")


# ----------------- Run -----------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
