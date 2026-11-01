# Web K 怎么用

打开 `https://web.telegram.org/k/`，登录态存在 profile 目录。页面加载完大概 13 秒，别省这点时间，
等它把 manager 挂到 window 上：

```js
window.rootScope.managers.apiManager          // MTProto 入口
window.appDownloadManager                     // 下载（有坑，见下）
window.rootScope.managers.apiFileManager      // 下载（用这个）
```

进页面先按一下 `Escape`，K 偶尔会弹「外观设置」挡住。

## 拿频道 peer

MTProto 的方法都要 inputPeer，`getDialogs` 里有现成的 id 和 access_hash：

```js
const d = await api.invokeApi('messages.getDialogs', {
  offset_date: 0, offset_id: 0, offset_peer: {_: 'inputPeerEmpty'},
  limit: 100, hash: 0});
const c = d.chats.find(x => x.username === 'channel_name');
const peer = {_: 'inputPeerChannel', channel_id: c.id, access_hash: c.access_hash};
```

频道不在对话列表里就找不到，私有频道得先手动打开一次。

## 找帖子

```js
await api.invokeApi('messages.search', {
  peer, q: '#作者tag', filter: {_: 'inputMessagesFilterEmpty'},
  min_date: 0, max_date: 0, offset_id: 0, add_offset: 0,
  limit: 100, max_id: 0, min_id: 0, hash: 0});
```

翻页把 `offset_id` 设成上一页最小的消息 id，直到返回空。

搜出来只有"桜桃喵"这种带井号的 tag 才有结果，光搜作者名是 0 条 —— Telegram 的搜索是按词切的，
中文人名切不出来。

链接可能在 `m.entities` 里而不在正文里。作者经常把一个 emoji 做成超链接，正文只显示 🤏🏾，
URL 藏在 `messageEntityTextUrl`。

## 拿相册

作者的图放在评论区相册里，频道帖子只是封面加标题。用 `messages.getReplies`：

```js
await api.invokeApi('messages.getReplies', {
  peer, msg_id: postId, offset_id: 0, offset_date: 0, add_offset: 0,
  limit: 100, max_id: 0, min_id: 0, hash: 0});
```

返回倒序，翻过来就是相册顺序。每条消息的 `media.photo` 或 `media.document` 里有文件 id、
尺寸列表、`file_reference`。评论超过 100 条就用 `offset_id` 往早翻，按 `message.id` 去重。

## 下载

```js
const blob = await rootScope.managers.apiFileManager
                          .downloadMedia({media: photo, thumb: 最大尺寸});
```

四个坑，全是试出来的：

1. 用 `apiFileManager`，别用 `appDownloadManager`。后者是 worker 镜像，下载文档前要走
   `appDocsManager.getDoc()` 查本地 store，没渲染过的文档查不到，直接抛
   `Cannot read properties of undefined`。

2. `media` 传裸的 photo / document（`msg.media.photo`），传 `msg.media` 整个包装会报
   `Cannot set properties of undefined`。

3. 照片必须给 `thumb`，不给就 reject（`preloadPhoto photoEmpty!`）。尺寸得自己挑：`sizes` 里混着
   `photoSizeProgressive`（最大档常常是它，**没有 `size` 字段**，只有 `sizes` 数组）和
   `photoStrippedSize`（模糊占位）。按 `w*h` 排，别按 `size` 排。给了 `thumb` 下载的就是这张图，
   挑错等于下错尺寸。

4. 文档必须给 `fileName`，不然 `Cannot read properties of undefined (reading 'id')`。
   更怪的是同一个文档第一次调用必定失败，失败完状态才准备好。先空跑一发：

```js
try { await afm.downloadMedia({media: doc, fileName: '__warmup__'}); } catch (e) {}
const blob = await afm.downloadMedia({media: doc, fileName: name});
```

## 落盘

Blob 别转 base64。一张 500KB 的图要在 JS 里拼七十万字符再回 Python 解码，慢十几倍还可能爆栈。
直接 POST 到本机：

```js
await fetch('http://127.0.0.1:8899/put?name=' + encodeURIComponent(name),
            {method: 'POST', body: blob});
```

HTTPS 页面请求 `http://127.0.0.1` 不算混合内容，localhost 是可信来源。
Python 这边起个 `ThreadingHTTPServer` 收 body 写盘，见 `sink.py`。

## 想再挖点别的

`performance.getEntriesByType('resource')` 里能翻出加载过的 JS 文件名，`appDownloadManager-xxxx.js`
这种，下下来读源码比瞎猜快得多。
