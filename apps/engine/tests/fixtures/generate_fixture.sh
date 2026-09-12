#!/bin/bash
cd "$(dirname "$0")"
ffmpeg -y \
  -f lavfi -i "testsrc=size=640x480:rate=30:duration=8" \
  -f lavfi -i "sine=frequency=440:duration=8" \
  -c:v libx264 -preset ultrafast -c:a aac -shortest \
  test_video.mp4
echo "Fixture created: test_video.mp4"
