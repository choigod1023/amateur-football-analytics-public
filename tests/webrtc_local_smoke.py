"""Loopback-only SRT -> MediaMTX -> authenticated WHEP -> decoded video.

Run with Python having aiortc and requests installed, and pass --ffmpeg and
--mediamtx executable paths. Test credentials are random, never printed, and
removed with the temporary configuration. While running they are present in
process arguments and may be visible to other users on the same computer.

This tests loopback only: it is not a test of an iPhone, a browser, TLS,
public ICE, NAT traversal, or a deployed server. It does not alter network
configuration. Ports are fixed, so run this separately from other smoke tests.
"""
import argparse
import asyncio
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode

import aioice.ice
import requests
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription

parser = argparse.ArgumentParser()
parser.add_argument('--ffmpeg', required=True)
parser.add_argument('--mediamtx', required=True)
args = parser.parse_args()

# aioice normally excludes loopback. The test server accepts only loopback;
# without a loopback client ICE candidate the connection stays in checking.
# This override is strictly local to this disposable test process.
aioice.ice.get_host_addresses = lambda use_ipv4, use_ipv6: ['127.0.0.1'] if use_ipv4 else []

password, phrase = secrets.token_hex(16), secrets.token_hex(16)
config = f'''logLevel: error
rtsp: false
rtmp: false
hls: false
moq: false
webrtc: true
webrtcAddress: 127.0.0.1:18889
webrtcLocalUDPAddress: 127.0.0.1:18189
webrtcIPsFromInterfaces: false
webrtcAdditionalHosts: [127.0.0.1]
srt: true
srtAddress: 127.0.0.1:18890
api: false
metrics: false
pprof: false
authMethod: internal
authInternalUsers:
  - user: pub
    pass: {password}
    ips: [127.0.0.1]
    permissions:
      - action: publish
        path: match
  - user: read
    pass: {password}
    ips: [127.0.0.1]
    permissions:
      - action: read
        path: match
paths:
  match:
    srtPublishPassphrase: {phrase}
'''


async def receive():
    peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    got_frame = asyncio.Event()
    frame_size = []
    errors = []
    tasks = []

    @peer.on('track')
    def on_track(track):
        async def consume():
            if track.kind == 'video':
                try:
                    frame = await track.recv()
                    frame_size.extend((frame.width, frame.height))
                    got_frame.set()
                except Exception as exc:
                    errors.append(type(exc).__name__)
                    got_frame.set()
        tasks.append(asyncio.create_task(consume()))

    peer.addTransceiver('video', direction='recvonly')
    try:
        await peer.setLocalDescription(await peer.createOffer())
        endpoint = 'http://127.0.0.1:18889/match/whep'
        headers = {'Content-Type': 'application/sdp'}
        for attempt in range(15):
            bad = await asyncio.to_thread(requests.post, endpoint, data=peer.localDescription.sdp, headers=headers, timeout=4)
            if bad.status_code == 401:
                break
            await asyncio.sleep(1)
        if bad.status_code != 401:
            raise RuntimeError(f'Unauthenticated WHEP returned {bad.status_code}, expected 401')
        # The publisher can still be coming online; 404 is a transient state.
        for attempt in range(15):
            good = await asyncio.to_thread(requests.post, endpoint, data=peer.localDescription.sdp, headers=headers, auth=('read', password), timeout=4)
            if good.status_code == 201:
                break
            if good.status_code != 404:
                raise RuntimeError(f'Authenticated WHEP returned {good.status_code}')
            await asyncio.sleep(1)
        if good.status_code != 201:
            raise RuntimeError('Stream did not become available')
        await peer.setRemoteDescription(RTCSessionDescription(sdp=good.text, type='answer'))
        await asyncio.wait_for(got_frame.wait(), timeout=20)
        if errors or not frame_size:
            raise RuntimeError('Video decoding failed: ' + ', '.join(errors))
        print('unauthenticated_http=401 authenticated_http=201')
        print('ice_state=' + peer.iceConnectionState)
        print('decoded_video_size=' + str(frame_size[0]) + 'x' + str(frame_size[1]))
    finally:
        await peer.close()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


creation = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
with tempfile.TemporaryDirectory() as directory:
    config_file = Path(directory) / 'mediamtx.yml'
    config_file.write_text(config, encoding='utf-8')
    server = subprocess.Popen([args.mediamtx, str(config_file)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation)
    publisher = None
    try:
        time.sleep(1)
        if server.poll() is not None:
            raise RuntimeError('MediaMTX failed to start')
        query = urlencode({'streamid': f'publish:match:pub:{password}', 'passphrase': phrase, 'pbkeylen': '16', 'pkt_size': '1316'})
        publisher = subprocess.Popen([args.ffmpeg, '-loglevel', 'quiet', '-re', '-f', 'lavfi', '-i', 'testsrc=size=320x180:rate=10', '-t', '50', '-c:v', 'libx264', '-profile:v', 'baseline', '-pix_fmt', 'yuv420p', '-g', '10', '-preset', 'ultrafast', '-f', 'mpegts', 'srt://127.0.0.1:18890?' + query], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation)
        time.sleep(2)
        if publisher.poll() is not None:
            raise RuntimeError('Publisher failed to start')
        asyncio.run(receive())
    finally:
        if publisher and publisher.poll() is None:
            publisher.kill()
            publisher.wait()
        if server.poll() is None:
            server.terminate()
        server.wait(timeout=10)
