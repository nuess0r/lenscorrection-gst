#!/usr/bin/env python3
# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4

# test.py
# 2025 Christoph Zimmermann <nussgipfel@brain4free.org>

import gi
import time

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")

from gi.repository import Gst, GstBase, GLib, GObject  # noqa: E402

Gst.init(None)
Gst.init_python()

gstreamer_pipeline = """
                videotestsrc num-buffers=100 ! video/x-raw, width=640, height=480, framerate=30/1 ! videoconvert ! video/x-raw, width=640, height=480, framerate=30/1 ! lenscorrection ! video/x-raw, width=640, height=480, framerate=30/1 ! tee name=t !
                queue ! videoconvert !  x264enc tune=zerolatency bitrate=2000 speed-preset=ultrafast !  flvmux streamable=true ! udpsink sync=false
                t. ! queue ! videoconvert ! xvimagesink handle-events=false sync=false
"""


# GStreamer pipeline
pipeline = Gst.parse_launch(gstreamer_pipeline)

# Start processing
start_time = time.time()
pipeline.set_state(Gst.State.PLAYING)
bus = pipeline.get_bus()

# Wait for the pipeline to finish
msg = bus.timed_pop_filtered(
    Gst.CLOCK_TIME_NONE, Gst.MessageType.ERROR | Gst.MessageType.EOS
)

if msg:
    t = msg.type
    if t == Gst.MessageType.ERROR:
        err, debug = msg.parse_error()
        print(f"Error: {err}, {debug}")
    elif t == Gst.MessageType.EOS:
        print("Pipeline finished successfully.")

pipeline.set_state(Gst.State.NULL)

# Log total video processing time
total_time = time.time() - start_time
print(f"Total wall-clock processing time for the video: {total_time:.2f} seconds")

