#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
from collections import defaultdict
import html
import json
from logging import DEBUG, INFO
from logging import getLogger
from logging import StreamHandler
import os
from os.path import dirname
from os.path import exists, isdir
from pathlib import Path
import random
import shutil
import sys
from urllib.parse import urlparse
import zipfile

import aiohttp
import twitter

logger = getLogger(__name__)
handler = StreamHandler()
handler.setLevel(INFO)
logger.setLevel(DEBUG)
logger.addHandler(handler)

OUTPUT_DIR = "output"
CSS_DIR = "css"
TW_STATUS_URL = "https://twitter.com/i/status/{}"

HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>BIRD:status/{id_str}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="canonical" href="{canonical_root}/i/status/{id_str}/">
  <link rel="stylesheet" href="/i/css/style.min.css?{stamp}">
</head>
<body>
<section id="content">
  <header>
    <h1 class="entry-title">status/{id_str}</h1>
  </header>
  <div class="entry-content entry-content-main">
    <h2>body</h2>
    <blockquote>
<p>{body}</p>
<p><a href="{tw_url}"><cite>{tw_url}</cite></a></p>
    </blockquote>
    <h2>media</h2>
    <ul>
{attachments}
    </ul>
    <h2>urls</h2>
    <ul>
{urls}
    </ul>
    <h2>json</h2>
    <pre>{payload}</pre>
    <a href="/i/list/{date}/">More information...</a>
  </div>
</section>
</body>
</html>
"""

LIST_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>BIRD:list/{date}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="canonical" href="{canonical_root}/i/list/{date}/">
  <link rel="stylesheet" href="/i/css/style.min.css?{stamp}">
</head>
<body>
<section id="content">
  <header>
    <h1 class="entry-title">list/{date}</h1>
  </header>
  <div class="entry-content entry-content-main">
{tweets}
  <a href="/i/list/{year}/">More information...</a>
  </div>
</section>
</body>
</html>
"""

MONTH_LIST_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>BIRD:list/{date}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="canonical" href="{canonical_root}/i/list/{date}/">
  <link rel="stylesheet" href="/i/css/style.min.css?{stamp}">
</head>
<body>
<section id="content">
  <header>
    <h1 class="entry-title">list/{date}</h1>
  </header>
  <div class="entry-content entry-content-main">
{tweets}
  <a href="/i/">More information...</a>
  </div>
</section>
</body>
</html>
"""

YEAR_LIST_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>BIRD: Information of Ruin Document</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="canonical" href="{canonical_root}/i/">
  <link rel="stylesheet" href="/i/css/style.min.css?{stamp}">
</head>
<body>
<section id="content">
  <header>
    <h1 class="entry-title">BIRD: Information of Ruin Document</h1>
  </header>
  <div class="entry-content entry-content-main">
  <p><small>パンツ、廃墟、サニタリーポーチ、シャンプー、クラゲ、Tシャツ、グラフィティ、結婚観、お酒、ポリャモリ、レズ風俗、長女、ぎょにそ、バスボム、残り物ミックスサンド、万引き、パチスロ必勝法、副業、ホメオパシー、激安バッグ、今すぐ</small></p>
{tweets}
  <a href="..">More information...</a>
  </div>
</section>
</body>
</html>
"""


def _load_json(z, filename):
    data = str(z.open(filename).read(), encoding="utf-8")
    i = min(filter(lambda x: x > 0, [data.find("["), data.find("{"), data.find("\"")]), default=0)
    return data[:i], json.loads(data[i:])


async def _save(src, dst, sem, loop):
    try:
        async with sem:
            async with aiohttp.ClientSession(loop=loop) as client:
                req = await client.request("GET", "{}".format(src))
                body = await req.read()
                logger.info("downloaded: {}".format(src))
                req.close()
    except Exception as ex:
        logger.warning("cannot open: {} ({})".format(src, ex))
        return
    if not exists(dirname(dst)):
        os.makedirs(dirname(dst))
    with open(dst, "wb") as f:
        f.write(body)


def _get_tweet_list(archive, user_id, output_root, canonical_root, url_basepath, css_hash, media):
    _, statistic = _load_json(archive, "data/js/payload_details.js")
    _, user = _load_json(archive, "data/js/user_details.js")
    _, index = _load_json(archive, "data/js/tweet_index.js")
    logger.debug("You are @{screen_name} ({id}).".format(**user))
    logger.debug("There are {tweets} tweets until {created_at}.".format(**statistic))
    tweet_basepath = "{}/i/status/{{}}/index.html".format(output_root)
    tweet_urlbase = "/i/status/{}/"
    tweet_list_basepath = "{}/i/list/{{}}/index.html".format(output_root)
    tweet_list_urlbase = "/i/list/{}/"
    tweet_list_list_path = "{}/i/index.html".format(output_root)

    _media = defaultdict(list)
    for x in media:
        url = url_basepath.format(urlparse(x[0].replace(r"\/", "/"))[2])
        if url.endswith(":large"):
            url = url[:-6]
        _media[x[2]].append(url)

    dates = defaultdict(list)
    for x in index:
        h, tweets = _load_json(archive, x.get("file_name"))
        dates[x.get("year")].append((x.get("month"), len([t for t in tweets if
                                                          t.get("user").get("id") == user_id])))
        files = list()
        for t in tweets:
            t = t.get("retweeted_status", t)
            if t.get("user").get("id") == user_id:
                id_str = t.get("id_str")
                text = t.get("text").strip()
                text = text or "<i>(no text)</i>"
                urls = list()
                attachments = list()
                for i, u in enumerate(t.get("entities").get("urls")):
                    _u = u.get("expanded_url")
                    d = u.get("display_url")
                    urls.append("""<li><a href="{}">{}</a></li>""".format(_u, d))
                for i, m in enumerate(_media.get(t.get("id_str"), [])):
                    attachments.append("""<li><a href="{0}">{0}</a></li>""".format(m))
                tw_path = tweet_basepath.format(id_str)
                if not exists(dirname(tw_path)):
                    os.makedirs(dirname(tw_path))
                attachments = attachments or ["<li>(no media)</li>"]
                urls = urls or ["<li>(no urls)</li>"]
                date = "{:04d}/{:02d}".format(x.get("year"), x.get("month"))
                with open(tw_path, "w") as f:
                    f.write(HTML.format(id_str=id_str,
                                        date=date,
                                        body=text.replace("\n", "<br>"),
                                        payload=html.escape(json.dumps(t, indent=2)),
                                        tw_url=TW_STATUS_URL.format(id_str),
                                        attachments="\n".join(attachments),
                                        urls="\n".join(urls),
                                        canonical_root=canonical_root,
                                        stamp=css_hash).strip())
                logger.info("wrote tweet: {}".format(id_str))
                item = """<h2><a href="{}">status/{}</a></h2>
<blockquote>
<p>{}</p>
</blockquote>
""".format(tweet_urlbase.format(id_str), id_str, text)
                files.append(item)
        year = "{:04d}".format(x.get("year"))
        date = "{:04d}/{:02d}".format(x.get("year"), x.get("month"))
        tw_list_path = tweet_list_basepath.format(date)
        if not exists(dirname(tw_list_path)):
            os.makedirs(dirname(tw_list_path))
        with open(tw_list_path, "w") as f:
            f.write(LIST_HTML.format(date=date, year=year, tweets="\n".join(files),
                                     canonical_root=canonical_root, stamp=css_hash))
        logger.info("wrote tweet list: {}".format(date))
    for y, v in dates.items():
        year = "{:04d}".format(y)
        tw_list_list_path = tweet_list_basepath.format(year)
        files = list()
        for m, c in v:
            date = "{:04d}/{:02d}".format(y, m)
            tw_list_path = tweet_list_urlbase.format(date)
            files.append("""
<h2><a href="{}">list/{}</a></h2>
<p>{} tweets ...</p>
""".format(tw_list_path, date, c))
        with open(tw_list_list_path, "w") as f:
            f.write(MONTH_LIST_HTML.format(date=year, tweets="\n".join(files),
                                           canonical_root=canonical_root, stamp=css_hash))
        logger.info("wrote tweet list: {}".format(date))
    files = list()
    for y in sorted(dates.keys(), reverse=True):
        year = "{:04d}".format(y)
        tw_list_path = tweet_list_urlbase.format(year)
        files.append("""
<h2><a href="{}">list/{}</a></h2>
<p>{} tweets ...</p>
""".format(tw_list_path, year, sum([x[1] for x in dates[y]])))
    with open(tweet_list_list_path, "w") as f:
        f.write(YEAR_LIST_HTML.format(tweets="\n".join(files),
                                      canonical_root=canonical_root, stamp=css_hash))
    logger.info("wrote tweet list: all")


def _get_media_list(archive, output_root, consumer_key, consumer_secret, with_extract_video=True):
    _, statistic = _load_json(archive, "data/js/payload_details.js")
    _, user = _load_json(archive, "data/js/user_details.js")
    _, index = _load_json(archive, "data/js/tweet_index.js")
    logger.debug("You are @{screen_name} ({id}).".format(**user))
    logger.debug("There are {tweets} tweets until {created_at}.".format(**statistic))
    image_basepath = "{}/i/images{{}}".format(output_root)

    media = list()
    videos = list()
    for i, x in enumerate(index):
        h, tweets = _load_json(archive, x.get("file_name"))
        for t in filter(lambda m: (m.get("retweeted_status", m)
                                   .get("entities").get("media") and
                                   m.get("user").get("id") == 2415471974 and
                                   "@" not in m.get("text")),
                        tweets):
            for m in t.get("retweeted_status", t).get("entities").get("media"):
                img = m.get("media_url_https")
                if "video" in img:
                    logger.debug("found video: status/{}".format(t["id_str"]))
                    videos.append(t["id_str"])
                logger.debug("appended image: {}:large".format(img))
                media.append(("{}:large".format(img),
                              image_basepath.format(urlparse(img.replace(r"\/", "/"))[2]),
                              t["id_str"]))
    if with_extract_video:
        twi = twitter.Twitter(auth=twitter.OAuth("", "", consumer_key, consumer_secret))
        for t in twi.statuses.lookup(_id=",".join(videos)):
            for m in t.get("retweeted_status", t).get("extended_entities").get("media"):
                url = sorted(m.get("video_info").get("variants"),
                             key=lambda x: x.get("bitrate", -1),
                             reverse=True)[0].get("url")
                logger.debug("appended video: {}".format(url))
                media.append((url, image_basepath.format(urlparse(url.replace(r"\/", "/"))[2]),
                              m["id_str"]))
    return media


def _download_media_list(media):
    logger.debug("saving image ...")
    loop = asyncio.get_event_loop()
    sem = asyncio.Semaphore(32)
    loop.run_until_complete(asyncio.wait([_save(x[0], x[1], sem, loop) for x in media]))
    loop.close()
    logger.debug("... saved image")


def main(archive_path, user_id, output_root, canonical_root, css_hash,
         consumer_key=None, consumer_secret=None, media_path=None):
    try:
        archive = zipfile.ZipFile(archive_path)
    except (FileNotFoundError, PermissionError, IsADirectoryError, zipfile.BadZipFile) as ex:
        logger.fatal("Cannot open zip archive for read")
        raise ex
    except Exception as ex:
        raise ex

    media = list()
    if consumer_key and consumer_secret:
        media = _get_media_list(archive, output_root, consumer_key, consumer_secret)
        if media_path:
            try:
                with open(media_path, "w") as f:
                    f.write("\n".join([x[0] for x in media]))
            except (PermissionError, IsADirectoryError) as ex:
                logger.fatal("Cannot open media list for write")
                raise ex
            except Exception as ex:
                raise ex
    elif media_path:
        image_basepath = "{}/i/images{{}}".format(output_root)
        try:
            with open(media_path) as f:
                media = f.read().split("\n")
        except (FileNotFoundError, PermissionError, IsADirectoryError) as ex:
            logger.fatal("Cannot open media list for read")
            raise ex
        except Exception as ex:
            raise ex
        media = [(x, image_basepath.format(urlparse(x.replace(r"\/", "/"))[2])) for x in media]
    else:
        logger.fatal("Specify consumer_key/secret or media_file_list_path")
        return

    _get_tweet_list(archive, user_id, output_root, canonical_root, "/i/images{}", css_hash, media)

    _download_media_list(media)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        logger.fatal("usage: {} TWITTER_ZIP_ARCHIVE(archive.zip) YOUR_USER_ID \
CANONICAL_ROOT(https://example.com) [MEDIA_LIST(media_list.txt)]".format(sys.argv[0]))
        sys.exit(1)

    archive_path = sys.argv[1]
    try:
        user_id = int(sys.argv[2])
    except ValueError:
        logger.fatal("USER_ID must be int: {}".format(sys.argv[2]))
        sys.exit(2)
    canonical_root = sys.argv[3]
    media_path = sys.argv[4] if len(sys.argv) > 4 else "media_list.txt"

    consumer_key = ""
    consumer_secret = ""
    try:
        with open("credential.json") as f:
            c = json.load(f)
            consumer_key = c["ck"]
            consumer_secret = c["cs"]
    except FileNotFoundError:
        logger.warning("Not found: credential.json")
    except PermissionError:
        logger.warning("Cannot open: credential.json")
    except KeyError:
        logger.warning("No key in credentials.json: consumer_key(ck) or consumer_secret(cs)")
    if not exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        logger.info("Created output directory: {}".format(OUTPUT_DIR))

    CSS_DST = Path(OUTPUT_DIR) / "i" / Path(CSS_DIR).parts[-1]
    if exists(CSS_DST):
        logger.warning("Cannot copy directory: '{}' -> '{}'".format(CSS_DIR, CSS_DST))
        logger.warning("Already exists: {}".format(CSS_DST))
    elif isdir(CSS_DIR):
        shutil.copytree(CSS_DIR, CSS_DST)
        logger.info("Copied css directory: {} -> {}".format(CSS_DIR, CSS_DST))
    else:
        logger.warning("Cannot copy directory: '{}' -> '{}'".format(CSS_DIR, CSS_DST))
        logger.warning("Not found: {}".format(CSS_DIR))

    css_hash = "".join(random.choices("0123456789abcdef", k=8))
    try:
        main(archive_path, user_id, OUTPUT_DIR, canonical_root, css_hash,
             consumer_key, consumer_secret, media_path)
    except (FileNotFoundError, PermissionError, IsADirectoryError) as ex:
        logger.fatal("{}: {}".format(ex.strerror, ex.filename))
        sys.exit(3)
    except (zipfile.BadZipFile) as ex:
        logger.fatal("{}: {}".format(str(ex), archive_path))
        sys.exit(4)
