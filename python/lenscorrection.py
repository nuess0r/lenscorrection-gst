#!/usr/bin/env python
# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4

# lenscorrection.py
# 2025 Christoph Zimmermann <nussgipfel@brain4free.org>
#
# Correct lens distorions using Lensfun database",
#
# You can run the plugin from the source doing from lenscorrection-gst/:
#
#  $ export GST_PLUGIN_PATH=$GST_PLUGIN_PATH:$PWD
#  $ GST_DEBUG=python:4 gst-launch-1.0 fakesrc num-buffers=10 ! lenscorrection ! fakesink
#
#  Example with full set of properties
#  $ LANG= GST_DEBUG=python:4 gst-launch-1.0 fakesrc num-buffers=10 ! video/x-raw, width=640, height=480, framerate=30/1 ! lenscorrection aperture=5.6 focallength=50 distance=10.0 reverse=False cammaker="NIKON CORPORATION" cammodel="NIKON D7200" lens="Nikon AF Zoom-Nikkor 28-105mm f/3.5-4.5D IF" aperture=5.6 focallength=70 distance=10.0 reverse=false ! fakesink
#
# List of supported cameras and lenses: https://lensfun.github.io/lenslist/

import gi
import time
import lensfunpy
import cv2
import numpy

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")

from gi.repository import Gst, GstBase, GLib, GObject  # noqa: E402

Gst.init(None)

DEFAULT_WIDTH = 1920
DEFAULT_HIGH = 1080
DEFAULT_APERTURE = 2.8
DEFAULT_FOCALLENGTH = 50
DEFAULT_DISTANCE = 1000.0
DEFAULT_REVERSE = False
DEFAULT_CAMMAKER = "GoPro"
DEFAULT_CAMMODEL = "HD2"
DEFAULT_LENS = ""

SRC_CAPS = Gst.Caps(
    Gst.Structure(
        "video/x-raw",
        format="RGB",
        width=Gst.IntRange(range(1, GLib.MAXINT)),
        height=Gst.IntRange(range(1, GLib.MAXINT)),
        framerate=Gst.FractionRange(Gst.Fraction(1, 1), Gst.Fraction(GLib.MAXINT, 1)),
    )
)

SINK_CAPS = Gst.Caps(
    Gst.Structure(
        "video/x-raw",
        format="RGB",
        width=Gst.IntRange(range(1, GLib.MAXINT)),
        height=Gst.IntRange(range(1, GLib.MAXINT)),
        framerate=Gst.FractionRange(Gst.Fraction(1, 1), Gst.Fraction(GLib.MAXINT, 1)),
    )
)

SRC_PAD_TEMPLATE = Gst.PadTemplate.new(
    "src", Gst.PadDirection.SRC, Gst.PadPresence.ALWAYS, SRC_CAPS
)

SINK_PAD_TEMPLATE = Gst.PadTemplate.new(
    "sink", Gst.PadDirection.SINK, Gst.PadPresence.ALWAYS, SINK_CAPS
)

class Lenscorrection(GstBase.BaseTransform):

    __gstmetadata__ = (
        "Lenscorrection Filter",
        "Filter",
        "Correct lens distorions using Lensfun database",
        "Christoph Zimmermann <nussgipfel@brain4free.org>",
    )

    __gsttemplates__ = (SRC_PAD_TEMPLATE, SINK_PAD_TEMPLATE)
    
    __gproperties__ = {
        "aperture": (float,
            "Aperture",
            "The aperture (f-number) at which the image was taken.",
            0.01,
            48.0,
            DEFAULT_APERTURE,
            GObject.ParamFlags.READWRITE
           ),
        "focallength": (int,
            "Focallength",
            "The focal length in mm at which the image was taken.",
            0,
            1000000,
            DEFAULT_FOCALLENGTH,
            GObject.ParamFlags.READWRITE
           ),
        "distance": (float,
            "Distance",
            "The approximative focus distance in meters (distance > 0)",
            0.01,
            1000000.0,
            DEFAULT_DISTANCE,
            GObject.ParamFlags.READWRITE
           ),
        "reverse": (bool,
            "Reverse",
            "If this parameter is true, a reverse transform will be prepared. That is, you take an undistorted image as input and convert it so that it will look as if it would be a shot made with lens.",
            DEFAULT_REVERSE,
            GObject.ParamFlags.READWRITE
           ),
        "cammaker": (str,
            "Manufacturer",
            "The camera manufacturer.",
            DEFAULT_CAMMAKER,
            GObject.ParamFlags.READWRITE
           ),
        "cammodel": (str,
            "Camera",
            "The camera model.",
            DEFAULT_CAMMODEL,
            GObject.ParamFlags.READWRITE
           ),
        "lens": (str,
            "Lens",
            "The lens model.",
            DEFAULT_LENS,
            GObject.ParamFlags.READWRITE
           ),
    }

    def __init__(self):
        super().__init__()
        self.set_qos_enabled(True)
        
        self.width = DEFAULT_WIDTH
        self.height = DEFAULT_HIGH
        self.aperture = DEFAULT_APERTURE
        self.focallength = DEFAULT_FOCALLENGTH
        self.distance = DEFAULT_DISTANCE
        self.reverse = DEFAULT_REVERSE
        self.cammaker = DEFAULT_CAMMAKER
        self.cammodel = DEFAULT_CAMMODEL
        self.lens = DEFAULT_LENS
        
    def query_lensfun(self):
        """
        Query the Lensfun db for camera parameters
        """
        Gst.info("query lensfun")
        try:
            #Query the Lensfun db for camera parameters
            Gst.info(f"Opening Lensfun database: {self.cammaker}, {self.cammodel}")
            db = lensfunpy.Database()
            cam = db.find_cameras(self.cammaker, self.cammodel)[0]
            print(cam)
        except Exception as e:
            Gst.error("Camera not found %s" % e)
            return False
        try: 
            if self.lens:
                lens = db.find_lenses(cam,lens=self.lens)[0]
            else:
                lens = db.find_lenses(cam)[0]
            print(lens)
        except Exception as e:
            Gst.error("Lens not found %s" % e)
            return False
        try:
            mod = lensfunpy.Modifier(lens, cam.crop_factor, self.width, self.height)
            mod.initialize(self.focallength, self.aperture, self.distance, reverse=self.reverse)

            self.undistCoords = mod.apply_geometry_distortion()
            Gst.info("%s" % self.undistCoords)

            return True

        except Exception as e:
            Gst.error("%s" % e)
            return False

    def do_set_caps(self, incaps, outcaps):
        Gst.info("set caps")
        s = incaps.get_structure(0)
        self.width = s.get_int("width").value
        self.height = s.get_int("height").value
        
        self.query_lensfun()

        return True

    def do_get_property(self, prop):
        Gst.info("get properties")
        if prop.name == 'aperture':
            return self.aperture
        elif prop.name == 'focallength':
            return self.focallength
        elif prop.name == 'distance':
            return self.distance
        elif prop.name == 'reverse':
            return self.reverse
        elif prop.name == 'cammaker':
            return self.cammaker
        elif prop.name == 'cammodel':
            return self.cammodel
        elif prop.name == 'lens':
            return self.lens
        else:
            raise AttributeError('unknown property %s' % prop.name)

    def do_set_property(self, prop, value):
        Gst.info("set properties")
        if prop.name == 'aperture':
            self.aperture = value
        elif prop.name == 'focallength':
            self.focallength = value
        elif prop.name == 'distance':
            self.distance = value
        elif prop.name == 'reverse':
            self.reverse = value
        elif prop.name == 'cammaker':
            Gst.info("set cammaker")
            Gst.info("%s" % value)
            self.cammaker = value
        elif prop.name == 'cammodel':
            Gst.info("set cammodel")
            Gst.info("%s" % value)
            self.cammodel = value
        elif prop.name == 'lens':
            self.lens = value
        else:
            raise AttributeError('unknown property %s' % prop.name)
            
        #self.query_lensfun()

    def do_transform_ip(self, inbuf):
        try:
            inbuf_info = inbuf.map(Gst.MapFlags.READ | Gst.MapFlags.WRITE)
            with inbuf_info:
                frame = numpy.ndarray(
                    shape=(self.height, self.width, 3),
                    dtype=numpy.uint8,
                    buffer=inbuf_info.data,
                )
                
                cv2.remap(frame, self.undistCoords, None, cv2.INTER_NEAREST)

                return Gst.FlowReturn.OK

        except Gst.MapError as e:
            Gst.error("mapping error %s" % e)
            return Gst.FlowReturn.ERROR
        except Exception as e:
            Gst.error("%s" % e)
            return Gst.FlowReturn.ERROR


GObject.type_register(Lenscorrection)
__gstelementfactory__ = ("lenscorrection", Gst.Rank.NONE, Lenscorrection)

