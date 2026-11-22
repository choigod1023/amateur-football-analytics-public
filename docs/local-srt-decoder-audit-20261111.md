# Local SRT decoding audit and alternative sender

The running wide-video simulation has H.264 errors in the player and analysis
logs. In this test, the four original MP4 files and their concat playlist
decoded locally without errors. An isolated direct FFmpeg SRT sender/receiver
also produced no decoder errors over 10 seconds. The existing 6500×1000 H.264
stream-copy publisher sent through a separate local MediaMTX 1.21.3 instance
and TCP RTSP reader reproduced decoding errors. With its default write queue,
MediaMTX reported a slow reader and discarded 40 frames. Increasing
`writeQueueSize` to 8192 removed that warning in a short run but did not remove
all decoder errors. This confirms at least one queue-loss failure mode, not
the cause of every error; joins before a keyframe and packet loss remain
possible. We did not measure end-to-end latency or peak RAM of the larger queue.

An isolated trial instead decoded and re-encoded the 25 fps source at its
original 6500×1000 resolution using H.264 libx264 ultrafast, no B-frames, and
25-frame GOP. With MediaMTX `writeQueueSize: 8192`, the TCP RTSP receiver
decoded 15 seconds without logged H.264 errors or a slow-reader warning.
This is one short local run, not proof of loss-free playback, long-duration
stability, iPhone/Moblin compatibility, or performance on a congested network.
CPU encoding and the larger queue add resource and latency costs. The existing
user-facing processes and their settings were not changed.

`scripts/local_playlist_sender.py` provides this sender for **loopback-only**
tests. It requires an existing FFmpeg concat playlist and a running SRT
listener; it does not modify an incoming iPhone stream. For a 25 fps playlist:

```powershell
$python = '..\football-coach-server\.venv\Scripts\python.exe'
& $python scripts/local_playlist_sender.py --ffmpeg <ffmpeg.exe> --playlist <playlist.txt> --output 'srt://127.0.0.1:18891?streamid=publish:match&pkt_size=1316'
```

In an isolated MediaMTX instance the relevant settings were `writeQueueSize:
8192`, `rtspTransports: [tcp]`, loopback-only RTSP/SRT addresses, and unused
protocols disabled. Check memory and latency under load before retaining a
larger queue. Other frame rates need an explicitly chosen keyframe interval;
`-g 25` means roughly one second only at 25 fps. This sender does not send the
playlist progress notifications used by the existing simulation's identity
reset, and therefore is not a drop-in replacement for that supervisor. Do not
switch an active dashboard to it without also preserving cut notifications.

The existing application and player must be tested together with the new
sender, including continuous operation across playlist cuts, reconnection,
decoder errors after startup, analysis-to-video delay, and independently
labelled frame correspondence. Moblin's encoder settings must be verified
separately. The unchanged running dashboard may still exhibit decoding errors.
