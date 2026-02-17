---
name: p2m-studio
description: "Photo-to-Movie generator. When user sends multiple photos (5+) and asks to make a video, movie, memorial, or 纪念影片/做视频/生成视频, trigger this skill. Also trigger when user sends 10+ photos in a batch. Generates a narrated movie with Ken Burns effect, subtitles, and classical music from photos."
metadata: {"moltbot":{"emoji":"🎬","requires":{"bins":["ffmpeg","python3"],"env":["GEMINI_API_KEY"]},"install":[{"id":"brew-ffmpeg","kind":"brew","formula":"ffmpeg","bins":["ffmpeg"],"label":"Install ffmpeg (brew)"}]}}
---

# P2M Studio (Photo-to-Movie)

Generate memorial movies from photos with AI narration, subtitles, and classical music.

## Step 1: Save Photos

Save all user-provided photos to a temporary directory. Create the directory first:

```bash
mkdir -p /tmp/p2m_photos_$RANDOM
```

Save each photo the user sent into that directory as JPG/PNG files. Remember the directory path.

## Step 2: Run Pipeline

Run the generation script. Use `--moltbot` for machine-readable output:

```bash
bash ~/moltbot/skills/p2m-studio/scripts/p2m.sh generate --input "{photosDir}" --output "/tmp/p2m_output_$$" --moltbot
```

The pipeline takes 1-3 minutes. It will:
1. Import and deduplicate photos
2. Analyze each photo with Gemini Vision (captioning + scene detection)
3. Build a storyboard with Ken Burns animations
4. Generate Chinese narration with AI + text-to-speech
5. Add classical piano background music with ducking
6. Render 720p preview + 1080p final video

## Step 3: Send Results

Parse stdout for protocol lines:
- `MEDIA:/path/to/file.mp4` → Send this video file to the user
- `DONE:/path/to/final.mp4` → Pipeline complete, this is the final video
- `PROGRESS:N:message` → Optional: report progress to user
- `ERROR:message` → Report error to user

**Send the final MP4 video file to the user.** Also mention that an SRT subtitle file is available in the same output directory if they want external subtitles.

## Options

Custom duration (seconds):
```bash
bash ~/moltbot/skills/p2m-studio/scripts/p2m.sh generate --input "{photosDir}" --output "/tmp/p2m_output_$$" --duration 300 --moltbot
```

Custom template:
```bash
bash ~/moltbot/skills/p2m-studio/scripts/p2m.sh generate --input "{photosDir}" --output "/tmp/p2m_output_$$" --template marriage_5min_restrained --moltbot
```

## Notes

- Default: ~1 min video, Chinese narration, classical piano, 1080p H.264 MP4
- Template: "marriage_5min_restrained" (6 acts: 相遇/成长/婚礼/家庭/现在/未来)
- Requires: GEMINI_API_KEY (for photo captioning + narration), ffmpeg, python3
- Processing time: ~1-3 min for 6-20 photos
- Minimum photos: 5 (fewer will still work but quality is reduced)
- SRT subtitles always generated alongside video
