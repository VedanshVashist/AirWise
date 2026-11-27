"""Exercise the deployed scripts and poster artwork in an installed Chrome browser."""
import os
import shutil
import subprocess
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from urllib.parse import unquote
from unittest.mock import patch

import server


def chrome_binary():
    for name in ("google-chrome", "chromium", "chrome"):
        if binary := shutil.which(name):
            return binary
    for root in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        binary = Path(os.getenv(root, ".")) / "Google/Chrome/Application/chrome.exe"
        if binary.is_file():
            return str(binary)
    return None


# Drive the same controls a visitor uses. A status mutation signals completion
# after the asynchronous artwork decode, API response and canvas export.
WORKFLOW = """
window.addEventListener('load', () => {
    const finish = result => fetch('/result/' + encodeURIComponent(result));
    const status = document.querySelector('#campaignStatus');
    new MutationObserver((_, observer) => {
        if (status.textContent.startsWith('Could not')) {
            observer.disconnect();
            finish(status.textContent);
            return;
        }
        if (!status.textContent.startsWith('Campaign ready')) return;
        observer.disconnect();
        const output = document.querySelector('#campaignOutput');
        const png = output.querySelector('[download]').href;
        const transcript = output.querySelector('textarea').value;
        const valid = png.startsWith('data:image/png;base64,') &&
            transcript.includes('Give your commute a cleaner route') &&
            transcript.includes('New Delhi') && transcript.includes('Current AQI unavailable');
        finish(valid ? 'WORKFLOW PASSED' : 'Unexpected campaign export');
    }).observe(status, {childList: true});
    document.querySelector('.skip').click();
    if (location.hash !== '#campaign' || document.activeElement.id !== 'main') {
        finish('Skip link failed');
        return;
    }
    const form = document.querySelector('#campaignForm');
    form.elements.audience.value = 'Commuters';
    form.requestSubmit();
});
"""


class BrowserFixture(server.Handler):
    def do_GET(self):
        if self.path.startswith("/result/"):
            self.server.result = unquote(self.path.removeprefix("/result/"))
            self.send_asset("OK", "text/plain")
            self.server.finished.set()
        elif self.path == "/":
            index = (server.PUBLIC / "index.html").read_text(encoding="utf-8")
            self.send_asset(index.replace("</body>", '<script src="/workflow.js"></script></body>'), "text/html")
        elif self.path == "/workflow.js":
            self.send_asset(WORKFLOW, "text/javascript")
        else:
            super().do_GET()

    def send_asset(self, content, media_type):
        raw = content.encode()
        self.send_response(200)
        self.send_header("Content-Type", media_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


class BrowserTests(unittest.TestCase):
    @unittest.skipUnless(chrome_binary(), "Chrome or Chromium is required for the browser workflow")
    def test_campaign_export_when_air_provider_is_offline(self):
        with TemporaryDirectory() as profile, patch.dict(os.environ, OPENAI_API_KEY=""), patch.object(
                server, "remote", side_effect=OSError), ThreadingHTTPServer(("127.0.0.1", 0), BrowserFixture) as web:
            web.finished = Event()
            thread = Thread(target=web.serve_forever, daemon=True)
            thread.start()
            try:
                browser = subprocess.Popen([
                    chrome_binary(), "--headless", "--disable-gpu", "--no-first-run", "--disable-background-networking",
                    "--user-data-dir=" + profile,
                    f"http://127.0.0.1:{web.server_port}/#campaign",
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    self.assertTrue(web.finished.wait(40), "Chrome did not finish the campaign workflow")
                    self.assertEqual(web.result, "WORKFLOW PASSED")
                finally:
                    browser.terminate()
                    browser.wait(timeout=10)
            finally:
                web.shutdown()
                thread.join()
