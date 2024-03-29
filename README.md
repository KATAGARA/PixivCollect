<h1 align="center">
  Pixiv Collect
  <br>
  <br>
  <a href="/LICENSE"><img src="https://img.shields.io/badge/license-GPL%203.0-brightgreen.svg" alt="GPL 3.0 LICENSE"></a>
  <a href="/releases"><img src="https://img.shields.io/badge/release-v0.0.1-blue.svg" alt="Pixiv Collect Releases"></a>
  <img src="https://img.shields.io/badge/Python-3.8-lightgrey" alt="Python">
</h1>

- [注意](#注意)
- [介绍](#介绍)
  - [Pixiv收集](#Pixiv收集)
  - [图片移动](#图片移动)
  - [分析图片](#分析图片)
  - [数据库信息](#数据库信息)
<br><br>
  
# 注意

本项目是为 [PixivAlbum](https://github.com/KAKETAKAGE/PixivAlbum) 项目服务的。<br>
需要安装数据库：[MongoDB](https://www.mongodb.com/try/download/community) [教程](/.github/docs/MongoDB.md)。<br>
请在执行目录下放置保存了 [Pixiv](https://www.pixiv.net/) 登入后cookie的cookie.txt文件 [教程](/.github/docs/Cookie.md)。


# 介绍

1. 收集Pixiv网站的图片并将信息保存到在MongoDB中。
2. 模块化设计，分为List、Illust、Image三个处理模块和监控模块Monitor。
3. 处理模块会启动进程并行运行。每个模块接受上游模块数据，用户->Monitor->List->Illust->Image。
4. Image模块会将已保存的作品信息保存到Image数据库，下次遇到未更新的此作品会跳过，避免重复下载。
5. 实时显示收集进度  
<br>

![进度条](https://raw.githubusercontent.com/KAKETAKAGE/PixivCollect/master/.github/imgs/py_tqdm.png)

## Pixiv收集

* `-t --type`：固定值：`pc`
* `-p --path`：`str` 保存图片的路径
* `-pb --pbar`：`[F, T]` 是否开启进度条
* `-db --dbName`：`str` 数据库名
* `-pt --port`：`int` MongoDB端口号
* `-d --date`：`int` 收集排行榜的日期，单次运行只能保存一天
* `-pa --params`：`JSON字符串`
* `-wr --waitRank`：`[F, T]` 是否等待排行榜更新
* `-pn --progressNum`：`JSON字符串` List，Illust和Image模块的进程数数组。eg：[1,5,10]  
<br>

--params eg: `[['overall'], ['original'], [''], 1, ['manga']]` 解释：
1. `['overall']` 数组为排行榜类型，可选值为：`overall, illust, ugoira, manga`
2. `['original]` 数组为排行榜模式，可选值为：`daily, weekly, monthly, original, male, female, rookie`
3. `['']` 数组为排行榜模式2（~~取不来名了~~），可选值为 `'', r18, r18g`，`''`为空，代表一般。
4. `true` 为是否保存图片，`false`只保存信息
5. `['manga]` 数组为排除此类图片，可选值为：`illust, ugoira, manga`  
<br>

下面3个是同等的<br>
`['overall', 'original', '', 1, ['manga']]` <br>
`[['overall'], ['original'], [''], 1, ['manga']]` <br>
`[[['overall'], ['original'], [''], 1, ['manga']]]`  
<br>

多条添加<br>
`[[['overall'], ['original'], [''], 1, ['manga']], [['illust', 'manga'], ['weekly'], ['', 'r18'], 1, ['manga']]]`  
<br>

因为命令行`"`的问题，输入时请用`!`代替`"`，先这样将就下。
```
.\pixiv_collect.exe -t pc -p E:/Pixiv -pb T -db Pixiv -pt 27017 -d 20210531 -pa [[!overall!],[!original!],[!!],1,[!manga!]] -wr T -pn [2,8,15]
```
### 已下载图片跳过
已下载图片跳过功能无法关闭（必须修改源码才能关闭）。现在只通过判断作品 upload_date 是否更新，image 集合中已下图片张数是否正确来判断是否需要下载图片。
这是目前想到的适用于 PixivAlbum 较好的方法，如有建议欢迎提出。


## 图片移动
* `-t --type`：固定值：`im`
* `--src`：`str` 图片移动源目录
* `--tra`：`str` 图片移动目标目录
* `-m --mode`：`[keep, move]` 图片移动模式
  * `keep` 源目录图片移动到目标目录（相同文件覆盖），图片移动日期参数的排行榜包含的图片保留在源目录。场景：图片保存在本机，把图片移动到外置硬盘中。
  * `move` 源目录中图片移动日期参数的排行榜包含的图片复制到目标目录。场景：外置硬盘中的图片复制到本机中。
* `-md --moveDate`：`JSON字符串` 图片移动日期，程序结束后`-md`中排行榜日期包含的图片在源目录和目标目录中都存在
* `-pb --pbar`：`[F, T]` 是否开启进度条
* `-db --dbName`：`str` 数据库名
* `-pt --port`：`int` MongoDB端口号  
<br>

```
场景一：图片保存到笔记本中，笔记本硬盘要被小姐姐塞满了，把小姐姐搬到豪宅去。
.\pixiv_collect.exe -t im --src E:/Pixiv --tra F:/Pixiv -m keep -md [20210531,20210530] -db Pixiv -pt 27017

场景二：把移动硬盘中的小姐姐复制到本机中，查看小姐姐时就不用一直插着移动硬盘了。
.\pixiv_collect.exe -t im --src F:/Pixiv --tra E:/Pixiv -m move -md [20210531] -db Pixiv -pt 27017
```

## 分析图片

获取目录中图片的张数、作品数和大小。

* `-t --type`：固定值：`ifa`
* `-p --path`：`str` 保存图片的路径
* `-pb --pbar`：`[F, T]` 是否开启进度条
* `-db --dbName`：`str` 数据库名
* `-pt --port`：`int` MongoDB端口号  
<br>

```
.\pixiv_collect.exe -t ifa -p E:/Pixiv -db Pixiv -pt 27017

{"illust": {"album": 5075, "image": 22645, "size": 34348193623}, "manga": {"album": 459, "image": 4508, "size": 6253882057}, "ugoira": {"album": 606, "image": 37139, "size": 3806648693}}
```

## 数据库信息

PixivAlbum项目中此功能为了界面美观开发的，会在0.1.0版本移除。

* `-t --type`：固定值：`gdi`
* `-db --dbName`：`str` 数据库名
* `-pt --port`：`int` MongoDB端口号  
<br>

```
.\pixiv_collect.exe -t gdi -db Pixiv -pt 27017

{"collections": 25, "documents": 30774406, "data_size": 15778838898.0, "index_size": 1604812800.0}
{"mode": "rank", "rank_date": 20210601, "params": "default", "total_illust": 7060, "real_illust": 4364, "download_illust": 1140, "download_image": 5317, "download_gif": 102, "use_time": 1491, "finish_time": "2021-06-02_11:56:51"}
```
