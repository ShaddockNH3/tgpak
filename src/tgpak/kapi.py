"""Telegram Web K 驱动。

Web K 把内部 manager 挂在 window.rootScope.managers 上，可以直接调 MTProto：

    managers.apiManager.invokeApi(method, params)
    appDownloadManager.downloadMedia({media, thumb}) -> Blob

两条要注意的：
1. 相册顺序 = 评论区消息 id 升序。photo.id 是随机 64 位，跟顺序无关。
2. downloadMedia 要传裸 photo/document 对象，传 messageMediaPhoto 包装会报错。
"""
import json
import pathlib
import time

from playwright.sync_api import sync_playwright

from .sink import Sink

JS_RESOLVE = r"""
async (username) => {
    const api = window.rootScope.managers.apiManager;
    const d = await api.invokeApi('messages.getDialogs', {
        offset_date: 0, offset_id: 0, offset_peer: {_: 'inputPeerEmpty'},
        limit: 100, hash: 0});
    const c = (d.chats || []).find(x => x.username === username || x.title === username);
    if (!c) return null;
    window.__peer = {_: 'inputPeerChannel', channel_id: c.id, access_hash: c.access_hash};
    return {id: String(c.id), title: c.title};
}
"""

JS_SEARCH = r"""
async ([q, offset]) => {
    const api = window.rootScope.managers.apiManager;
    const r = await api.invokeApi('messages.search', {
        peer: window.__peer, q, filter: {_: 'inputMessagesFilterEmpty'},
        min_date: 0, max_date: 0, offset_id: offset, add_offset: 0,
        limit: 100, max_id: 0, min_id: 0, hash: 0});
    return (r.messages || []).map(m => ({
        id: m.id,
        grouped: String(m.grouped_id || ''),
        text: (m.message || '').replace(/\n/g, ' ')
    }));
}
"""

JS_REPLIES = r"""
async (postId) => {
    const api = window.rootScope.managers.apiManager;
    const peer = window.__peer;
    let all = [], offset = 0;
    for (let i = 0; i < 30; i++) {
        const r = await api.invokeApi('messages.getReplies', {
            peer, msg_id: postId, offset_id: offset, offset_date: 0, add_offset: 0,
            limit: 100, max_id: 0, min_id: 0, hash: 0});
        const msgs = r.messages || [];
        if (!msgs.length) break;
        all = all.concat(msgs);
        const oldest = Math.min(...msgs.map(m => m.id));
        if (offset && oldest >= offset) break;
        offset = oldest;
        if (msgs.length < 100) break;
    }
    const seen = new Set();
    const items = [];
    window.__media = {};
    for (const m of all.sort((a, b) => a.id - b.id)) {
        if (seen.has(m.id)) continue;
        seen.add(m.id);
        const md = m.media || {};
        if (!md.photo && !md.document) continue;
        const obj = md.photo || md.document;
        window.__media[m.id] = obj;
        let fname = null;
        if (md.document) {
            const fa = (md.document.attributes || []).find(a => a.file_name);
            if (fa) fname = fa.file_name;
        }
        const mime = md.photo ? 'image/jpeg' : (md.document.mime_type || '');
        items.push({
            idx: items.length + 1, msg: m.id, id: String(obj.id),
            kind: md.photo ? 'photo' : 'doc', fname, mime,
            size: obj.size ?? null,
            ext: md.photo ? 'jpg'
                : (mime.includes('video') ? 'mp4' : (mime.includes('zip') ? 'zip' : 'bin'))
        });
    }
    return items;
}
"""

JS_ONE = r"""
async ([msgId, name, port]) => {
    const obj = window.__media[msgId];
    if (!obj) return 'NO_MEDIA';
    const afm = window.rootScope.managers.apiFileManager;
    let arg;
    if (obj._ === 'document' || obj.mime_type) {
        // 文档第一次调用必定报 Cannot read properties of undefined (reading 'id')，
        // 失败一次之后状态才准备好。先空跑一发，代价是立即返回，不下载。
        try { await afm.downloadMedia({media: obj, fileName: '__warmup__'}); } catch (e) {}
        arg = {media: obj, fileName: name};
    } else {
        const sizes = (obj.sizes || [])
            .filter(s => s.w && s.h && s._ !== 'photoStrippedSize')
            .sort((a, b) => (b.w * b.h) - (a.w * a.h));
        arg = {media: obj, thumb: sizes[0]};
    }
    try {
        const blob = await afm.downloadMedia(arg);
        if (!blob || !blob.size) return 'NO_BLOB';
        const r = await fetch('http://127.0.0.1:' + port + '/put?name=' + encodeURIComponent(name),
                              {method: 'POST', body: blob});
        const t = await r.text();
        return t.startsWith('ERR') ? t : String(blob.size);
    } catch (e) { return 'ERR:' + (e && e.message ? e.message : e); }
}
"""


def launch(pw, profile: pathlib.Path, headless=False):
    profile.mkdir(parents=True, exist_ok=True)
    return pw.chromium.launch_persistent_context(
        user_data_dir=str(profile), channel="chrome", headless=headless,
        viewport={"width": 1300, "height": 820},
        accept_downloads=True,
        ignore_default_args=["--enable-automation"],
        args=["--no-first-run", "--disable-blink-features=AutomationControlled"],
    )


def login(profile: pathlib.Path):
    """打开 K 让你自己登录，登录完回车。"""
    with sync_playwright() as pw:
        ctx = launch(pw, profile, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://web.telegram.org/k/", wait_until="domcontentloaded")
        print("在窗口里登录 Telegram（扫码或手机号都行）。登录完回终端按回车。")
        input()
        ctx.close()
    print("登录态已存进", profile)


class WebK:
    def __init__(self, profile: pathlib.Path, channel: str, headless=False, port=8899):
        self.profile = profile
        self.channel = channel
        self.headless = headless
        self.sink = Sink(port).start()
        self.port = port
        self._pw = None
        self._ctx = None
        self.page = None
        self.info = None
        self.last_error = ""

    def __enter__(self):
        self._pw = sync_playwright().start()
        self._ctx = launch(self._pw, self.profile, self.headless)
        self.page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        self.page.goto("https://web.telegram.org/k/", timeout=90000,
                       wait_until="domcontentloaded")
        self.page.wait_for_timeout(13000)
        self.page.keyboard.press("Escape")
        self.info = self.page.evaluate(JS_RESOLVE, self.channel)
        if not self.info:
            raise SystemExit(f"找不到频道 {self.channel}，确认已登录且它在对话列表里")
        return self

    def __exit__(self, *exc):
        self._ctx.close()
        self._pw.stop()
        self.sink.stop()

    def search(self, tag: str):
        """在频道里搜 tag，翻页拿全部帖子。"""
        found, offset, seen = [], 0, set()
        for _ in range(20):
            batch = self.page.evaluate(JS_SEARCH, [tag, offset])
            if not batch:
                break
            for m in batch:
                if m["id"] not in seen:
                    seen.add(m["id"])
                    found.append(m)
            oldest = min(m["id"] for m in batch)
            if oldest == offset:
                break
            offset = oldest
            time.sleep(1.0)
        return found

    def load(self, post_id: int):
        """拿评论区（相册）全部媒体，按相册顺序返回。"""
        items = self.page.evaluate(JS_REPLIES, post_id)
        if not isinstance(items, list):
            raise RuntimeError(f"第 {post_id} 帖拉取失败: {items}")
        return items

    def download(self, msg_id: int, name: str, dest: pathlib.Path) -> int | None:
        """下载一个媒体到 dest/name，返回字节数。"""
        self.sink.set_dir(dest)
        r = self.page.evaluate(JS_ONE, [msg_id, name, self.port])
        if isinstance(r, str) and (r.startswith("ERR") or r in ("NO_MEDIA", "NO_BLOB")):
            self.last_error = r
            return None
        self.last_error = ""
        return int(r)
