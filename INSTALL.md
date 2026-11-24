# Installation and deployment guide

## 1. Hardware and operating system

The target is a PC with two GTX 950s (usually 2 GB each, but check). No SLI bridge is needed. Each card is an independent CUDA device and multi-GPU inference can split the weights across devices. Start with one 1.7B model; try 4B only after the small model runs reliably. Recommended: 8 GB RAM minimum for small models, 16 GB or more for CPU offload and simultaneous video work, and an SSD with at least 20 GB free. The GPUs do not need to render every task: FFmpeg defaults to CPU H.264 encoding for compatibility with Maxwell. An NVIDIA driver that actually supports your model runtime is required for GPU inference.

Use an OS still receiving security updates. Windows PowerShell examples below do not require administrator privileges except system-level installations. Linux commands assume a traditional desktop/server setup. Keep the PC awake when the worker needs to post.

## 2. Obtain the source

From the downloaded source archive, extract into a directory of your choice and open a terminal in `reel-lab`. If you have pushed it to your own GitHub repository instead, clone it:

```sh
git clone https://github.com/YOUR_USERNAME/reel-lab.git
cd reel-lab
```

To publish this repository yourself, create a **private empty repository** called `reel-lab` at https://github.com/new (do not initialize a README when pushing existing history). From the project directory:

```sh
git init -b main
git add .
git commit -m "Initial Reel Lab application"
git remote add origin https://github.com/YOUR_USERNAME/reel-lab.git
git push -u origin main
```

If the directory already has Git history, skip `git init` and the initial commit if appropriate. Sign in through your normal Git credential manager or GitHub authentication workflow. Never commit `.env`, tokens, videos or databases. Check `git status` first. GitHub Actions runs only the mock/unit tests; no live posting credentials should be stored there.

## 3. Install Python and FFmpeg

Windows: install Python 3.12 from https://www.python.org/downloads/ (enable PATH) and FFmpeg from https://ffmpeg.org/download.html. Ensure `ffmpeg.exe` and `ffprobe.exe` are on PATH; reopen the terminal. If using winget, `winget search ffmpeg` can locate a package. Verify:

```powershell
py -3 --version
ffmpeg -version
ffprobe -version
nvidia-smi
```

Create the application environment (no activation required):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
```

Linux (Debian/Ubuntu example):

```sh
sudo apt install python3 python3-venv ffmpeg git
python3 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
```

In the following examples replace `python` with `.\.venv\Scripts\python.exe` (Windows) or `.venv/bin/python` (Linux), or activate the environment using the usual method.

## 4. Install and benchmark the local LLM

Install Ollama from https://ollama.com/download. Its documented NVIDIA backend supports compute capability 5.0 and higher; older Maxwell cards require a compatible driver (current documentation specifies 570+ for compute capability 5.0–6.2). GTX 950 is compute capability 5.2. Verify the exact supported driver for your OS and installed hardware; legacy GPU support can change. If the current Ollama build does not recognize the GPUs, CPU inference is acceptable for this workload.

```sh
ollama pull qwen3:1.7b
ollama run qwen3:1.7b
```

Ask it to caption a sample video description. In another terminal:

```sh
ollama ps
nvidia-smi
```

The model should use GPU memory if supported. Qwen3 1.7B's default quantized weights are about 1.4 GB; context and runtime overhead consume additional VRAM. Reel Lab deliberately uses a 2048-token context and short responses. If it performs well, try `ollama pull qwen3:4b` and change `OLLAMA_MODEL=qwen3:4b` in `.env`. This model's weights are about 2.5 GB, so it may need split GPUs and/or CPU RAM. No guarantee of fitting entirely in the 4 GB combined VRAM. If the system struggles, try `qwen3:0.6b`, or `qwen2.5:1.5b` where available.

Ollama manages its devices itself. Do not use SLI. To test GPU visibility you can set `CUDA_VISIBLE_DEVICES=0` in the environment of the Ollama server, restart the server, then benchmark. Compare with both GPUs visible. For CPU-only operation, use an environment supported by your Ollama release to hide CUDA devices (for example `CUDA_VISIBLE_DEVICES=-1`). Keep Ollama bound to localhost. Refer to https://docs.ollama.com/gpu and https://github.com/ggml-org/llama.cpp/blob/master/docs/multi-gpu.md for alternative runtimes. This project currently implements the Ollama API, not a llama.cpp-native adapter.

If Ollama isn't running in the background, start `ollama serve`. An already-running desktop instance may report the port is occupied; do not start a second server on the same port.

## 5. Try the entire local workflow with no account

Leave `.env` with `DRY_RUN=true`, `ALLOW_LIVE_TRIALS=false`. Check the installation:

```sh
python -m reel_lab doctor
python -m unittest discover -s tests -v
```

Create a sample MP4 if you don't have a clip. This synthetic color card is for dry-run testing only:

```sh
ffmpeg -f lavfi -i color=c=blue:s=640x480:r=30 -t 5 -c:v libx264 -pix_fmt yuv420p sample.mp4
```

Use a past or current timestamp for an immediate dry run (the example below is intentionally in the past):

```sh
python -m reel_lab add sample.mp4 --brief "A blue test card for a dry run" --caption "Test clip" --duration 5 --at 2026-01-01T12:00:00-06:00
python -m reel_lab list
python -m reel_lab show 1
```

Open the rendered file displayed by `show` and review it. The renderer creates a 1080x1920 H.264 MP4, pads landscape video, preserves available original audio, trims and checks duration/size. It does not generate content or automatically crop around subjects. If you leave off `--caption`, Ollama generates a draft based on `--brief` and recent results.

```sh
python -m reel_lab approve 1
python -m reel_lab tick
python -m reel_lab show 1
```

The state should be `simulated` with no network request to Instagram. IDs may differ if you already have a database. For a real clip only, `reset-dry ID` returns it to a draft so it can be reviewed again in live mode. Do not approve synthetic test cards for real publishing.

## 6. Optional graphical interface

```sh
python -m pip install -r requirements-dashboard.txt
python -m streamlit run dashboard.py --server.address 127.0.0.1
```

Open http://127.0.0.1:8501. Enter a local video path and a brief, select a clip duration/start, enter a schedule with a UTC offset and create a draft. Expand a draft, preview the video, optionally correct the caption and schedule, and check the review box. Approve separately. The worker is a second process. The interface has no multi-user authentication; never bind it to a public interface. For off-machine access prefer a trusted private tunnel or remote desktop, with authentication.

## 7. Set up official Instagram API access

This is the only part involving Meta. It is not needed for local editing, model development, the queue or dry runs. Requirements and developer interface labels can change with the API version; follow the linked official instructions. Begin with a **public eligible Creator or Business account** that already shows the Trial option in Instagram's mobile Reel composer. Check its account status and recommendation eligibility. Do not attempt to evade eligibility or rate limits.

1. Sign in at https://developers.facebook.com/ and create an app under your own account with the Instagram use case/product. If using Facebook Login for Business, connect the Instagram professional account to a Facebook Page that you control and configure the app for that login method. Use the app dashboard's Instagram API configuration and add an authorized app-role/test account as appropriate. Development mode typically only serves app roles; broader customer access may need app review, advanced access and business verification. Do not request unrelated scopes.
2. Prefer **Facebook Login for Business** for local resumable uploading. Follow Meta's authentication and permissions documentation to obtain the authorized access token and the professional Instagram account's numeric ID. The relevant permissions normally include `instagram_basic`, `instagram_content_publish`, and `instagram_manage_insights`; Page discovery/read permissions can also be necessary depending on the setup. Use Meta's Graph API Explorer or official token debugging tools to verify token scopes, expiry and account ownership. For Instagram Login, the permissions use `instagram_business_*` names and URL upload is required by this adapter.
3. Copy the token into `.env` on the deployment PC only; never paste it into ChatGPT, a repository, screenshots or a public message. Set `IG_USER_ID` to the numeric Instagram professional account ID (not a username or Facebook Page ID), `IG_LOGIN=facebook`, `IG_UPLOAD=resumable`. Set `IG_API_VERSION` to a supported version whose publishing docs explicitly show Trial Reels. The supplied example uses v27.0 but account availability can change.
4. For read-only identity validation, set `DRY_RUN=false`, `ALLOW_LIVE_TRIALS=true`, then run `python -m reel_lab identity`. This checks the authenticated account's ID and username. It is not a publishing test. **Do not start the worker yet.** Confirm that the returned username belongs to your intended account. Keep tokens private and renew manually using Meta's official token flow before expiry. Do not copy tokens from browser traffic.

The adapter sends `trial_params` with `graduation_strategy=MANUAL` by default or `SS_PERFORMANCE` if explicitly selected. The exact availability of this field alongside resumable upload must be verified against current Meta docs and the app/account. If the API rejects it, don't remove the Trial field or retry as an ordinary Reel. Turn off live mode and use Instagram's native Trial scheduler until compatibility is confirmed. No live request was tested during development.

### Alternative: HTTPS URL upload

Set `IG_LOGIN=instagram` (or `facebook`) and `IG_UPLOAD=url`. You must make the **exact rendered MP4** accessible to Meta over HTTPS using authorized storage you already control (e.g. a short-lived signed URL that remains valid during processing). Do not expose the local computer directly to the public Internet. The model never generates or controls a video URL.

You can use `MEDIA_BASE_URL=https://your-authorized-storage.example/reels` and manually upload the named rendered file there before approving the job. Alternatively, provide `--video-url` with the exact hosted media URL when creating a draft, if you can ensure it matches the rendered clip. URL mode cannot prove remote bytes match the local file; you must verify correspondence yourself. For the usual local workflow the Facebook resumable method avoids the need for hosted media.

## 8. First real Trial Reel

Keep the worker stopped. Use a video that you own and intend to publish publicly to non-followers. Choose manual sharing unless you deliberately want Instagram's optional promotion. Verify the `Trial` behavior in your official publishing docs and ensure account acceptance.

```sh
python -m reel_lab add myclip.mp4 --brief "Explain what the video contains and the audience in plain language" --duration 20 --at 2027-01-01T18:00:00-06:00
python -m reel_lab list
python -m reel_lab show 2
```

Replace the future example time with the desired time and use the actual new ID. Review the rendered video, caption, hypothesis, and `trial` mode. If necessary:

```sh
python -m reel_lab edit 2 --caption "An accurate caption that I reviewed" --at 2027-01-01T18:00:00-06:00
python -m reel_lab approve 2
python -m reel_lab tick
```

`tick` publishes only if an approved job is due. To use automatic Instagram promotion, pass `--auto-share` when creating the draft. No separate command promotes a live trial; the platform does that according to its own criteria. For the first post, verify in the Instagram app that it actually appeared under Trial Reels and not as a normal Reel. Stop further publication if anything is unexpected.

The worker counts publish attempts against a rolling 24-hour cap and respects the configured minimum interval. Defaults: two attempts per day and six hours between attempts. This is not a guarantee of platform allowance; trial-specific limits can be stricter. Keep a conservative posting cadence and comply with recommendation and content policies. `cancel ID` cancels a draft or approved item, not an already published Reel. Manage live posts in Instagram itself.

## 9. Batch preparation and daily operation

Place genuine original MP4s in an inbox with matching UTF-8 `.txt` files:

```
inbox/clip-a.mp4
inbox/clip-a.txt
inbox/clip-b.mp4
inbox/clip-b.txt
```

The briefs describe the content, desired hook, intended audience and any claims that are safe to make. Run:

```sh
python -m reel_lab ingest inbox --at 2027-01-01T18:00:00-06:00 --spacing-hours 24
```

This renders up to 30 seconds from each clip, asks the model for captions, schedules drafts at spaced times, and queues them for review. Matching rendered bytes are rejected; the pipeline cannot detect all near-duplicates. Do not use it to flood the platform with duplicate or low-quality variations. Approve each draft after review. For automatic subtitles, you can transcribe source clips with a separately installed local Whisper tool and include the transcript in the brief, or embed reviewed subtitles in the source video beforehand. Transcription is not built into this release.

Start the worker:

```sh
python -m reel_lab worker --seconds 60
```

This is intentionally unattended *after* approval, not an autonomous publishing agent. Ctrl+C stops the worker. Restart it normally after edits to `.env`; it loads settings at startup. Past-due approved tasks can run upon restart, still subject to spacing and the cap; cancel stale jobs before restarting. The approvals are tied to the dry/live mode in which they were made. Check the queue regularly.

### Windows startup

Use Task Scheduler, Create Task, and set a trigger At startup or At log on. Use the same user who owns the data directory. Action: Start a program. Program: full path to `.venv\Scripts\python.exe`. Arguments: `-m reel_lab worker --seconds 60`. Start in: full path of the project folder, without enclosing quotes in the UI field. Ensure the process has an available account profile and network, set restart-on-failure behavior, and do not launch multiple workers. Don't set the task to terminate after the default multiday timeout. The GUI and Ollama are not needed for publishing already approved jobs; Ollama needs to be running to draft captions.

### Linux startup

Create a systemd user service at `~/.config/systemd/user/reel-lab.service`, replacing the paths below:

```ini
[Unit]
Description=Reel Lab worker
After=network-online.target

[Service]
WorkingDirectory=/home/USER/reel-lab
ExecStart=/home/USER/reel-lab/.venv/bin/python -m reel_lab worker --seconds 60
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
```

Then run:

```sh
systemctl --user daemon-reload
systemctl --user enable --now reel-lab.service
journalctl --user -u reel-lab.service -f
```

If the user manager stops at logout, configure an appropriate persistent user service through your system administrator. Avoid running this application as root.

## 10. Analytics and experiment design

The worker queries available media insights per metric at approximately 24 and 72 hours, within a 12-hour window. Missing metrics are not fabricated as zero. If a trial isn't exposed through the insights API or permissions are missing, it may not return metrics at all; the app will retry within that time window. Keep it running regularly. Reported insights can also include other surfaces after promotion, so compare similar trial modes and ages; individual samples don't establish causality.

```sh
python -m reel_lab report
python -m reel_lab report --ai
```

For each real experiment change a meaningful creative variable (e.g. first sentence, pacing, subject), use distinct material, and compare shares/views, likes/views and watch time where available. The local model sees recent summaries for future drafts, not the video itself. Review its recommendations and correct unsupported claims. It cannot post independently.

## 11. Failures and maintenance

| Symptom | Action |
|---|---|
| Ollama out of memory | Reduce model to 1.7B/0.6B; test CPU mode; close competing apps. |
| FFmpeg not found | Install it and reopen terminal; check both ffmpeg and ffprobe. |
| `simulated` | Dry run succeeded; no post was sent. |
| Approval doesn't run | Check timestamp, mode, spacing/cap and job state. |
| Live identity fails | Verify username/ID, token expiry, app role, login and permissions. |
| Trial publishing rejected | Verify availability and exact trial parameters in current Meta docs. Never remove trial mode as fallback. |
| `uncertain` or interrupted `publishing` | Further live publishing is blocked. Stop worker, check Instagram and Meta's tools. No automatic retry. Reconcile only after confirming result. |
| No metrics | Confirm permissions and account API access; check in the Instagram app. |

If you verified that a stuck Reel was published, record its confirmed numeric media ID with `python -m reel_lab reconcile ID --media-id MEDIA_ID`. If you verified it did not publish and want to abandon the job, run `python -m reel_lab reconcile ID` without a media ID. Only do this after stopping the worker; the app deliberately never retries a final publish automatically. Duplicate protection also applies to abandoned jobs; do not bypass it by manipulating the database. Keep the worker stopped whenever you are investigating ambiguous outcomes.

Back up `data/` (SQLite and rendered files) with the worker and dashboard stopped, along with a separate secure backup of `.env`. If moving to a different path, database entries contain absolute paths; restore to the same path or deliberately migrate them. Never put token-containing `.env` in Git or share it publicly. Use a dedicated OS account and restrict file access.

## References

* Meta Instagram Platform/content publishing: https://developers.facebook.com/docs/instagram-platform/content-publishing/
* Meta API media publish endpoint: https://developers.facebook.com/docs/graph-api/reference/shadow-ig-user/media_publish/
* Trial Reels overview: https://about.fb.com/news/2024/12/trial-reels-try-content-non-followers-first-see-what-perfoms-best/
* Meta insights reference: https://developers.facebook.com/docs/insights/references/
* Secondary current publishing guide (Trial request shape; verify against Meta): https://rizamo.com/guides/how-to-post-to-instagram-via-api/
* NVIDIA legacy compute capabilities: https://developer.nvidia.com/cuda/gpus/legacy
* Ollama GPU support: https://docs.ollama.com/gpu
* Ollama model sizes: https://ollama.com/library/qwen3/tags
