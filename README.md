# extract-twitter

## Usage

1. Copy `example.credential.json` to `credential.json` and set consumer_key (`ck`) and consumer_secret (`cs`).

2. Run `./main.py TWITTER_ZIP_ARCHIVE YOUR_USER_ID CANONICAL_ROOT [MEDIA_LIST=media_list.txt]`.

    * TWITTER_ZIP_ARCHIVE: path to ZIP archive downloaded from "Your Tweet archive" on [https://twitter.com/settings/account](https://twitter.com/settings/account).
    * YOUR_USER_ID: your twitter user id (perhaps first part of ZIP archive name)
    * CANONICAL_ROOT: your site root (e.g. https://example.com)
    * MEDIA_LIST (one url per line, optional): If `credential.json` is not found, this file will be used for downloading media.
