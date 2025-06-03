import streamlit as st
import yt_dlp
import os
import tempfile
import re
from PIL import Image
import requests

def sanitize_filename(title):
    return re.sub(r'[\\/:*?"<>|]', '', title)

def get_video_info(url, cookies_path=None):
    ydl_opts = {'quiet': True}
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

def download_video(url, fmt, resolution, cookies_path=None):
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            'outtmpl': os.path.join(tmpdir, '%(title)s.%(ext)s'),
            'quiet': True,
            'windowsfilenames': True,
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
            result = ydl.download([url])
        # Find the downloaded file
        for f in os.listdir(tmpdir):
            if f.endswith('.mp3') or f.endswith('.mp4'):
                return os.path.join(tmpdir, f)
        return None

def main():
    st.set_page_config(page_title="YouTube MP3/MP4 Downloader", layout="wide")
    st.title("YouTube MP3/MP4 Downloader (Web Version)")
    lang = st.radio("Language / ภาษา", ["English", "ไทย"], horizontal=True)
    is_th = lang == "ไทย"
    url = st.text_input("YouTube Link or Video Name" if not is_th else "ลิงก์ YouTube หรือชื่อวิดีโอ")
    cookies_file = st.file_uploader("cookies.txt (optional)" if not is_th else "cookies.txt (ถ้ามี)", type=["txt"])
    fetch_btn = st.button("Fetch Info" if not is_th else "ดึงข้อมูลวิดีโอ")
    video_info = None
    if fetch_btn and url:
        with st.spinner("Fetching info..."):
            cookies_path = None
            if cookies_file:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as tmp:
                    tmp.write(cookies_file.read())
                    cookies_path = tmp.name
            try:
                search_url = url if url.startswith('http') else f"ytsearch1:{url}"
                title, thumbnail, resolutions = get_video_info(search_url, cookies_path)
                video_info = (title, thumbnail, resolutions)
            except Exception as e:
                st.error(f"Error: {e}")
    if video_info or (fetch_btn and url):
        title, thumbnail, resolutions = video_info if video_info else ("", "", [])
        if title:
            st.success(("ชื่อวิดีโอ: " if is_th else "Video Title: ") + title)
            if thumbnail:
                st.image(thumbnail, width=320)
            filename = sanitize_filename(title)
            st.write(("ชื่อไฟล์: " if is_th else "File name: ") + filename)
            fmt = st.radio(("เลือกรูปแบบไฟล์:" if is_th else "Download Format:"), ["MP3", "MP4"], horizontal=True)
            selected_fmt = 'mp3' if fmt == "MP3" else 'mp4'
            selected_res = None
            if selected_fmt == 'mp4' and resolutions:
                res_strs = [f"{r}p" for r in resolutions]
                res = st.selectbox(("เลือกความละเอียดวิดีโอ:" if is_th else "Select Resolution:"), res_strs)
                selected_res = int(res.replace('p',''))
            else:
                selected_res = None
            if st.button("Download" if not is_th else "ดาวน์โหลด"):
                with st.spinner("Downloading..."):
                    cookies_path = None
                    if cookies_file:
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as tmp:
                            tmp.write(cookies_file.read())
                            cookies_path = tmp.name
                    try:
                        search_url = url if url.startswith('http') else f"ytsearch1:{url}"
                        out_path = download_video(search_url, selected_fmt, selected_res, cookies_path)
                        if out_path:
                            with open(out_path, "rb") as f:
                                btn_label = "Download File" if not is_th else "ดาวน์โหลดไฟล์"
                                st.download_button(btn_label, f, file_name=os.path.basename(out_path))
                        else:
                            st.error("Download failed.")
                    except Exception as e:
                        st.error(f"Error: {e}")

if __name__ == "__main__":
    main()
