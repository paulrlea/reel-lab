# iPhone footage ingestion on Windows

The free local workflow uses Windows SMB sharing and an iPhone Shortcut. Only share the dedicated incoming directory, not your whole project or user profile; keep SMB on a trusted private network and never forward its ports to the Internet.

## Windows 10 setup

From the project directory, create `data\incoming` if missing. In Explorer right-click this folder, select Properties > Sharing > Advanced Sharing, enable sharing, and name it `ReelLabFootage`. Grant Change/Read only to a designated password-protected Windows account; also ensure NTFS permissions allow that account to write. In Windows network settings confirm the trusted home network is Private, enable file and printer sharing for Private networks only, and retain password-protected sharing. If you are not authorized to change those settings, ask the administrator. Use `ipconfig` to find the current LAN IPv4 address. Consider a DHCP reservation on your own router to keep it stable.

On the iPhone, connect to the same Wi-Fi, open Files > Browse > More > Connect to Server, and enter `smb://PC_IP/ReelLabFootage`. Select Registered User and sign in with the authorized Windows username/password (not the Windows Hello PIN). Test by copying one non-sensitive video to the folder with Photos > Share > Save to Files.

## iPhone Shortcut

Make a Photos album called Reel Lab Footage. Add only footage intended for content. In Shortcuts, create a shortcut with Find Photos (album equals Reel Lab Footage, media type video), Repeat with Each, Save File (repeat item, choose the shared folder, Ask Where to Save off, overwrite off if available). Test manually with one small clip. Some iOS versions/providers may not support unattended SMB writes or may ask for confirmation while locked; if so, use Share > Save to Files manually or consider Immich. Do not automatically delete iPhone originals. For automation, use Shortcuts > Automation > Wi-Fi (your home network) or Charger > Run Immediately where supported, and choose your tested shortcut. Avoid repeated bulk transfers by using a separate sent album or tracking a successfully transferred item; Reel Lab also deduplicates identical bytes. Files may have repeated iPhone names: do not overwrite existing different footage.

## Start the Reel Lab watcher

From your project directory, after installing Python and Reel Lab according to INSTALL.md:

```powershell
python -m reel_lab watch-footage --seconds 15 --settle 30
```

The watcher uses `data/incoming` by default and copies stable `.mov`, `.mp4` and `.m4v` files to `data/footage/YYYY-MM-DD/<sha256>.<extension>` without deleting originals. The date is the source file modification date, not necessarily capture date. The settling period is a heuristic, not a guarantee; use longer periods for slow transfers. The watcher verifies file bytes and rechecks the source signature. To use a separate shared folder, pass `--folder "C:\your\incoming"`. Keep only one watcher running. It is separate from the publishing worker.

```powershell
python -m reel_lab footage
python -m reel_lab add "data\footage\YYYY-MM-DD\HASH.mov" --brief "Describe your footage" --at 2027-01-01T18:00:00-06:00
```

Replace the example path and time. The text-only LLM can't infer what happened in footage without a brief; review any caption and actual clip before approving. Batch ingest accepts MOV/MP4/M4V files with matching `.txt` briefs. Imports are only a footage catalog and do not create or publish posts automatically.

For unattended startup, create a Windows Task Scheduler task with program `.venv\Scripts\python.exe` (absolute path), arguments `-m reel_lab watch-footage --seconds 15 --settle 30`, and Start in set to the absolute project directory. Run under the user with access to the incoming folder. Do not start competing watcher processes. Keep the PC awake, and periodically back up and clean up the incoming folder yourself after verifying archived copies.
