# P 盘那套的限制

用的是 [pikpakapi](https://github.com/Quan666/PikPakAPI) 这个库，但有几件事库本身没处理好，
自己补。

## 空间只有 6GB

免费号 6GB，原档一期动辄几 GB。做法是分批：转存一批 → 下载 → 删云端，再下一批。

```python
await cli.restore(sid, token, [f['id'] for f in batch])
await asyncio.sleep(8)                       # 等它落盘，别急着查
pack = await find_pack_folder(cli)           # 转存目标是 "Pack From Shared"
landed = await cli.file_list(parent_id=pack, size=100)
# 下载完立刻
await cli.delete_forever([src['id']])
```

## file_list 最大 100，而且会静默截断

`cli.file_list(parent_id=..., size=200)` 不会报错，就是只给你 100 条。所以一批最多 90 个文件，
否则后面 10 个永远下不到，而且不报错。分页要自己翻 `page_token`。

## 转存不一定马上落盘

`restore` 之后 `file_list` 里可能还有一部分没出现。不要当成失败，记着留到下一轮重试。
表现是日志里一堆「还没落盘」。

## 频率限制

跑太快会返回：

```
Aborted - Your operation is too frequent, please try again later
```

这时候继续重试没用，整个 API 都被限了。停一会儿再跑。批量跑的时候一期一期间隔一下。

## 断点

进度记在 `out/dl_progress.json`，key 是 `期数/文件名`。重跑时跳过已完成的。
文件名是分享里的原名（`1 (23).jpg` 这种），不要自己改，改了就对不上进度。

## 下载链接

`get_download_url` 返回的是有时效的直链，拿到就立刻下，别存。
