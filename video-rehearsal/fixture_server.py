"""Loopback-only fixture server, not a production server. Single byte ranges only."""
import argparse
import functools
import http.server
import pathlib
import re


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = pathlib.Path(self.translate_path(self.path))
        match = re.fullmatch(r'bytes=(\d+)-(\d*)', self.headers.get('Range', ''))
        if match and path.is_file():
            data = path.read_bytes()
            start = int(match[1])
            end = min(int(match[2]) if match[2] else len(data) - 1, len(data) - 1)
            if start >= len(data) or end < start:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{len(data)}')
                self.end_headers()
                return
            self.send_response(206)
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Type', self.guess_type(str(path)))
            self.send_header('Content-Range', f'bytes {start}-{end}/{len(data)}')
            self.send_header('Content-Length', str(end - start + 1))
            self.end_headers()
            self.wfile.write(data[start:end + 1])
            return
        super().do_GET()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=pathlib.Path)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    handler = functools.partial(RangeHandler, directory=str(args.directory.resolve()))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', args.port), handler)
    print(f'Fixture server: http://127.0.0.1:{server.server_port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
