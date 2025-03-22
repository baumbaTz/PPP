import os
import subprocess
import requests
import logging
import time
import re

# Configuration
API_URL = "http://ppp.wirr.de:5000/episode"
UPLOAD_URL = "http://ppp.wirr.de:5000/results"
LOG_FILE = "output/podcast_transcriber.log"
MODEL_DIR = "/app/models"
MODEL_NAME = "ggml-large-v3-turbo.bin"
MODEL_PATH = os.path.join(MODEL_DIR, MODEL_NAME)
MODEL_URL = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{MODEL_NAME}"
WHISPER_CPP_PATH = "/app/whisper.cpp/main"

# Setup logging
log_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(log_formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])

# Retrieve or set default nickname
nickname = os.getenv("NICKNAME", "anonymous")
logging.info(f"Nickname: {nickname}")

logging.info("Initializing setup for whisper.cpp...")

# Ensure whisper.cpp has correct permissions
if not os.path.exists(WHISPER_CPP_PATH):
    logging.error(f"Whisper.cpp executable not found at {WHISPER_CPP_PATH}")
    exit(1)
os.chmod(WHISPER_CPP_PATH, 0o755)
logging.info(f"Ensured whisper.cpp executable has correct permissions.")

# Function to download the model if it doesn't exist
def download_model():
    if not os.path.exists(MODEL_PATH):
        logging.info(f"Model file not found at {MODEL_PATH}. Downloading...")
        os.makedirs(MODEL_DIR, exist_ok=True)
        try:
            response = requests.get(MODEL_URL, stream=True)
            response.raise_for_status()
            with open(MODEL_PATH, 'wb') as model_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        model_file.write(chunk)
            logging.info("Model download completed successfully.")
        except requests.exceptions.HTTPError as http_err:
            logging.error(f"HTTP error occurred while downloading model: {http_err}")
            raise
        except Exception as e:
            logging.error(f"Error downloading model: {e}")
            raise
    else:
        logging.info(f"Model file already exists at {MODEL_PATH}. Skipping download.")

# Call the download_model function before processing
download_model()

def request_episode():
    max_retries = 10
    retry_count = 0
    
    while retry_count < max_retries:
        logging.info("Requesting a new episode from the API...")
        response = requests.get(API_URL)
        if response.status_code == 404:
            logging.info("No unprocessed episodes available. Retrying in 10 minutes...")
            time.sleep(600)  # Wait for 10 minutes before retrying
            return None, None, None, None
        elif response.status_code == 200:
            episode = response.json()
            
            # Log the entire received episode data as a block
            logging.info(f"Received episode data:\n"
                         f"-------------------------\n"
                         f"GUID: {episode['guid']}\n"
                         f"Podcast Name: {episode['podcast_name']}\n"
                         f"Episode Title: {episode['episode_title']}\n"
                         f"File URL: {episode['file_url']}\n"
                         f"Token: {episode['token']}\n"
                         f"Token Created At: {episode['token_created_at']}\n"
                         f"-------------------------")
            
            return episode['file_url'], episode['guid'], episode['token'], episode['podcast_name']
        else:
            logging.warning(f"Attempt {retry_count + 1}/{max_retries}: Error fetching episode. Status code: {response.status_code}")
        
        if retry_count < max_retries - 1:
            logging.info(f"Waiting 60 seconds before retry {retry_count + 2}...")
            time.sleep(60)
        retry_count += 1
    
    logging.error("Failed to fetch episode after maximum retries.")
    return None, None, None, None

def sanitize_filename(filename):
    # Replace any character that is not a letter, digit, or underscore with an underscore
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

def download_episode(episode_url, output_path):
    max_retries = 10
    retry_count = 0
    
    while retry_count < max_retries:
        logging.info(f"Attempting to download episode from {episode_url}...")
        try:
            r = requests.get(episode_url, stream=True)
            if r.status_code == 200 and 'audio' in r.headers.get('Content-Type', ''):
                with open(output_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                logging.info(f"Episode downloaded to {output_path}")
                return True
            else:
                logging.warning(f"Attempt {retry_count + 1}/{max_retries}: Download failed. Status code: {r.status_code}, Content-Type: {r.headers.get('Content-Type')}")
        except Exception as e:
            logging.error(f"Attempt {retry_count + 1}/{max_retries}: Error during download: {e}")
        
        if retry_count < max_retries - 1:
            logging.info(f"Waiting 60 seconds before retry {retry_count + 2}...")
            time.sleep(60)
        retry_count += 1
    
    logging.error("Failed to download episode after maximum retries.")
    return False

def execute(cmd):
    popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, universal_newlines=True)
    for stdout_line in iter(popen.stdout.readline, ""):
        logging.info(stdout_line.strip())
    popen.stdout.close()
    return_code = popen.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, cmd)

def process_audio_with_whisper_cpp(audio_file):
    output_txt = f"{audio_file}.txt"
    output_json = f"{audio_file}.json"
    output_srt = f"{audio_file}.srt"
    output_wav = f"{audio_file}.wav"

    try:
        logging.info(f"Processing audio file {audio_file} with ffmpeg to .wav")
        execute(["ffmpeg", "-i", audio_file, "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", output_wav])

        logging.info(f"Processing audio file {output_wav} with whisper.cpp...")
        execute([WHISPER_CPP_PATH, "-f", output_wav, "-otxt", "-osrt", "-oj", "-of", audio_file, "-m", MODEL_PATH])

        logging.info("whisper.cpp completed successfully.")
        return output_txt, output_json, output_srt, output_wav
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running whisper.cpp or ffmpeg: {e}")
        return None, None, None, None

def send_results(txt_path, json_path, srt_path, guid, episode_token, processed_count, failed_count, nickname, podcast_name):
    logging.info(f"Sending results for episode with GUID {guid} to the API...")
    result_data = {
        'guid': guid,
        'token': episode_token,
        'results': {
            'transcript': open(txt_path).read(),
            'json_data': open(json_path).read(),
            'srt_data': open(srt_path).read()
        },
        'nickname': nickname,
        'podcast_name': podcast_name
    }
    logging.info(f"Sending nickname: {nickname}, podcast_name: {podcast_name}")

    max_retries = 10
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            response = requests.post(UPLOAD_URL, json=result_data)
            if response.status_code == 200:
                processed_count += 1
                logging.info(f"Results for episode with GUID {guid} successfully uploaded. Total successful uploads: {processed_count}")
                return processed_count, failed_count
            else:
                logging.warning(f"Attempt {retry_count + 1}/{max_retries}: Failed to upload results. Status code: {response.status_code}")
        except requests.exceptions.ConnectionError as e:
            logging.warning(f"Attempt {retry_count + 1}/{max_retries}: Connection error occurred: {str(e)}")
        except Exception as e:
            logging.warning(f"Attempt {retry_count + 1}/{max_retries}: Unexpected error occurred: {str(e)}")
        
        if retry_count < max_retries - 1:  # Don't sleep after the last attempt
            logging.info(f"Waiting 60 seconds before retry {retry_count + 2}...")
            time.sleep(60)
        retry_count += 1
    
    # If we get here, all retries failed
    failed_count += 1
    logging.error(f"Failed to upload results for episode with GUID {guid} after {max_retries} attempts. Total failed uploads: {failed_count}")
    return processed_count, failed_count

def cleanup_files(files):
    logging.info("Cleaning up temporary files...")
    for file in files:
        logging.info(f"Checking if {file} exists...")
        if os.path.exists(file):
            os.remove(file)
            logging.info(f"Deleted file: {file}")

def process_episode():
    processed_count = 0
    failed_count = 0

    while True:
        episode_url, guid, episode_token, podcast_name = request_episode()
        if not episode_url:
            continue
        # Generate a sanitized filename for the episode
        sanitized_guid = sanitize_filename(guid)
        episode_file = f"output/episode_{sanitized_guid}.mp3"

        if not download_episode(episode_url, episode_file):
            logging.info(f"Skipping episode {guid} due to download failure.")
            continue

        txt_path, json_path, srt_path, wav_path = process_audio_with_whisper_cpp(episode_file)
        if txt_path is None:
            logging.info(f"Skipping episode {guid} due to processing error.")
            continue

        # Send the results to the API and log upload success or failure
        processed_count, failed_count = send_results(txt_path, json_path, srt_path, guid, episode_token, processed_count, failed_count, nickname, podcast_name)

        cleanup_files([episode_file, txt_path, json_path, srt_path, wav_path])

if __name__ == "__main__":
    process_episode()
