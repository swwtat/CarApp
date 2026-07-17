import cv2 as cv
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 8080
latest_frame = None
lock = threading.Lock()

class H(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/status":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok" if latest_frame is not None else b"no_frame")
        elif self.path == "/capture":
            self.serve("image/jpeg")

    def serve(self, mime):
        global latest_frame
        with lock:
            if latest_frame is None:
                self.send_response(204)
                self.end_headers()
                return
            _, j = cv.imencode(".jpg", latest_frame, [cv.IMWRITE_JPEG_QUALITY, 80])
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.end_headers()
        self.wfile.write(j.tobytes())

def cap():
    global latest_frame
    c = cv.VideoCapture("/dev/camera_depth")
    c.set(cv.CAP_PROP_FOURCC, cv.VideoWriter.fourcc(*"MJPG"))
    c.set(cv.CAP_PROP_FRAME_WIDTH, 640)
    c.set(cv.CAP_PROP_FRAME_HEIGHT, 480)
    while True:
        r, f = c.read()
        if r:
            with lock:
                latest_frame = f
        time.sleep(0.03)

threading.Thread(target=cap, daemon=True).start()
print("ready")
HTTPServer(("0.0.0.0", PORT), H).serve_forever()
