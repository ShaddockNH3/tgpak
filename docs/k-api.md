# Web K 内部 API

打开 `https://web.telegram.org/k/`，登录态存在 profile 目录。页面加载完大约 13 秒，
这段时间就是在等它把 manager 挂到 window 上，别提前动手。

```js
window.rootScope.managers.apiManager          // MTProto 入口
window.rootScope.managers.apiFileManager      // 下载（用这个）
window.appDownloadManager                     // 下载（有坑，见下）
```

进页面先按一下 `Escape`，K 偶尔会弹「外观设置」挡在前面。

## 拿频道 peer

MTProto 的方法都要 inputPeer，`getDialogs` 里有现成的 id 和 access_hash：

```js
const d = await api.invokeApi('messages.getDialogs', {
  offset_date: 0, offset_id: 0, offset_peer: {_: 'inputPeerEmpty'},
  limit: 100, hash: 0});
const c = d.chats.find(x => x.username === 'channel_name');
const peer = {_: 'inputPeerChannel', channel_id: c.id, access_hash: c.access_hash};
```

频道不在对话列表里就找不到。私有频道得先手动打开一次。

## 找帖子

```js
await api.invokeApi('messages.search', {
  peer, q: '#作者tag', filter: {_: 'inputMessagesFilterEmpty'},
  min_date: 0, max_date: 0, offset_id: 0, add_offset: 0,
  limit: 100, max_id: 0, min_id: 0, hash: 0});
```

翻页把 `offset_id` 设成上一页最小的消息 id，直到返回空。

只有带井号的 tag 搜得到，光搜作者名是 0 条。Telegram 的搜索按词切，中文人名切不出来。

链接可能在 `m.entities` 里而不在正文里。作者会把一个 emoji 做成超链接，正文只显示 🤏🏾，
URL 藏在 `messageEntityTextUrl`。

## 取评论区

图放在评论区相册里，频道帖子只是封面加标题。用 `messages.getReplies`：

```js
await api.invokeApi('messages.getReplies', {
  peer, msg_id: postId, offset_id: 0, offset_date: 0, add_offset: 0,
  limit: 100, max_id: 0, min_id: 0, hash: 0});
```

返回是倒序的，翻过来就是相册顺序。每条消息的 `media.photo` 或 `media.document` 里带着
文件 id、尺寸列表和 `file_reference`。评论超过 100 条用 `offset_id` 往早翻，按 `message.id` 去重。

顺序只有这一个来源。文件 id 末位跟顺序无关。

## 下载

```js
const blob = await rootScope.managers.apiFileManager
                          .downloadMedia({media: photo, thumb: 最大尺寸});
```

四个坑：

1. 用 `apiFileManager`，不要用 `appDownloadManager`。后者是 worker 镜像，下文档前要走
   `appDocsManager.getDoc()` 查本地 store，没渲染过的文档查不到，抛
   `Cannot read properties of undefined`。

2. `media` 传裸的 photo / document（`msg.media.photo`）。传 `msg.media` 整个包装会报
   `Cannot set properties of undefined`。

3. 照片必须给 `thumb`，不给就 reject（`preloadPhoto photoEmpty!`）。尺寸自己挑：`sizes` 里混着
   `photoSizeProgressive`（最大档常常是它，没有 `size` 字段，只有 `sizes` 数组）和
   `photoStrippedSize`（模糊占位）。按 `w*h` 排，不要按 `size` 排。给了哪个 `thumb` 就下哪张，
   挑错等于下错尺寸。

4. 文档必须给 `fileName`，否则报 `Cannot read properties of undefined (reading 'id')`。
   而且同一个文档第一次调用必定失败，失败完状态才准备好。先空跑一发：

```js
try { await afm.downloadMedia({media: doc, fileName: '__warmup__'}); } catch (e) {}
const blob = await afm.downloadMedia({media: doc, fileName: name});
```

## 落盘

Blob 不要转 base64。一张 500KB 的图要在 JS 里拼七十万字符再回 Python 解码，慢十几倍，
还可能爆栈。直接 POST 到本机：

```js
await fetch('http://127.0.0.1:8899/put?name=' + encodeURIComponent(name),
            {method: 'POST', body: blob});
```

HTTPS 页面请求 `http://127.0.0.1` 不算混合内容，localhost 是可信来源。
Python 那边起个 `ThreadingHTTPServer` 收 body 写盘，见 `sink.py`。

## 想看源码

`performance.getEntriesByType('resource')` 里能翻出加载过的 JS 文件名，
`appDownloadManager-xxxx.js` 这种。下回来读，比瞎猜接口快。
