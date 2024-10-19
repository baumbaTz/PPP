# PPP Podcast Processing Project
- Automatic Transcription of Podcast Episodes with Faster-Whisper (https://github.com/SYSTRAN/faster-whisper)
- Backend API to deliver Episodes to transcribe and ingest the results.

# Wanna help?
If you have Docker or Docker Desktop:
- Pull the Image from 
```
baumbatz/ppp-transcriber-gpu
```
```
https://hub.docker.com/repository/docker/baumbatz/ppp-transcriber-gpu
```
- First Start (replace with your nickname [for stats] and your path [for temp files]
```
docker run --gpus all -e NICKNAME="yournicknamehere" --name ppp-gpu -v PATH-TO-TEMP-FOLDER-ON-YOUR-MACHINE:/app/output baumbatz/ppp-transcriber-gpu:latest
```
- Next start... just start the container

Gotta stop the container? 
- No Problem. If your container doesn't deliver the results within 6 hours of the request it will be reassigned to the next person. :)
