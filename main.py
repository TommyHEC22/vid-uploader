import csv
import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import quote
import os
import time
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.credentials import Credentials
import io
import json
from datetime import datetime
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
import base64
import tempfile
import subprocess
from datetime import datetime, timedelta
import logging
from io import BytesIO
import platform
import moviepy
import shutil
import subprocess

# Prefer Windows path if on Windows, otherwise detect magick or convert on Linux
if platform.system() == "Windows":
    os.environ["IMAGEMAGICK_BINARY"] = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"
else:
    magick_path = shutil.which("magick")
    convert_path = shutil.which("convert")
    if magick_path:
        os.environ["IMAGEMAGICK_BINARY"] = magick_path
    elif convert_path:
        os.environ["IMAGEMAGICK_BINARY"] = convert_path
    else:
        # leave unset — moviepy may still work with imageio fallback; we will warn
        os.environ.pop("IMAGEMAGICK_BINARY", None)

# Debugging information (safe: only call binaries if they exist)
print("Platform:", platform.system())
print("IMAGEMAGICK_BINARY env:", os.environ.get("IMAGEMAGICK_BINARY"))
if os.environ.get("IMAGEMAGICK_BINARY"):
    subprocess.run([os.environ["IMAGEMAGICK_BINARY"], "-version"], check=False)
else:
    print("No ImageMagick binary found on PATH (magick/convert).")


from moviepy import ImageClip, TextClip, CompositeVideoClip, VideoFileClip, vfx

def require_env(name):
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val

YOUTUBE_CLIENT_ID = require_env("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = require_env("YOUTUBE_CLIENT_SECRET")
REFRESH_TOKEN_ENV = require_env("YT_REFRESH_TOKEN")
        
TOKEN_FILE = "token.json"


with open("love_quotes.csv", newline="", encoding="utf-8") as infile:
    reader = csv.reader(infile)
    quotes = list(reader)
    random_quote = random.choice(quotes)

    quotes = random_quote[0]
    authors = random_quote[1]
    category = random_quote[2]

    author = authors.split(",")[0].strip()

    print("Selected Quote:, ", quotes)


def save_author_image(author):
    print(f"Generating AI portrait for: {author}")
    
    # 1. Setup a "Smart" Session that retries automatically on 502/Timeout
    session = requests.Session()
    retry_strategy = Retry(
        total=5, # Try 5 times
        backoff_factor=2, # Wait 2s, 4s, 8s between retries
        status_forcelist=[429, 500, 502, 503, 504], # Retry on these errors
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)

    # 2. Refined Prompt for better consistency
    # Adding "oil painting" and "centered portrait" helps the AI
    prompt = f"Professional oil painting of the person {author}, centered portrait, dark academic style, moody lighting, 18th century, age 30, high detail, 9:16 aspect ratio"
    encoded_prompt = quote(prompt)
    
    # We add a random seed each time so if one fails, the next attempt is 'fresh'
    seed = os.urandom(4).hex()
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=720&height=1280&seed={seed}&nologo=true"

    try:
        # We increase the timeout to 60s because AI generation is slow
        response = session.get(image_url, timeout=60)
        response.raise_for_status()
        
        safe_name = author.replace(" ", "_").lower()
        filename = f"{safe_name}_ai.jpg"
        
        with open(filename, "wb") as f:
            f.write(response.content)
            
        print(f"Successfully generated: {filename}")
        return filename
        
    except Exception as e:
        print(f"AI generation permanently failed for {author}: {e}")
        os._exit(1)
        return None


def create_quote_video(image_path, quotes, author):
    print(f"Creating video for: {author}")
    
    # 1. Select a random audio file
    audio_folder = "audio" 
    random_index = random.randint(1, 19)
    audio_source_path = os.path.join(audio_folder, f"{random_index}.mp4")
    
    video_with_audio = VideoFileClip(audio_source_path)
    audio_clip = video_with_audio.audio
    duration = audio_clip.duration

    # 2. Create the Background Image Clip
    # v2.x use: .with_duration()
    bg_clip = ImageClip(image_path).with_duration(duration)

    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    text_clip = TextClip(
        text=f'"{quotes}"\n\n— {author}',
        fontsize=30,
        color='white',
        font=font_path,  # Use the absolute path here
        stroke_color='black',
        stroke_width=0.5,
        method='caption',
        size=(int(bg_clip.w * 0.7), None),
        align='center'
    ).with_duration(duration).with_position('center')

    # 4. Assemble the Video
    # v2.x use: .with_audio()
    final_video = CompositeVideoClip([bg_clip, text_clip])
    final_video = final_video.with_audio(audio_clip)

    # 5. Add Fade-In Effect
    # v2.x uses a list of effects via .with_effects()
    final_video = final_video.with_effects([vfx.FadeIn(1.5)])

    # 6. Export
    output_filename = f"{author.replace(' ', '_').lower()}_short.mp4"
    final_video.write_videofile(output_filename, fps=24, codec="libx264")
    
    # Clean up
    video_with_audio.close()
    final_video.close()
    bg_clip.close()
    text_clip.close()
    audio_clip.close()
    
    return output_filename

def get_youtube_tokens(filename=TOKEN_FILE):
    """Load YouTube tokens from local file or fallback to GH Actions secret"""
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    elif REFRESH_TOKEN_ENV:  # fallback to the env secret
        return {
            "refresh_token": REFRESH_TOKEN_ENV
        }
    else:
        return None


def save_youtube_tokens(tokens, filename=TOKEN_FILE):
    """Save YouTube tokens locally"""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)


def refresh_youtube_token(refresh_token):
    """Refresh YouTube access token — returns new token dict or None"""
    print(f"Attempting to refresh token for Client ID: {YOUTUBE_CLIENT_ID[:10]}...")
    data = {
        "client_id": YOUTUBE_CLIENT_ID,
        "client_secret": YOUTUBE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    try:
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data=data,
            timeout=10,
        )
    except Exception as e:
        print("Token refresh request failed (network):", e)
        return None

    if response.status_code != 200:
        print("Token refresh failed:", response.status_code)
        try:
            print("Response body:", response.text)
        except Exception:
            pass
        return None

    try:
        token_data = response.json()
    except Exception as e:
        print("Token refresh returned non-json body:", e)
        return None

    if "access_token" not in token_data:
        print("Token response missing access_token:", token_data)
        return None

    new_tokens = {
        "access_token": token_data["access_token"],
        "refresh_token": refresh_token,  # Google usually does NOT return a new one
        "expires_at": (
            datetime.utcnow()
            + timedelta(seconds=token_data.get("expires_in", 3600))
        ).isoformat(),
        "token_type": token_data.get("token_type", "Bearer"),
    }

    # Save ephemeral token.json in workspace (optional; OK to keep)
    save_youtube_tokens(new_tokens)
    return new_tokens



def get_valid_youtube_token():
    """Return a valid access token string — refreshes using available refresh token if needed."""
    tokens = get_youtube_tokens()

    # If no tokens file but we have REFRESH_TOKEN_ENV, try to refresh using env
    if not tokens:
        if REFRESH_TOKEN_ENV:
            new = refresh_youtube_token(REFRESH_TOKEN_ENV)
            return new["access_token"] if new else None
        return None

    # If tokens exists but lacks access_token/expires_at -> try refresh
    if "access_token" not in tokens or "expires_at" not in tokens:
        refresh_token = tokens.get("refresh_token") or REFRESH_TOKEN_ENV
        if not refresh_token:
            return None
        new = refresh_youtube_token(refresh_token)
        return new["access_token"] if new else None

    # tokens contains expires_at — check expiry
    try:
        expires_at = datetime.fromisoformat(tokens["expires_at"])
    except Exception:
        refresh_token = tokens.get("refresh_token") or REFRESH_TOKEN_ENV
        if not refresh_token:
            return None
        new = refresh_youtube_token(refresh_token)
        return new["access_token"] if new else None

    # If about to expire, refresh
    if expires_at <= datetime.utcnow() + timedelta(minutes=5):
        refresh_token = tokens.get("refresh_token") or REFRESH_TOKEN_ENV
        if not refresh_token:
            return None
        new = refresh_youtube_token(refresh_token)
        return new["access_token"] if new else None

    # Otherwise the token is valid
    return tokens["access_token"]



def upload_to_youtube(video_path, quote_text, author, category):
    """
    Upload a local video file (path) to YouTube.
    Returns the uploaded video id or raises on error.
    """
    access_token = get_valid_youtube_token()
    if not access_token:
        raise RuntimeError("No valid access token available")

    tokens = get_youtube_tokens()
# prefer token file value, fallback to env secret
    refresh_token = (tokens.get("refresh_token") if tokens else None) or REFRESH_TOKEN_ENV

    if not refresh_token:
        raise RuntimeError("No refresh token available; reauthorize or set YT_REFRESH_TOKEN secret.")

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        client_id=YOUTUBE_CLIENT_ID,
        client_secret=YOUTUBE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )


    youtube = build("youtube", "v3", credentials=creds)

    title = f"{author} - {quote_text}"
    if len(title) > 100:
        title = title[:97] + "..."

    description = f"{author} - {quote_text}"

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": [
                "quotes", "inspirational", "motivational", "shorts", "daily",
                "love", "hope", "life", "wisdom", "philosophy"
            ],
            "categoryId": "22",
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", chunksize=256 * 1024, resumable=True)

    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    # Resumable upload loop — will raise on errors
    response = None
    while response is None:
        status, response = request.next_chunk()
        # optional: show progress: if status: print(int(status.progress() * 100))
    print(f"Uploaded to YouTube: {response['id']}")
    return response["id"]

image_path = save_author_image(author)
video = create_quote_video(image_path, quotes, author)
#video_id = upload_to_youtube(video, quotes, authors, category)
os.remove(image_path)
#os.remove(video)