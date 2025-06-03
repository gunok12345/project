import sys
import os
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QLineEdit, QPushButton, QFileDialog, QVBoxLayout, QHBoxLayout, QMessageBox, QComboBox, QProgressBar, QDialog, QSizePolicy
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QThread
from PyQt5.QtGui import QIcon, QPixmap
import threading
from youtube_mp3_downloader import download_mp3
import re

class TitleAndResWorker(QThread):
    result = pyqtSignal(str, list, str, str)  # เพิ่ม thumbnail_url
    def __init__(self, url, search_query=None):
        super().__init__()
        self.url = url
        self.search_query = search_query or ''
    def run(self):
        title = ''
        resolutions = []
        thumbnail_url = ''
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(self.url, download=False)
                # ถ้าเป็น search (ytsearch1:) จะได้ info['entries']
                if 'entries' in info:
                    print(f"[DEBUG][worker] info['entries'] type: {type(info['entries'])}, value: {info['entries']}")
                if 'entries' in info and info['entries']:
                    print(f"[DEBUG][worker] yt-dlp entries: {len(info['entries'])}")
                    for idx, e in enumerate(info['entries']):
                        print(f"[DEBUG][worker] entry[{idx}]: {e}")
                        if e:
                            print(f"[DEBUG][worker] entry[{idx}]: title={e.get('title')!r}, ie_key={e.get('ie_key')!r}, thumbnail={e.get('thumbnail')!r}, thumbnails={e.get('thumbnails')!r}")
                    entry = None
                    # 1. หา entry ที่เป็นวิดีโอจริง (ie_key ขึ้นต้นด้วย 'Youtube') และมี title
                    for e in info['entries']:
                        if e and e.get('ie_key', '').lower().startswith('youtube') and e.get('title'):
                            entry = e
                            break
                    # 2. ถ้าไม่เจอ ให้ fallback เป็น entry แรกที่มี title
                    if not entry:
                        for e in info['entries']:
                            if e and e.get('title'):
                                entry = e
                                break
                    # 3. ถ้าไม่เจออีก ให้ fallback เป็น entry แรกที่มี title หรือ description
                    if not entry:
                        for e in info['entries']:
                            if e and (e.get('title') or e.get('description')):
                                entry = e
                                break
                    # 4. ถ้ายังไม่เจอ ให้ถือว่าไม่พบวิดีโอ
                    if not entry:
                        print(f"[DEBUG][worker] No suitable entry found in yt-dlp entries.")
                        self.result.emit('', [], self.search_query, '')
                        return
                    print(f"[DEBUG][worker] Selected entry: title={entry.get('title')!r}, ie_key={entry.get('ie_key')!r}, thumbnail={entry.get('thumbnail')!r}, thumbnails={entry.get('thumbnails')!r}")
                    title = entry.get('title', '')
                    formats = entry.get('formats', [])
                    # หา thumbnail จาก entry ที่เลือก ถ้าไม่มีให้วนหา entry ไหนก็ได้ที่มี thumbnail
                    thumbnail_url = entry.get('thumbnail', '') or (entry.get('thumbnails', [{}])[0].get('url', '') if entry.get('thumbnails') else '')
                    if not thumbnail_url:
                        for e in info['entries']:
                            if e and (e.get('thumbnail') or (e.get('thumbnails') and e.get('thumbnails')[0].get('url'))):
                                thumbnail_url = e.get('thumbnail', '') or (e.get('thumbnails', [{}])[0].get('url', '') if e.get('thumbnails') else '')
                                if thumbnail_url:
                                    break
                else:
                    print(f"[DEBUG][worker] No entries found in yt-dlp info.")
                    title = info.get('title', '')
                    formats = info.get('formats', [])
                    thumbnail_url = info.get('thumbnail', '') or (info.get('thumbnails', [{}])[0].get('url', '') if info.get('thumbnails') else '')
                print(f"[DEBUG][worker] yt-dlp title: {title} | thumbnail: {thumbnail_url}")
                for f in formats:
                    if f.get('vcodec') != 'none' and f.get('ext') == 'mp4' and f.get('height'):
                        resolutions.append(f['height'])
        except Exception as e:
            print(f"[DEBUG][worker] yt-dlp error: {e}")
        resolutions = sorted(set(resolutions), reverse=True)
        self.result.emit(title, resolutions, self.search_query, thumbnail_url)

class DownloadWorker(QThread):
    progress = pyqtSignal(float)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    def __init__(self, url, cookies, output, fmt, resolution):
        super().__init__()
        self.url = url
        self.cookies = cookies
        self.output = output
        self.fmt = fmt
        self.resolution = resolution
    def run(self):
        try:
            import yt_dlp
            ydl_opts = {
                # outtmpl: sanitize title for Windows
                'outtmpl': os.path.join(self.output, '%(title)s.%(ext)s'),
                'progress_hooks': [self.hook],
                'quiet': True,
                'windowsfilenames': True,  # ให้ yt-dlp ช่วย sanitize ชื่อไฟล์สำหรับ Windows
            }
            if self.fmt == 'mp3':
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                })
            elif self.fmt == 'mp4':
                if self.resolution:
                    ydl_opts.update({
                        'format': f"bestvideo[ext=mp4][vcodec!=none][height={self.resolution}]+bestaudio[ext=m4a]/mp4",
                        'merge_output_format': 'mp4',
                    })
                else:
                    ydl_opts.update({
                        'format': 'bestvideo[ext=mp4][vcodec!=none][height<=1080]+bestaudio[ext=m4a]/mp4',
                        'merge_output_format': 'mp4',
                    })
            if self.cookies:
                ydl_opts['cookiefile'] = self.cookies
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
            self.finished.emit('success')
        except Exception as e:
            self.error.emit(str(e))
    def hook(self, d):
        if d.get('status') == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes', 0)
            if total:
                percent = downloaded / total * 100
                self.progress.emit(percent)

class LoadingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('กำลังโหลดข้อมูล...' if getattr(parent, 'language', 'th') == 'th' else 'Loading...')
        self.setModal(True)
        self.setFixedSize(350, 120)
        layout = QVBoxLayout()
        self.label = QLabel('กำลังดึงข้อมูลวิดีโอ...' if getattr(parent, 'language', 'th') == 'th' else 'Fetching video info...')
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminate
        layout.addWidget(self.progress)
        self.setLayout(layout)

def sanitize_filename(title):
    # Remove invalid characters for Windows filenames
    return re.sub(r'[\\/:*?"<>|]', '', title)

class DownloaderUI(QWidget):
    def __init__(self):
        super().__init__()
        self.language = 'th'  # 'th' = ไทย, 'en' = English
        self.setWindowTitle('YouTube MP3 Downloader')
        self.setMinimumSize(1200, 900)
        self.resize(1400, 1000)
        self.init_ui()
        self.thumbnail_pixmap = None

    def set_language(self, lang):
        self.language = lang
        if lang == 'en':
            self.url_label.setText('YouTube Link:')
            self.url_input.setPlaceholderText('https://www.youtube.com/watch?v=...')
            self.confirm_btn.setText('Confirm')
            self.cookies_label.setText('cookies.txt (optional):')
            self.cookies_input.setPlaceholderText('Select cookies.txt file')
            self.cookies_btn.setText('Browse')
            self.output_label.setText('Output Folder:')
            self.output_input.setPlaceholderText('Select download folder')
            self.output_btn.setText('Browse')
            self.format_label.setText('Download Format:')
            self.format_mp3.setText('MP3 (audio only)')
            self.format_mp4.setText('MP4 (video+audio)')
            self.download_btn.setText('Download')
            self.status_label.setText('')
            self.lang_btn.setText('เปลี่ยนเป็นภาษาไทย')
        else:
            self.url_label.setText('ลิงก์ YouTube:')
            self.url_input.setPlaceholderText('https://www.youtube.com/watch?v=...')
            self.confirm_btn.setText('ยืนยัน')
            self.cookies_label.setText('cookies.txt (ถ้ามี):')
            self.cookies_input.setPlaceholderText('เลือกไฟล์ cookies.txt')
            self.cookies_btn.setText('เลือกไฟล์')
            self.output_label.setText('โฟลเดอร์ปลายทาง:')
            self.output_input.setPlaceholderText('เลือกโฟลเดอร์ดาวน์โหลด')
            self.output_btn.setText('เลือกโฟลเดอร์')
            self.format_label.setText('เลือกรูปแบบไฟล์:')
            self.format_mp3.setText('MP3 (เสียงเท่านั้น)')
            self.format_mp4.setText('MP4 (วิดีโอ+เสียง)')
            self.download_btn.setText('ดาวน์โหลด')
            self.status_label.setText('')
            self.lang_btn.setText('Switch to English')
        self.title_label.setText('')
        self.filename_label.setText('')

    def fetch_title(self, url):
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get('title', '')
        except Exception:
            return ''

    def fetch_resolutions(self, url):
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                resolutions = set()
                for f in info.get('formats', []):
                    if f.get('vcodec') != 'none' and f.get('ext') == 'mp4' and f.get('height'):
                        resolutions.add(f['height'])
                return sorted(resolutions, reverse=True)
        except Exception:
            return []

    def show_loading(self):
        self.loading_dialog = LoadingDialog(self)
        self.loading_dialog.show()
        QApplication.processEvents()

    def hide_loading(self):
        if hasattr(self, 'loading_dialog') and self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None

    def on_url_changed(self):
        # reset เฉยๆ ไม่ fetch อัตโนมัติ
        self.resolution_combo.clear()
        self.resolution_combo.setEnabled(False)
        self.current_title = ''
        self.title_label.setText('')
        self.filename_label.setText('')

    def on_confirm_url(self):
        url = self.url_input.text().strip()
        search_query = url  # search_query คือข้อความค้นหาจริง (ไม่เติม ytsearch1:)
        if url and not (url.startswith('http://') or url.startswith('https://')):
            url = f"ytsearch1:{url}"
        self._current_url_for_fetch = url
        if not url or url == 'ytsearch1:':
            self.url_label.setText(self.tr('ลิงก์ YouTube:') if self.language == 'th' else 'YouTube Link:')
            self.thumbnail_label.clear()
            self.thumbnail_label.setVisible(False)
            self.resolution_combo.clear()
            self.resolution_combo.setEnabled(False)
            return
        self.show_loading()
        self.url_label.setText(self.tr('ลิงก์ YouTube:') if self.language == 'th' else 'YouTube Link:')
        self.thumbnail_label.clear()
        self.thumbnail_label.setVisible(False)
        self.resolution_combo.clear()
        self.resolution_combo.setEnabled(False)
        self.title_res_worker = TitleAndResWorker(url, search_query)
        self.title_res_worker.result.connect(self.on_title_and_res_ready)
        self.title_res_worker.start()

    def on_title_and_res_ready(self, title, resolutions, search_query, thumbnail_url):
        self.hide_loading()
        self.current_title = title
        print(f"[DEBUG] yt-dlp title: '{title}' | search_query: '{search_query}' | thumbnail: '{thumbnail_url}'")
        # Always show the real YouTube title if available
        if title:
            filename = sanitize_filename(title)
            ext = 'mp3' if self.selected_format == 'mp3' else 'mp4'
            if self.language == 'th':
                self.title_label.setText(f"ชื่อวิดีโอ: {title}")
                self.filename_label.setText(f"ชื่อไฟล์: {filename}.{ext}")
            else:
                self.title_label.setText(f"Video Title: {title}")
                self.filename_label.setText(f"File name: {filename}.{ext}")
        else:
            self.title_label.setText(self.tr('ไม่พบวิดีโอ') if self.language == 'th' else 'Video not found')
            self.filename_label.setText('')
        # โหลดและแสดง thumbnail
        if thumbnail_url:
            try:
                from urllib.request import urlopen
                from PyQt5.QtGui import QImage
                img_data = urlopen(thumbnail_url).read()
                image = QImage()
                image.loadFromData(img_data)
                pixmap = QPixmap.fromImage(image)
                self.thumbnail_label.setPixmap(pixmap.scaled(self.thumbnail_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.thumbnail_label.setVisible(True)
            except Exception as e:
                print(f"[DEBUG] thumbnail load error: {e}")
                self.thumbnail_label.clear()
                self.thumbnail_label.setVisible(False)
        else:
            self.thumbnail_label.clear()
            self.thumbnail_label.setVisible(False)
        self.resolution_combo.clear()
        if self.selected_format == 'mp4' and resolutions:
            for r in resolutions:
                self.resolution_combo.addItem(f"{r}p")
            self.resolution_combo.setEnabled(True)
            self.resolution_combo.setCurrentIndex(0)
        else:
            self.resolution_combo.setEnabled(False)

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        # ปุ่มสลับภาษาเล็กๆ มุมขวาบน
        topbar = QHBoxLayout()
        topbar.setSpacing(0)
        topbar.addStretch(1)
        self.lang_btn = QPushButton()
        self.lang_btn.setFixedSize(200, 60)
        self.lang_btn.clicked.connect(self.toggle_language)
        self.lang_btn.setStyleSheet('''
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e0e7ff, stop:1 #b0c7f7);
                color: #2566d8;
                border: none;
                border-radius: 20px;
                font-size: 18px;
                font-weight: bold;
                padding: 8px 20px;
                min-width: 140px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b0c7f7, stop:1 #e0e7ff);
                color: #174ea6;
            }
        ''')
        topbar.addWidget(self.lang_btn)
        layout.addLayout(topbar)

        # Thumbnail อยู่บนสุด
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setFixedHeight(200)
        self.thumbnail_label.setFixedWidth(340)
        self.thumbnail_label.setStyleSheet('background: #e0e7ff; border-radius: 12px;')
        self.thumbnail_label.setVisible(False)
        layout.addWidget(self.thumbnail_label, alignment=Qt.AlignHCenter)

        # --- แยก label ชื่อวิดีโอ/ชื่อไฟล์ ---
        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet('''
            QLabel {
                color: #2566d8;
                font-weight: bold;
                font-size: 26px;
                max-width: 1200px;
                padding-bottom: 0px;
                padding-top: 0px;
            }
        ''')
        layout.addWidget(self.title_label)
        self.filename_label = QLabel()
        self.filename_label.setWordWrap(True)
        self.filename_label.setStyleSheet('''
            QLabel {
                color: #888;
                font-size: 22px;
                max-width: 1200px;
                padding-bottom: 0px;
                padding-top: 0px;
            }
        ''')
        layout.addWidget(self.filename_label)

        # ช่องกรอก URL (label อยู่บน)
        self.url_label = QLabel()
        self.url_label.setWordWrap(True)
        self.url_label.setStyleSheet('''
            QLabel {
                color: #222;
                font-weight: bold;
                letter-spacing: 0.5px;
                font-size: 22px;
                max-width: 1200px;
                padding-bottom: 0px;
                padding-top: 0px;
            }
        ''')
        self.url_input = QLineEdit()
        self.url_input.setMinimumHeight(72)
        self.url_input.setMinimumWidth(900)
        self.url_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.confirm_btn = QPushButton()
        self.confirm_btn.setMinimumHeight(72)
        self.confirm_btn.setMinimumWidth(200)
        self.confirm_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.confirm_btn.clicked.connect(self.on_confirm_url)
        url_row = QVBoxLayout()
        url_row.setSpacing(0)
        url_row.addWidget(self.url_label)
        url_input_row = QHBoxLayout()
        url_input_row.setSpacing(4)
        url_input_row.addWidget(self.url_input, stretch=1)
        url_input_row.addWidget(self.confirm_btn, alignment=Qt.AlignRight)
        url_row.addLayout(url_input_row)
        layout.addLayout(url_row)

        # --- cookies.txt (label อยู่บน) ---
        self.cookies_label = QLabel()
        self.cookies_label.setStyleSheet('font-size: 20px; color: #222; font-weight: bold;')
        self.cookies_input = QLineEdit()
        self.cookies_input.setMinimumHeight(60)
        self.cookies_input.setMinimumWidth(800)
        # --- set default cookies path ---
        default_cookies = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'www.youtube.com_cookies.txt')
        if os.path.exists(default_cookies):
            self.cookies_input.setText(default_cookies)
        self.cookies_btn = QPushButton()
        self.cookies_btn.setMinimumHeight(60)
        self.cookies_btn.setMinimumWidth(180)
        self.cookies_btn.clicked.connect(self.browse_cookies)
        cookies_vbox = QVBoxLayout()
        cookies_vbox.setSpacing(0)
        cookies_vbox.addWidget(self.cookies_label)
        cookies_hbox = QHBoxLayout()
        cookies_hbox.setSpacing(4)
        cookies_hbox.addWidget(self.cookies_input)
        cookies_hbox.addWidget(self.cookies_btn)
        cookies_vbox.addLayout(cookies_hbox)
        layout.addLayout(cookies_vbox)

        # --- output folder (label อยู่บน) ---
        self.output_label = QLabel()
        self.output_label.setStyleSheet('font-size: 20px; color: #222; font-weight: bold;')
        self.output_input = QLineEdit()
        self.output_input.setMinimumHeight(60)
        self.output_input.setMinimumWidth(800)
        self.output_btn = QPushButton()
        self.output_btn.setMinimumHeight(60)
        self.output_btn.setMinimumWidth(180)
        self.output_btn.clicked.connect(self.browse_output)
        output_vbox = QVBoxLayout()
        output_vbox.setSpacing(0)
        output_vbox.addWidget(self.output_label)
        output_hbox = QHBoxLayout()
        output_hbox.setSpacing(4)
        output_hbox.addWidget(self.output_input)
        output_hbox.addWidget(self.output_btn)
        output_vbox.addLayout(output_hbox)
        layout.addLayout(output_vbox)

        # Format selection row
        self.format_label = QLabel()
        self.format_mp3 = QPushButton()
        self.format_mp4 = QPushButton()
        self.format_mp3.setCheckable(True)
        self.format_mp4.setCheckable(True)
        self.format_mp3.setChecked(True)
        self.format_mp3.setMinimumHeight(80)
        self.format_mp3.setMinimumWidth(250)
        self.format_mp4.setMinimumHeight(80)
        self.format_mp4.setMinimumWidth(250)
        self.format_mp3.clicked.connect(lambda: self.set_format('mp3'))
        self.format_mp4.clicked.connect(lambda: self.set_format('mp4'))
        self.format_mp3.setStyleSheet(self.format_btn_style(True))
        self.format_mp4.setStyleSheet(self.format_btn_style(False))
        self.resolution_combo = QComboBox()
        self.resolution_combo.setMinimumHeight(80)
        self.resolution_combo.setMinimumWidth(250)
        self.resolution_combo.setEnabled(False)
        format_row = QHBoxLayout()
        format_row.setSpacing(4)
        format_row.addWidget(self.format_label)
        format_row.addWidget(self.format_mp3)
        format_row.addWidget(self.format_mp4)
        format_row.addWidget(self.resolution_combo)
        format_row.addStretch(1)
        layout.addLayout(format_row)

        self.download_btn = QPushButton()
        self.download_btn.setMinimumHeight(120)
        self.download_btn.setMinimumWidth(400)
        self.download_btn.clicked.connect(self.start_download)

        self.status_label = QLabel('')
        self.status_label.setObjectName('statusLabel')
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setMinimumHeight(32)

        self.progress_label = QLabel('')
        self.progress_label.setVisible(False)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(40)
        self.progress_bar.setMinimumWidth(600)
        self.progress_bar.setVisible(False)  # ซ่อน progress bar ตอนแรก

        layout.addWidget(self.download_btn)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.setStretch(0, 0)
        layout.setStretch(1, 0)
        layout.setStretch(2, 0)
        layout.setStretch(3, 0)
        layout.setStretch(4, 0)
        layout.setStretch(5, 0)
        layout.setStretch(6, 0)
        layout.setStretch(7, 0)
        layout.setSpacing(0)

        self.setLayout(layout)
        self.set_language(self.language)
        self.selected_format = 'mp3'

        mp3_icon = QIcon()
        mp4_icon = QIcon()
        try:
            mp3_icon.addFile(os.path.join(os.path.dirname(__file__), 'mp3_icon.png'))
            mp4_icon.addFile(os.path.join(os.path.dirname(__file__), 'mp4_icon.png'))
        except Exception:
            pass
        self.format_mp3.setIcon(mp3_icon)
        self.format_mp4.setIcon(mp4_icon)
        self.format_mp3.setIconSize(QSize(40, 40))
        self.format_mp4.setIconSize(QSize(40, 40))

        self.url_input.textChanged.connect(self.on_url_changed)

    def on_title_and_res_ready(self, title, resolutions, search_query, thumbnail_url):
        self.hide_loading()
        self.current_title = title
        print(f"[DEBUG] yt-dlp title: '{title}' | search_query: '{search_query}' | thumbnail: '{thumbnail_url}'")
        # Always show the real YouTube title if available
        if title:
            filename = sanitize_filename(title)
            ext = 'mp3' if self.selected_format == 'mp3' else 'mp4'
            if self.language == 'th':
                self.title_label.setText(f"ชื่อวิดีโอ: {title}")
                self.filename_label.setText(f"ชื่อไฟล์: {filename}.{ext}")
            else:
                self.title_label.setText(f"Video Title: {title}")
                self.filename_label.setText(f"File name: {filename}.{ext}")
        else:
            self.title_label.setText(self.tr('ไม่พบวิดีโอ') if self.language == 'th' else 'Video not found')
            self.filename_label.setText('')
        # โหลดและแสดง thumbnail
        if thumbnail_url:
            try:
                from urllib.request import urlopen
                from PyQt5.QtGui import QImage
                img_data = urlopen(thumbnail_url).read()
                image = QImage()
                image.loadFromData(img_data)
                pixmap = QPixmap.fromImage(image)
                self.thumbnail_label.setPixmap(pixmap.scaled(self.thumbnail_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.thumbnail_label.setVisible(True)
            except Exception as e:
                print(f"[DEBUG] thumbnail load error: {e}")
                self.thumbnail_label.clear()
                self.thumbnail_label.setVisible(False)
        else:
            self.thumbnail_label.clear()
            self.thumbnail_label.setVisible(False)
        self.resolution_combo.clear()
        if self.selected_format == 'mp4' and resolutions:
            for r in resolutions:
                self.resolution_combo.addItem(f"{r}p")
            self.resolution_combo.setEnabled(True)
            self.resolution_combo.setCurrentIndex(0)
        else:
            self.resolution_combo.setEnabled(False)

    def on_url_changed(self):
        # reset เฉยๆ ไม่ fetch อัตโนมัติ
        self.resolution_combo.clear()
        self.resolution_combo.setEnabled(False)
        self.current_title = ''
        self.title_label.setText('')
        self.filename_label.setText('')

    def set_language(self, lang):
        self.language = lang
        if lang == 'en':
            self.url_label.setText('YouTube Link:')
            self.url_input.setPlaceholderText('https://www.youtube.com/watch?v=...')
            self.confirm_btn.setText('Confirm')
            self.cookies_label.setText('cookies.txt (optional):')
            self.cookies_input.setPlaceholderText('Select cookies.txt file')
            self.cookies_btn.setText('Browse')
            self.output_label.setText('Output Folder:')
            self.output_input.setPlaceholderText('Select download folder')
            self.output_btn.setText('Browse')
            self.format_label.setText('Download Format:')
            self.format_mp3.setText('MP3 (audio only)')
            self.format_mp4.setText('MP4 (video+audio)')
            self.download_btn.setText('Download')
            self.status_label.setText('')
            self.lang_btn.setText('เปลี่ยนเป็นภาษาไทย')
        else:
            self.url_label.setText('ลิงก์ YouTube:')
            self.url_input.setPlaceholderText('https://www.youtube.com/watch?v=...')
            self.confirm_btn.setText('ยืนยัน')
            self.cookies_label.setText('cookies.txt (ถ้ามี):')
            self.cookies_input.setPlaceholderText('เลือกไฟล์ cookies.txt')
            self.cookies_btn.setText('เลือกไฟล์')
            self.output_label.setText('โฟลเดอร์ปลายทาง:')
            self.output_input.setPlaceholderText('เลือกโฟลเดอร์ดาวน์โหลด')
            self.output_btn.setText('เลือกโฟลเดอร์')
            self.format_label.setText('เลือกรูปแบบไฟล์:')
            self.format_mp3.setText('MP3 (เสียงเท่านั้น)')
            self.format_mp4.setText('MP4 (วิดีโอ+เสียง)')
            self.download_btn.setText('ดาวน์โหลด')
            self.status_label.setText('')
            self.lang_btn.setText('Switch to English')
        self.title_label.setText('')
        self.filename_label.setText('')

    def start_download(self):
        url = self.url_input.text().strip()
        # ถ้าไม่ใช่ลิงก์ youtube ให้ค้นหาใน youtube
        if url and not (url.startswith('http://') or url.startswith('https://')):
            url = f"ytsearch1:{url}"
        if not (url.startswith('http://') or url.startswith('https://') or url.startswith('ytsearch1:')):
            QMessageBox.warning(self, self.tr('ข้อผิดพลาด') if self.language == 'th' else 'Error',
                                self.tr('กรุณากรอกลิงก์ YouTube ที่ถูกต้อง หรือชื่อวิดีโอ') if self.language == 'th' else 'Please enter a valid YouTube link or video title')
            return
        cookies = self.cookies_input.text().strip()
        output = self.output_input.text().strip()
        if not output:
            output = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')
        fmt = self.selected_format
        resolution = None
        if fmt == 'mp4' and self.resolution_combo.count() > 0:
            resolution = self.resolution_combo.currentText().replace('p', '')
        self.status_label.setText(self.tr('กำลังดาวน์โหลด...') if self.language == 'th' else 'Downloading...')
        self.download_btn.setEnabled(False)
        self.progress_label.setVisible(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat('0%')
        self.progress_bar.setVisible(True)
        self.show_loading()  # แสดง loading dialog ตอนเริ่มดาวน์โหลด
        self.worker = DownloadWorker(url, cookies if cookies else None, output, fmt, resolution)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_download_finished)
        self.worker.error.connect(self.on_download_error)
        self.worker.start()

    def on_progress(self, percent):
        self.progress_bar.setValue(int(percent))
        self.progress_bar.setFormat(f'{percent:.1f}%')

    def on_download_finished(self, msg):
        self.hide_loading()  # ปิด loading dialog เมื่อเสร็จ
        self.status_label.setText(self.tr('ดาวน์โหลดและแปลงไฟล์เสร็จสิ้น!') if self.language == 'th' else 'Download and conversion complete!')
        self.download_btn.setEnabled(True)
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat('100%')
        self.progress_bar.setVisible(False)

    def on_download_error(self, msg):
        self.hide_loading()  # ปิด loading dialog เมื่อ error
        self.status_label.setText((self.tr('เกิดข้อผิดพลาด:') if self.language == 'th' else 'Error:') + f' {msg}')
        self.download_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat('0%')
        self.progress_bar.setVisible(False)

    def toggle_language(self):
        # Toggle language and update UI
        if self.language == 'th':
            self.set_language('en')
        else:
            self.set_language('th')
        # Update title/filename label if video info is already loaded
        if hasattr(self, 'current_title') and self.current_title:
            filename = sanitize_filename(self.current_title)
            ext = 'mp3' if getattr(self, 'selected_format', 'mp3') == 'mp3' else 'mp4'
            if self.language == 'th':
                self.title_label.setText(f"ชื่อวิดีโอ: {self.current_title}")
                self.filename_label.setText(f"ชื่อไฟล์: {filename}.{ext}")
            else:
                self.title_label.setText(f"Video Title: {self.current_title}")
                self.filename_label.setText(f"File name: {filename}.{ext}")
        elif self.url_input.text().strip() == '':
            self.title_label.setText('')
            self.filename_label.setText('')
        # Update status label if needed
        if self.status_label.text() in ['ไม่พบวิดีโอ', 'Video not found']:
            self.status_label.setText('ไม่พบวิดีโอ' if self.language == 'th' else 'Video not found')


    def browse_cookies(self):
        file_path, _ = QFileDialog.getOpenFileName(self, self.tr('เลือก cookies.txt') if self.language == 'th' else 'Select cookies.txt', '', 'Text Files (*.txt);;All Files (*)')
        if file_path:
            self.cookies_input.setText(file_path)

    def browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr('เลือกโฟลเดอร์ดาวน์โหลด') if self.language == 'th' else 'Select download folder', os.getcwd())
        if folder:
            self.output_input.setText(folder)

    def format_btn_style(self, active):
        if active:
            return '''
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2566d8, stop:1 #4f8cff);
                    color: #fff;
                    border: 2px solid #2566d8;
                    border-radius: 10px;
                    padding: 12px 28px;
                    font-size: 17px;
                    font-weight: bold;
                }
            '''
        else:
            return '''
                QPushButton {
                    background: #e0e7ff;
                    color: #2566d8;
                    border: 2px solid #b0c7f7;
                    border-radius: 10px;
                    padding: 12px 28px;
                    font-size: 17px;
                    font-weight: bold;
                }
            '''

    def set_format(self, fmt):
        self.selected_format = fmt
        self.format_mp3.setChecked(fmt == 'mp3')
        self.format_mp4.setChecked(fmt == 'mp4')
        self.format_mp3.setStyleSheet(self.format_btn_style(fmt == 'mp3'))
        self.format_mp4.setStyleSheet(self.format_btn_style(fmt == 'mp4'))
        url = self.url_input.text().strip()
        search_query = url  # search_query คือข้อความค้นหาจริง (ไม่เติม ytsearch1:)
        if url and not (url.startswith('http://') or url.startswith('https://')):
            url = f"ytsearch1:{url}"
        if fmt == 'mp4' and url:
            self.show_loading()
            self.resolution_combo.setEnabled(False)
            self.resolution_combo.clear()
            self.title_res_worker = TitleAndResWorker(url, search_query)
            self.title_res_worker.result.connect(self.on_title_and_res_ready)
            self.title_res_worker.start()
        elif fmt == 'mp3':
            self.resolution_combo.setEnabled(False)
            self.resolution_combo.clear()

def main():
    app = QApplication(sys.argv)
    window = DownloaderUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
