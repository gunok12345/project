# YouTube MP3/MP4 Downloader (Flask + yt-dlp)

## Features
- Download YouTube as MP3/MP4 (choose resolution)
- Unicode/Thai filename support
- Choose output folder (or default to `asset`)
- Cookie support (`cookies.txt`)
- Progress bar, real video title, thumbnail, language toggle
- Robust file cleanup (no uuid/garbage in output)
- After download, if output is `asset`, auto-cleanup all files in `asset`

## Deploy on Render.com (or Railway/Heroku)

### 1. Requirements
- Python 3.9+
- `yt-dlp`, `Flask`, `unidecode`, `PyQt5` (for GUI)

### 2. Quickstart (Local)
```sh
pip install -r requirements.txt
python app.py
```

### 3. Deploy to Cloud (Render)
1. Push this repo to GitHub
2. Go to [Render.com](https://render.com/), create new Web Service, connect your repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `python app.py`
5. Wait for deploy, get your public URL

### 4. Project Structure
```
app.py                # Flask backend
Procfile              # For Render/Heroku
requirements.txt      # Python dependencies
asset/                # Default output dir (auto-cleanup after download)
downloads/            # (legacy, not used)
templates/index.html  # Web UI
www.youtube.com_cookies.txt # Example cookies
```

### 5. Notes
- For ffmpeg: On Windows, edit `ffmpeg_location` in `app.py` to your ffmpeg bin path
- For cloud: ffmpeg is available by default on Render/Heroku
- If you want to use GUI: run `youtube_mp3_gui.py` (PyQt5)

---

**Deploy badge:**

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

---

If you have any issues, open an issue or PR!
