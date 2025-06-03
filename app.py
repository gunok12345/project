from flask import Flask, render_template, request, send_file, jsonify, after_this_request
import yt_dlp
import os
import tempfile
import re
import unicodedata
import threading

app = Flask(__name__)

def sanitize_filename(title):
    # Normalize Unicode
    title = unicodedata.normalize('NFKC', title)
    # Remove forbidden characters (Windows/macOS/Linux)
    forbidden = '<>:"/\\|?*\n\r\t'
    sanitized = ''.join(c for c in title if c not in forbidden)
    # Remove leading/trailing space, dot, dash, underscore
    sanitized = sanitized.strip(' .-_')
    # Replace multiple spaces/underscores/dashes with single space
    sanitized = re.sub(r'[ \-_]+', ' ', sanitized)
    # Limit length
    sanitized = sanitized[:80]
    # Fallback if empty
    if not sanitized:
        sanitized = "video"
    return sanitized

def get_video_info(url, cookies_path=None):
    # Always use www.youtube.com_cookies.txt as default if exists
    default_cookies_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '/www.youtube.com_cookies.txt')
    if not cookies_path and os.path.exists(default_cookies_path):
        cookies_path = default_cookies_path
    print(f"[DEBUG] get_video_info: cookies_path = {cookies_path}")
    ydl_opts = {
        'quiet': True,
        'ffmpeg_location': r'C:\Program Files\ffmpeg-master-latest-win64-gpl-shared\bin',
    }
    if cookies_path:
        ydl_opts['cookiefile'] = cookies_path
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if 'entries' in info and info['entries']:
            entry = next((e for e in info['entries'] if e and e.get('title')), info['entries'][0])
        else:
            entry = info
        title = entry.get('title', '')
        thumbnail = entry.get('thumbnail', '')
        formats = entry.get('formats', [])
        resolutions = sorted({f['height'] for f in formats if f.get('vcodec') != 'none' and f.get('ext') == 'mp4' and f.get('height')}, reverse=True)
        return title, thumbnail, resolutions

def download_video(url, fmt, resolution, cookies_path=None, custom_filename=None, output_dir=None):
    import shutil
    import time
    import json
    import os
    from unidecode import unidecode
    # Always use www.youtube.com_cookies.txt as default if exists
    default_cookies_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'www.youtube.com_cookies.txt')
    if not cookies_path and os.path.exists(default_cookies_path):
        cookies_path = default_cookies_path
    print(f"[DEBUG] download_video: cookies_path = {cookies_path}")
    with tempfile.TemporaryDirectory() as tmpdir:
        if custom_filename:
            safe_name = sanitize_filename(custom_filename)[:80]
        else:
            title, _, _ = get_video_info(url, cookies_path)
            safe_name = sanitize_filename(title)[:80]
        ext = 'mp3' if fmt == 'mp3' else 'mp4'
        outtmpl = os.path.join(tmpdir, 'yt-dlp-tmp.%(ext)s')
        ydl_opts = {
            'outtmpl': outtmpl,
            'quiet': True,
            'windowsfilenames': True,
            'ffmpeg_location': r'C:\Program Files\ffmpeg-master-latest-win64-gpl-shared\bin',
            'writeinfojson': True,
        }
        if cookies_path:
            ydl_opts['cookiefile'] = cookies_path
        if fmt == 'mp3':
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        elif fmt == 'mp4':
            if resolution:
                ydl_opts.update({
                    'format': f"bestvideo[ext=mp4][vcodec!=none][height={resolution}]+bestaudio[ext=m4a]/mp4",
                    'merge_output_format': 'mp4',
                })
            else:
                ydl_opts.update({
                    'format': 'bestvideo[ext=mp4][vcodec!=none][height<=1080]+bestaudio[ext=m4a]/mp4',
                    'merge_output_format': 'mp4',
                })
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([url])
            except Exception as e:
                print('[yt-dlp error]', e)
        print('[DEBUG] tmpdir files:')
        for f in os.listdir(tmpdir):
            fp = os.path.join(tmpdir, f)
            print(f"  {f} | size={os.path.getsize(fp)} | ctime={time.ctime(os.path.getctime(fp))}")
        # --- robust: หาไฟล์ output จาก infojson yt-dlp ---
        infojson_path = os.path.join(tmpdir, 'yt-dlp-tmp.info.json')
        src = None
        if os.path.exists(infojson_path):
            try:
                import json
                with open(infojson_path, 'r', encoding='utf-8') as jf:
                    info = json.load(jf)
                # yt-dlp >=2023.10.07: 'requested_downloads' มี 'filepath'
                if 'requested_downloads' in info and info['requested_downloads']:
                    src_candidate = info['requested_downloads'][0].get('filepath')
                    if src_candidate and os.path.exists(src_candidate):
                        src = src_candidate
                        print(f'[DEBUG] found output file from infojson: {src}')
                # yt-dlp <2023: อาจมี '_filename'
                if not src and '_filename' in info and os.path.exists(info['_filename']):
                    src = info['_filename']
                    print(f'[DEBUG] found output file from infojson (_filename): {src}')
            except Exception as e:
                print(f'[DEBUG] error reading infojson: {e}')
        if not src:
            # --- fallback: หาไฟล์ที่ชื่อไฟล์ตรงกับ safe_name ก่อน ---
            target_filename = safe_name + f'.{ext}'
            target_path = os.path.join(tmpdir, target_filename)
            import time as _time
            found = False
            for _ in range(6):  # wait up to 3s (6*0.5s)
                if os.path.exists(target_path):
                    found = True
                    break
                _time.sleep(0.5)
            if found:
                src = target_path
                print(f'[DEBUG] found output file: {src}')
            else:
                # fallback: หาไฟล์ .mp3/.mp4 ที่ใหญ่สุด/ล่าสุดใน temp
                candidates = [f for f in os.listdir(tmpdir) if f.endswith(f'.{ext}')]
                if not candidates:
                    candidates = [f for f in os.listdir(tmpdir) if f.endswith('.mp3') or f.endswith('.mp4')]
                if not candidates:
                    print('[DEBUG] No output file found in temp!')
                    return None
                candidates_full = [(f, os.path.getsize(os.path.join(tmpdir, f)), os.path.getctime(os.path.join(tmpdir, f))) for f in candidates]
                candidates_full.sort(key=lambda x: (x[2], x[1]), reverse=True)
                src = os.path.join(tmpdir, candidates_full[0][0])
                print(f'[DEBUG] fallback to file: {src}')
                # log กรณีเป็น uuid/ชื่อมั่ว
                if os.path.basename(src) != target_filename:
                    print(f'[DEBUG] WARNING: output file is not safe_name! Got {os.path.basename(src)} expected {target_filename}')
        # --- copy/rename ไฟล์เป็นชื่อที่ต้องการ ---
        if not output_dir:
            output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'asset'))
        dst_dir = output_dir
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, safe_name + f'.{ext}')
        i = 1
        dst_names = [os.path.basename(dst)]
        while os.path.exists(dst):
            dst = os.path.join(dst_dir, f"{safe_name} ({i}).{ext}")
            dst_names.append(os.path.basename(dst))
            i += 1
        try:
            # ไม่ว่า src จะชื่อ uuid หรือไม่ ให้ copy/rename เป็น safe_name เสมอ
            with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
                fdst.write(fsrc.read())
            print(f'[DEBUG] copied file to {dst}')
        except Exception as e:
            print(f'[DEBUG] copy/rename failed: {e}')
            return None
        # --- robust: ลบไฟล์ uuid/ชื่อมั่วใน output_dir ทันทีหลังดาวน์โหลด ---
        allowed_filenames = set(dst_names)
        for f in os.listdir(dst_dir):
            if f.endswith(f'.{ext}') and f not in allowed_filenames:
                try:
                    os.remove(os.path.join(dst_dir, f))
                    print(f'[DEBUG] removed extra file: {f}')
                except Exception as e:
                    print(f'[DEBUG] error removing extra file: {f}', e)
        print('[DEBUG] downloads dir:')
        for f in os.listdir(dst_dir):
            print(' ', f)
        # --- ห้ามลบไฟล์ทั้งหมดใน asset ที่นี่ ---
        return dst

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/fetch_info", methods=["POST"])
def fetch_info():
    url = request.form.get("url")
    lang = request.form.get("lang", "en")
    cookies = request.files.get("cookies")
    cookies_path = None
    if cookies:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.txt')
        cookies.save(tmp.name)
        cookies_path = tmp.name
    try:
        search_url = url if url.startswith('http') else f"ytsearch1:{url}"
        print(f"[DEBUG] /fetch_info: cookies_path = {cookies_path}")
        title, thumbnail, resolutions = get_video_info(search_url, cookies_path)
        filename = sanitize_filename(title)
        return jsonify({
            'title': title,
            'thumbnail': thumbnail,
            'resolutions': resolutions,
            'filename': filename
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url")
    fmt = request.form.get("fmt")
    res = request.form.get("res")
    output_dir = request.form.get("output_dir")  # รับ path โฟลเดอร์ปลายทางจากผู้ใช้
    cookies = request.files.get("cookies")
    cookies_path = None
    if cookies:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.txt')
        cookies.save(tmp.name)
        cookies_path = tmp.name
    try:
        search_url = url if url.startswith('http') else f"ytsearch1:{url}"
        resolution = int(res) if res and res.isdigit() else None
        print(f"[DEBUG] /download: cookies_path = {cookies_path}")
        # ดึง title จริงจาก get_video_info
        title, _, _ = get_video_info(search_url, cookies_path)
        print(f"[DEBUG] download: url={search_url}, fmt={fmt}, res={resolution}, cookies_path={cookies_path}, title={title}, output_dir={output_dir}")
        out_path = download_video(search_url, fmt, resolution, cookies_path, custom_filename=title, output_dir=output_dir)
        print(f"[DEBUG] download: out_path={out_path}")
        asset_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'asset'))
        def cleanup_asset():
            try:
                for f in os.listdir(asset_dir):
                    fp = os.path.join(asset_dir, f)
                    if os.path.isfile(fp):
                        try:
                            os.remove(fp)
                            print(f'[DEBUG] asset cleanup: removed {fp}')
                        except Exception as e:
                            print(f'[DEBUG] asset cleanup error: {fp}', e)
            except Exception as e:
                print(f'[DEBUG] asset cleanup error (outer):', e)
        if out_path:
            # ถ้า output_dir คือ asset ให้ลบไฟล์หลัง delay 3 วินาที
            if (not output_dir) or (os.path.abspath(output_dir) == asset_dir):
                threading.Timer(3.0, cleanup_asset).start()
            return send_file(out_path, as_attachment=True, download_name=os.path.basename(out_path))
        else:
            print('Download failed: No output file found')
            return "Download failed", 500
    except Exception as e:
        import traceback
        print('Download error:', e)
        traceback.print_exc()
        return str(e), 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
