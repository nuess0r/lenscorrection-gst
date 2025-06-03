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
#  $ LANG= GST_DEBUG=python:4 gst-launch-1.0 fakesrc num-buffers=10 ! video/x-raw, width=640, height=480, framerate=30/1 ! lenscorrection aperture=5.6 focallength=50 distance=10.0 reverse=False grid=False cammaker="NIKON CORPORATION" cammodel="NIKON D7200" lens="Nikon AF Zoom-Nikkor 28-105mm f/3.5-4.5D IF" ! fakesink
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
DEFAULT_FOCALLENGTH = 2.5
DEFAULT_DISTANCE = 10.0
DEFAULT_REVERSE = False
DEFAULT_GRID = False
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
        "focallength": (float,
            "Focallength",
            "The focal length in mm at which the image was taken.",
            0.0,
            1000000,
            DEFAULT_FOCALLENGTH,
            GObject.ParamFlags.READWRITE
           ),
        "distance": (float,
            "Distance",
            "The approximative focus distance in meters (distance > 0)",
            0.0,
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
        "grid": (bool,
            "Grid",
            "If this parameter is true, a rectangular grid is drawn over the source image before applying the lenscorrecton to show the applied correction (mainly for debuging)",
            DEFAULT_GRID,
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
        self.grid = DEFAULT_GRID
        self.cammaker = DEFAULT_CAMMAKER
        self.cammodel = DEFAULT_CAMMODEL
        self.lens = DEFAULT_LENS
        
    def query_lensfun(self):
        """
        Query the Lensfun db for camera parameters
        """
        Gst.info("query lensfun database")
        try:
            #Query the Lensfun db for camera parameters
            Gst.info(f"Opening Lensfun database: {self.cammaker}, {self.cammodel}")
            db = lensfunpy.Database()
            self.cam = db.find_cameras(self.cammaker, self.cammodel)[0]
            Gst.info(f"Camera found: {self.cam}")
        except Exception as e:
            Gst.error("Camera not found %s" % e)
            return False
        try: 
            if self.lens:
                self.lensmodel = db.find_lenses(self.cam,lens=self.lens)[0]
            else:
                self.lensmodel = db.find_lenses(self.cam)[0]
            Gst.info(f"Lens found: {self.lensmodel}")
        except Exception as e:
            Gst.error("Lens not found %s" % e)
            return False
        try:
            mod = lensfunpy.Modifier(self.lensmodel, self.cam.crop_factor, self.width, self.height)
            mod.initialize(self.focallength, self.aperture, self.distance, reverse=self.reverse)

            self.undistCoords = mod.apply_geometry_distortion()
            Gst.info(f"Undisortion coordinates: {self.undistCoords}")
            Gst.info(f"Undisortion coordinate size: {self.undistCoords.shape}")

            return True

        except Exception as e:
            Gst.error("%s" % e)
            return False

    def draw_grid(self):
        self.overlay = numpy.zeros((self.height, self.width, 3), dtype=numpy.uint8)
        font = cv2.FONT_HERSHEY_SIMPLEX
        stepx = int(self.width/8)
        stepy = int(self.height/8)
        for i in range(1,8):
            # draw blue grid lines
            cv2.line(self.overlay,(stepx*i,0),(stepx*i,self.height),(0,0,255),5)
            cv2.line(self.overlay,(0,stepy*i),(self.width,stepy*i),(0,0,255),5)
        cv2.putText(self.overlay,text=f"{self.cam}",
                    org=(stepx+100,stepy+50),
                    fontFace=font,
                    fontScale=1,
                    color=(255,255,255),
                    thickness=5,
                    lineType=cv2.LINE_AA)
        cv2.putText(self.overlay,text=f"{self.lensmodel}",
                    org=(stepx+100,stepy+100),
                    fontFace=font,
                    fontScale=1,
                    color=(255,255,255),
                    thickness=5,
                    lineType=cv2.LINE_AA)
        cv2.putText(self.overlay,text=f"{self.focallength}mm, F{self.aperture}, {self.distance}m",
                    org=(stepx+100,stepy+150),
                    fontFace=font,
                    fontScale=1,
                    color=(255,255,255),
                    thickness=5,
                    lineType=cv2.LINE_AA)
        return True

    def do_set_caps(self, incaps, outcaps):
        s = incaps.get_structure(0)
        self.width = s.get_int("width").value
        self.height = s.get_int("height").value

        # Query the database here as the do_start method is executed before width and height is set
        self.query_lensfun()
        
        if self.grid:
            self.draw_grid()

        return True

    def do_get_property(self, prop):
        if prop.name == 'aperture':
            return self.aperture
        elif prop.name == 'focallength':
            return self.focallength
        elif prop.name == 'distance':
            return self.distance
        elif prop.name == 'reverse':
            return self.reverse
        elif prop.name == 'grid':
            return self.grid
        elif prop.name == 'cammaker':
            return self.cammaker
        elif prop.name == 'cammodel':
            return self.cammodel
        elif prop.name == 'lens':
            return self.lens
        else:
            raise AttributeError('unknown property %s' % prop.name)

    def do_set_property(self, prop, value):
        if prop.name == 'aperture':
            self.aperture = value
        elif prop.name == 'focallength':
            self.focallength = value
        elif prop.name == 'distance':
            self.distance = value
        elif prop.name == 'reverse':
            self.reverse = value
        elif prop.name == 'grid':
            self.grid = value
        elif prop.name == 'cammaker':
            self.cammaker = value
        elif prop.name == 'cammodel':
            self.cammodel = value
        elif prop.name == 'lens':
            self.lens = value
        else:
            raise AttributeError('unknown property %s' % prop.name)

    def do_transform_ip(self, inbuf):
        try:
            inbuf_info = inbuf.map(Gst.MapFlags.READ | Gst.MapFlags.WRITE)
            with inbuf_info:
                frame = numpy.ndarray(
                    shape=(self.height, self.width, 3),
                    dtype=numpy.uint8,
                    buffer=inbuf_info.data,
                )

                if self.grid:
                    img = cv2.addWeighted(frame, 1, self.overlay, 0.7, 0)
                else:
                    img = frame
                
                array = cv2.remap(img, self.undistCoords, None, cv2.INTER_NEAREST)
                
                frame[:] = array[:]
                return Gst.FlowReturn.OK

        except Gst.MapError as e:
            Gst.error("mapping error %s" % e)
            return Gst.FlowReturn.ERROR
        except Exception as e:
            Gst.error("%s" % e)
            return Gst.FlowReturn.ERROR


GObject.type_register(Lenscorrection)
__gstelementfactory__ = ("lenscorrection", Gst.Rank.NONE, Lenscorrection)

