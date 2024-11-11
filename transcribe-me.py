import os
import subprocess
import requests
import logging
import time

# Configuration
API_URL = "http://ppp.wirr.de:5000/episode"  # API endpoint to request an episode
UPLOAD_URL = "http://ppp.wirr.de:5000/results"  # API endpoint to upload results
LOG_FILE = "/app/podcast_transcriber.log"  # Logfile placed in the 'app' folder of the container
MODEL_DIR = "/whisper.cpp/models"  # Directory to store Whisper models
MODEL_NAME = "ggml-large-v2.bin"  # Model filename
MODEL_PATH = os.path.join(MODEL_DIR, MODEL_NAME)  # Full path to the model
MODEL_URL = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{MODEL_NAME}"  # URL to download the model

# Setup logging with different formats for file and console
log_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')

# File handler (logs to file in the app folder)
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(log_formatter)

# Console handler (logs to console with the same format)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])

# Retrieve or set default nickname
nickname = os.getenv("NICKNAME", "anonymous")
logging.info(f"Nickname: {nickname}")

logging.info("Initializing setup for whisper.cpp...")

# Function to download the model if it doesn't exist
def download_model():
    if not os.path.exists(MODEL_PATH):
        logging.info(f"Model file not found at {MODEL_PATH}. Downloading...")
        os.makedirs(MODEL_DIR, exist_ok=True)
        try:
            response = requests.get(MODEL_URL, stream=True)
            response.raise_for_status()  # Check for HTTP errors
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
    logging.info("Requesting a new episode from the API...")
    response = requests.get(API_URL)
    if response.status_code == 404:
        logging.info("No unprocessed episodes available. Retrying in 10 minutes...")
        time.sleep(600)  # Wait for 10 minutes before retrying
        return None, None, None, None
    elif response.status_code != 200:
        logging.error(f"Error fetching episode. Status code: {response.status_code}")
        return None, None, None, None
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

def download_episode(episode_url, output_path):
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
            logging.warning(f"Download failed. Status code: {r.status_code}, Content-Type: {r.headers.get('Content-Type')}")
            return False
    except Exception as e:
        logging.error(f"Error during download: {e}")
        return False

def process_audio_with_whisper_cpp(audio_file):
    logging.info(f"Processing audio file {audio_file} with whisper.cpp...")
    output_txt = f"{audio_file}.txt"
    output_json = f"{audio_file}.json"
    output_srt = f"{audio_file}.srt"

    try:
        # Call whisper.cpp using subprocess
        result = subprocess.run(
            ["/whisper.cpp/main", "-f", audio_file, "-o", ".", "-m", MODEL_PATH],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        if result.returncode != 0:
            logging.error(f"whisper.cpp failed: {result.stderr.decode()}")
            return None, None, None
        else:
            logging.info(f"whisper.cpp completed successfully: {result.stdout.decode()}")
            return output_txt, output_json, output_srt
    except Exception as e:
        logging.error(f"Error running whisper.cpp: {e}")
        return None, None, None

def cleanup_files(files):
    logging.info("Cleaning up temporary files...")
    for file in files:
        if os.path.exists(file):
            os.remove(file)
            logging.info(f"Deleted file: {file}")

def process_episode():
    processed_count = 0
    failed_count = 0

    while True:
        total_start_time = time.time()

        episode_url, guid, episode_token, podcast_name = request_episode()
        if not episode_url:
            continue

        episode_file = f"episode_{guid}.mp3"

        if not download_episode(episode_url, episode_file):
            logging.info(f"Skipping episode {guid} due to download failure.")
            continue

        txt_path, json_path, srt_path = process_audio_with_whisper_cpp(episode_file)
        if txt_path is None:
            logging.info(f"Skipping episode {guid} due to processing error.")
            continue

        # Continue with your existing logic to send results, etc.
        logging.info(f"Finished processing episode with GUID {guid}. Moving on to the next...\n")
        
        cleanup_files([episode_file, txt_path, json_path, srt_path])

        total_end_time = time.time()
        total_processing_time = total_end_time - total_start_time
        logging.info(f"Total processing time for episode {guid}: {total_processing_time:.2f} seconds")

        logging.info(f"Total successful uploads: {processed_count}, Total failed uploads: {failed_count}")

if __name__ == "__main__":
    process_episode()
