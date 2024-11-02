import os
import torch
import requests
import json
from faster_whisper import WhisperModel
import logging
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# Configuration
API_URL = "http://ppp.wirr.de:5000/episode"  # API endpoint to request an episode
UPLOAD_URL = "http://ppp.wirr.de:5000/results"  # API endpoint to upload results
LOG_FILE = "/app/podcast_transcriber.log"  # Logfile placed in the 'app' folder of the container

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

# Check if CUDA-enabled GPU is available
if torch.cuda.is_available():
    try:
        # Test if FP16 is supported on the GPU
        torch.zeros(1, dtype=torch.float16, device="cuda")
        device = "cuda"
        precision = "float16"
        logging.info("GPU supports FP16, using FP16 precision.")
    except Exception as e:
        logging.warning(f"FP16 not supported on GPU, falling back to CPU (INT8): {e}")
        device = "cpu"
        precision = "int8"
else:
    logging.info("No GPU detected, falling back to CPU (INT8).")
    device = "cpu"
    precision = "int8"

logging.info(f"Device set to: {device} with precision: {precision}")
logging.info("Initializing Whisper model with large-v2...")

# Initialize the Whisper model
model = WhisperModel("large-v2", device=device, compute_type=precision)

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

    # First, try to download using requests
    try:
        r = requests.get(episode_url, stream=True)
        if r.status_code == 200 and 'audio' in r.headers.get('Content-Type', ''):
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            logging.info(f"Episode downloaded to {output_path}")
            return True
        else:
            logging.warning(f"Failed to download via requests. Status code: {r.status_code}, Content-Type: {r.headers.get('Content-Type')}")
            return False
    except Exception as e:
        logging.error(f"Error during requests download: {e}")
        return False

def download_with_selenium(episode_url, output_path):
    logging.info(f"Falling back to headless browser to download episode from {episode_url}...")

    # Set up Selenium with headless Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(options=chrome_options)

    try:
        driver.get(episode_url)
        time.sleep(5)  # Allow time for JavaScript to load and execute
        
        # Locate the audio element and extract the MP3 file URL
        audio_tag = driver.find_element_by_tag_name("audio")
        mp3_url = audio_tag.get_attribute("src")
        
        if mp3_url:
            logging.info(f"MP3 file found at {mp3_url}, downloading...")
            r = requests.get(mp3_url, stream=True)
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            logging.info(f"Episode downloaded to {output_path}")
            return True
        else:
            logging.error("No MP3 file found in the audio tag.")
            return False
    except Exception as e:
        logging.error(f"Error during Selenium download: {e}")
        return False
    finally:
        driver.quit()

def process_audio(audio_file):
    logging.info(f"Processing audio file {audio_file} with Whisper model...")
    try:
        # Force language to English ('en')
        segments, info = model.transcribe(audio_file, language="en")
        logging.info(f"Detected language: {info.language} with probability {info.language_probability}")
        logging.info(f"Processing complete for {audio_file}.")
        return segments
    except Exception as e:
        # Log the error and clean up the invalid file
        logging.error(f"Error processing file {audio_file}: {e}")
        if os.path.exists(audio_file):
            os.remove(audio_file)
            logging.info(f"Deleted invalid file {audio_file}")
        # Return None to signal that processing failed
        return None

def generate_output(segments, guid):
    logging.info(f"Generating TXT, JSON, and SRT outputs for episode with GUID {guid}...")
    output_data = {'guid': guid, 'transcripts': []}
    txt_output = []
    srt_output = []
    srt_counter = 1

    for segment in segments:
        txt_output.append(segment.text)
        output_data['transcripts'].append({
            'start': segment.start,
            'end': segment.end,
            'text': segment.text
        })
        
        # SRT format
        srt_output.append(f"{srt_counter}\n{format_srt_time(segment.start)} --> {format_srt_time(segment.end)}\n{segment.text}\n")
        srt_counter += 1
    
    # Write outputs to disk
    txt_path = f"output_{guid}.txt"
    json_path = f"output_{guid}.json"
    srt_path = f"output_{guid}.srt"
    
    with open(txt_path, "w") as txt_file:
        txt_file.write("\n".join(txt_output))
    
    with open(json_path, "w") as json_file:
        json.dump(output_data, json_file, indent=2)
    
    with open(srt_path, "w") as srt_file:
        srt_file.write("\n".join(srt_output))
    
    logging.info(f"Output files generated: {txt_path}, {json_path}, {srt_path}")
    
    return txt_path, json_path, srt_path

def format_srt_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = seconds % 60
    milliseconds = int((seconds % 1) * 1000)
    return f"{hours:02}:{minutes:02}:{int(seconds):02},{milliseconds:03}"

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

    max_retries = 5
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
        if os.path.exists(file):
            os.remove(file)
            logging.info(f"Deleted file: {file}")
            
def process_episode():
    processed_count = 0  # Track successful uploads
    failed_count = 0  # Track failed uploads
    
    while True:
        # Start timing the processing
        total_start_time = time.time()

        episode_url, guid, episode_token, podcast_name = request_episode()  # Ensure podcast_name is retrieved
        if not episode_url:
            continue
        
        episode_file = f"episode_{guid}.mp3"
        
        # Try downloading the episode via requests first
        if not download_episode(episode_url, episode_file):
            # If requests fails, try using Selenium to download the file
            if not download_with_selenium(episode_url, episode_file):
                logging.info(f"Skipping episode {guid} due to download failure.")
                continue  # Skip to the next episode

        # Process the MP3 audio file directly
        segments = process_audio(episode_file)
        if segments is None:
            logging.info(f"Skipping episode {guid} due to processing error.")
            continue  # Move on to the next episode
        
        # Generate output files
        txt_path, json_path, srt_path = generate_output(segments, guid)

        # Send the results to the API and log upload success or failure
        processed_count, failed_count = send_results(txt_path, json_path, srt_path, guid, episode_token, processed_count, failed_count, nickname, podcast_name)

        # Cleanup after processing the entire episode
        cleanup_files([episode_file, txt_path, json_path, srt_path])
        
        # Calculate and log total processing time
        total_end_time = time.time()
        total_processing_time = total_end_time - total_start_time
        logging.info(f"Processing time for episode {guid}: {total_processing_time:.2f} seconds")

        # Output total successful and failed uploads
        logging.info(f"Finished processing episode with GUID {guid}, moving to next...\n")
        logging.info(f"Total successful uploads: {processed_count}, Total failed uploads: {failed_count}")

if __name__ == "__main__":
    process_episode()
