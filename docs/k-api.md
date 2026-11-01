# Web K 的调用姿势

浏览器打开 `https://web.telegram.org/k/` 之后，登录态存在 profile 目录里。页面加载完
（约 13 秒，别省）内部的 manager 就挂在 window 上了：

```js
window.rootScope.managers.apiManager          // MTProto 入口
window.appDownloadManager                     // 文件下载
window.rootScope.managers.apiFileManager
```

## 拿频道 peer

MTProto 的方法都要 inputPeer，`getDialogs` 里就有现成的 id 和 access_hash：

```js
const d = await api.invokeApi('messages.getDialogs', {
  offset_date: 0, offset_id: 0, offset_peer: {_: 'inputPeerEmpty'},
  limit: 100, hash: 0});
const c = d.chats.find(x => x.username === 'channel_name');
const peer = {_: 'inputPeerChannel', channel_id: c.id, access_hash: c.access_hash};
```

频道不在对话列表里就找不到。私有频道只能先手动打开一次。

## 枚举某一期的帖子

```js
await api.invokeApi('messages.search', {
  peer, q: '#作者tag', filter: {_: 'inputMessagesFilterEmpty'},
  min_date: 0, max_date: 0, offset_id: 0, add_offset: 0,
  limit: 100, max_id: 0, min_id: 0, hash: 0});
```

翻页靠 `offset_id` 传上一页最小的消息 id，直到返回空。

## 拿相册本体

作者把图放在评论区的相册里，频道帖子只是封面 + 标题。用 `messages.getReplies` 拉评论区：

```js
await api.invokeApi('messages.getReplies', {
  peer, msg_id: postId, offset_id: 0, offset_date: 0, add_offset: 0,
  limit: 100, max_id: 0, min_id: 0, hash: 0});
```

返回的 `messages` **按 id 倒序**，翻过来就是相册顺序。每个消息的 `media.photo` 或
`media.document` 里带着文件 id、尺寸列表、`file_reference`。

一个帖子的评论可能超过 100 条，用 `offset_id` 往更早翻。去重按 `message.id`。

## 下载

```js
const blob = await rootScope.managers.apiFileManager
                          .downloadMedia({media: photo, thumb: 最大尺寸});
```

四个坑：

1. 用 `rootScope.managers.apiFileManager`，不是 `appDownloadManager`。后者是 worker 镜像，
   文档要走 `appDocsManager.getDoc()` 查本地 store，查不到就崩。
2. `media` 要传**裸的 photo / document 对象**（`msg.media.photo`），传 `msg.media` 整个包装会报
   `Cannot set properties of undefined`。
3. 照片必须给 `thumb`，否则直接 reject（`preloadPhoto photoEmpty!`）。尺寸要自己挑：`sizes` 里混着
   `photoSizeProgressive`（最大档常是它，**没有 `size` 字段**，只有 `sizes` 数组）和
   `photoStrippedSize`（模糊占位图）。按 `w*h` 排序取最大，别按 `size` 排。给了 `thumb` 之后
   下载的是**这张图**，所以 thumb 挑错就等于下错尺寸。
4. 文档必须给 `fileName`，否则 `Cannot read properties of undefined (reading 'id')`。更怪的是
   **同一个文档的第一次调用必定失败**，失败之后状态才准备好。所以先空跑一发再正式下：

```js
try { await afm.downloadMedia({media: doc, fileName: '__warmup__'}); } catch (e) {}
const blob = await afm.downloadMedia({media: doc, fileName: name});
```

## 落盘

Blob 别转 base64 —— 一张 500KB 的图要在 JS 里拼七十万字符的字符串再回传 Python 解码，
慢十几倍还可能爆栈。直接 POST 到本机：

```js
await fetch('http://127.0.0.1:8899/put?name=' + encodeURIComponent(name),
            {method: 'POST', body: blob});
```

HTTPS 页面请求 `http://127.0.0.1` 不会被当成混合内容拦掉，localhost 算可信来源。
Python 侧起个 `ThreadingHTTPServer` 收 body 写盘就行，见 `sink.py`。

## 其他

- 进页面先按一下 `Escape`，K 有时候会弹「外观设置」挡住。
- 想找内部的某个方法，去 `performance.getEntriesByType('resource')` 里翻 JS 文件名，
  `appDownloadManager-xxxx.js` 这种，下载下来读。
