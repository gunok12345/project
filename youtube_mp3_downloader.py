import subprocess
import os
import sys

def download_mp3(youtube_url, output_path='downloads', cookies_path=None, file_format='mp3', resolution=None):
    os.makedirs(output_path, exist_ok=True)
    if cookies_path:
        cookies_path = cookies_path.strip('"').strip("'").replace('/', '\\')
        if not os.path.isabs(cookies_path):
            cookies_path = os.path.abspath(cookies_path)
        if not os.path.isfile(cookies_path):
            print(f'ไม่พบไฟล์ cookies.txt ที่ {cookies_path}')
            return
    yt_dlp_cmd = [
        'yt-dlp',
        '-o', os.path.join(output_path, '%(title)s.%(ext)s'),
    ]
    if file_format == 'mp3':
        yt_dlp_cmd += ['--extract-audio', '--audio-format', 'mp3']
    elif file_format == 'mp4':
        if resolution:
            yt_dlp_cmd += ['-f', f"bestvideo[ext=mp4][vcodec!=none][height={resolution}]+bestaudio[ext=m4a]/mp4", '--merge-output-format', 'mp4']
        else:
            yt_dlp_cmd += ['-f', 'bestvideo[ext=mp4][vcodec!=none][height<=1080]+bestaudio[ext=m4a]/mp4', '--merge-output-format', 'mp4']
    if cookies_path:
        yt_dlp_cmd += ['--cookies', cookies_path]
    yt_dlp_cmd.append(youtube_url)
    try:
        result = subprocess.run(
            yt_dlp_cmd,
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print('เกิดข้อผิดพลาด:', result.stderr)
        else:
            print('ดาวน์โหลดและแปลงไฟล์เสร็จสิ้น')
    except FileNotFoundError:
        print('ไม่พบ yt-dlp กรุณาติดตั้งด้วยคำสั่ง: pip install yt-dlp')
    except Exception as e:
        print('เกิดข้อผิดพลาด:', e)
    try:
        import yt_dlp
        ydl_opts = {
            'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
        }
        if file_format == 'mp3':
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        elif file_format == 'mp4':
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
        if cookies_path:
            ydl_opts['cookiefile'] = cookies_path
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
        print('ดาวน์โหลดและแปลงไฟล์เสร็จสิ้น (yt-dlp module)')
    except ImportError:
        print('ไม่พบ yt-dlp ทั้ง executable และ module กรุณาติดตั้งด้วยคำสั่ง: pip install yt-dlp')
    except Exception as e:
        print('เกิดข้อผิดพลาด (yt-dlp module):', e)
