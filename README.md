# Alvi Studio

Alvi Studio is a local-first Windows desktop tool for dubbing Chinese, English, and other supported speech into Hindi. It keeps fixed clean voices per speaker, preserves timing, can retain music/SFX/reactions, and does not clone anyone's voice.

## Install

Run `artifacts\Alvi-Studio-Setup.exe`. On the **Choose Install Location** page, select a folder on the drive you want, for example:

```text
D:\Alvi Studio
```

The chosen folder is the storage boundary for all large and app-managed data:

```text
D:\Alvi Studio\
  runtime\       private Python and AI libraries
  tools\         bundled FFmpeg
  models\        downloaded model weights
  cache\         Hugging Face, Torch and pip caches
  projects\      resumable timelines and generated takes
  exports\       finished videos
  temp\           temporary audio and downloads
  logs\           logs
  updates\        downloaded updates
```

Windows itself still stores a few tiny integration records outside that folder: Start-menu/Desktop shortcuts, uninstall registry metadata, and normal operating-system bookkeeping. Alvi Studio does not put models, AI environments, project media, or caches there.

## First run

1. Open **Storage & Models**.
2. Select Fast, Balanced, or Studio quality.
3. Choose **Install selected model pack**. The app shows required and free space first.
4. Some Hugging Face models require accepting their terms and entering an access token. The token is used for that download and is not saved.
5. Return to **New dub**, choose a video, languages, soundtrack options and volume levels, then start the dub.

Approximate model-pack space is 14 GB for Fast, 19 GB for Balanced, and 22 GB for Studio, plus working room. Studio quality is intended for a modern NVIDIA GPU; CPU operation is possible for supported components but can be very slow.

## Processing pipeline

- Bandit v2 separates speech, music and effects.
- faster-whisper creates word-level transcription timing.
- pyannote assigns stable speaker identities in Balanced/Studio.
- a multi-clip vocal-range analysis selects a fixed male/female Hindi voice family; uncertain speakers use a neutral alternating assignment.
- SenseVoice estimates line emotion in Studio.
- MADLAD-400 translates to Hindi.
- Indic Parler-TTS creates clean named voices rather than cloning the source speaker.
- Studio makes three takes per line and scores timing/emotion before exact duration fitting.
- FFmpeg rebuilds the soundtrack and retains the original video stream.

No AI pipeline can honestly guarantee perfect transcription, translation, emotion, or gender-family estimation for every noisy scene. Alvi Studio preserves its timeline, translations, chosen takes and scores inside each project so failures are inspectable and future versions can add manual correction.

## Selected-drive guarantee

At startup, `StorageLayout` locks the following environment locations to the install root: Hugging Face, Transformers, Torch, Bandit weights, XDG cache, and all three temporary-directory variables. Path traversal outside the root is rejected. Use **Storage & Models → Run storage audit** to verify the active installation.

## GitHub updates

Enter `owner/repository` under **Storage & Models → GitHub automatic updates**. Release installers must include `Alvi-Studio-Setup.exe` and `Alvi-Studio-Setup.exe.sha256`. Automatic installation additionally requires the configured Windows code-signing publisher to match; unsigned updates are downloaded but not executed automatically.

The included workflow builds GitHub releases on Windows. Repository secrets may provide a signing certificate and password.

## Development

Run the source UI:

```powershell
.\run-dev.ps1
```

Run tests:

```powershell
python -m unittest discover -s tests -v
```

Build the installer (requires network access for official Python and FFmpeg archives and NSIS on `PATH`):

```powershell
.\packaging\build.ps1 -Python python -Version 0.1.1 -Repository "owner/repository" -ExpectedPublisher "Your signing publisher"
```

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) before redistributing model-powered builds or outputs.
