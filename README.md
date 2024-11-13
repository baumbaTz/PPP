# PPP Podcast Processing Project
- Automatic Transcription of Frogpants Podcast Episodes (using Faster-Whisper or Whisper.cpp)
- Backend API delivers Episodes to transcribe and ingests the results.
# Wanna help?
You need Docker or Docker Desktop:
- Pull the Image  
```
docker pull baumbatz/ppp-transcriber-cuda
```
```
https://hub.docker.com/repository/docker/baumbatz/ppp-transcriber-cuda
```
- First Start (replace with your nickname [for stats] and your path [for temp files]
```
docker run --gpus all -e NICKNAME="your-nickname" --name ppp-cpp -v path-to-temp-folder:/app/output baumbatz/ppp-transcriber-cuda:latest
```
- If you don't have a NVIDIA GPU remove "--gpus all" (i haven't found a easy way to make it work with AMD or Intel GPUs yet)
- Next start... just start the container

Gotta stop the container? 
- No Problem. If your container doesn't deliver the results within 12 hours of the request it will be reassigned to the next person. :)
# Use the Transcriptions for your own fun ideas
API URL
```
http://ppp.wirr.de:5000/
```
All API endpoints:
```
GET /episodes - List all episodes (with optional status filter: ?status=processed and ?status=unprocessed)
```
```
GET /results/<guid> - Get results for a specific episode
```
```
GET /tallies - List user tallies
```
# Thanks
- trevorlyman for making https://searchtms.com which showed the transcription stuff actually works
- TaliZorEl for suggesting to create this :)
- Crutlefish for helping with making it better and working on the Apple Silicon version of this
# Podcast Feeds currently in the queue
```
- Filmsack
- CORE
- Play Retro
- SKIM
- There Will Be Dungeons
- The Instance
- The Monday Show
- Diary of a Cartoonist
- Word on the Street
- BOOP

Non Frogpants Shows
- GORE
- Wait, You Haven't Seen...?
- Those Were The Days
- All Around Science
- Soundography (as soon as i figure out how to make that work)
```
